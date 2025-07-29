import logging
import json
from typing import Optional

from aiogram import Bot
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from aiocryptopay import AioCryptoPay, Networks
from aiocryptopay.models.update import Update

from config.settings import Settings
from bot.middlewares.i18n import JsonI18n
from bot.services.subscription_service import SubscriptionService
from bot.services.referral_service import ReferralService
from bot.keyboards.inline.user_keyboards import get_connect_and_main_keyboard
from bot.services.notification_service import notify_admin_new_payment
from db.dal import payment_dal, user_dal


class CryptoPayService:
    def __init__(
        self,
        token: Optional[str],
        network: str,
        bot: Bot,
        settings: Settings,
        i18n: JsonI18n,
        async_session_factory: sessionmaker,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
    ):
        self.bot = bot
        self.settings = settings
        self.i18n = i18n
        self.async_session_factory = async_session_factory
        self.subscription_service = subscription_service
        self.referral_service = referral_service
        if token:
            net = Networks.TEST_NET if str(network).lower() == "testnet" else Networks.MAIN_NET
            self.client = AioCryptoPay(token=token, network=net)
            self.client.register_pay_handler(self._invoice_paid_handler)
            self.configured = True
        else:
            logging.warning("CryptoPay token not provided. CryptoPay disabled")
            self.client = None
            self.configured = False

    async def close(self):
        """Close underlying AioCryptoPay session if initialized."""
        if self.client:
            try:
                await self.client.close()
                logging.info("CryptoPay client session closed.")
            except Exception as e:
                logging.warning(f"Failed to close CryptoPay client: {e}")

    async def create_invoice(
        self,
        session: AsyncSession,
        user_id: int,
        months: int,
        amount: float,
        description: str,
    ) -> Optional[str]:
        if not self.configured or not self.client:
            logging.error("CryptoPayService not configured")
            return None

        payment_record = await payment_dal.create_payment_record(
            session,
            {
                "user_id": user_id,
                "amount": float(amount),
                "currency": self.settings.CRYPTOPAY_ASSET,
                "status": "pending_cryptopay",
                "description": description,
                "subscription_duration_months": months,
                "provider": "cryptopay",
            },
        )
        payload = json.dumps({
            "user_id": str(user_id),
            "subscription_months": str(months),
            "payment_db_id": str(payment_record.payment_id),
        })
        try:
            invoice = await self.client.create_invoice(
                amount=amount,
                currency_type=self.settings.CRYPTOPAY_CURRENCY_TYPE,
                fiat=self.settings.CRYPTOPAY_ASSET if self.settings.CRYPTOPAY_CURRENCY_TYPE == "fiat" else None,
                asset=self.settings.CRYPTOPAY_ASSET if self.settings.CRYPTOPAY_CURRENCY_TYPE == "crypto" else None,
                description=description,
                payload=payload,
            )
            await payment_dal.update_provider_payment_and_status(
                session,
                payment_record.payment_id,
                str(invoice.invoice_id),
                str(invoice.status),
            )
            return invoice.bot_invoice_url
        except Exception as e:
            logging.error(f"CryptoPay invoice creation failed: {e}", exc_info=True)
            return None

    async def _invoice_paid_handler(self, update: Update, app: web.Application):
        invoice = update.payload
        if not invoice.payload:
            logging.warning("CryptoPay webhook without payload")
            return
        try:
            meta = json.loads(invoice.payload)
            user_id = int(meta["user_id"])
            months = int(meta["subscription_months"])
            payment_db_id = int(meta["payment_db_id"])
        except Exception as e:
            logging.error(f"Failed to parse CryptoPay payload: {e}")
            return

        async_session_factory: sessionmaker = app["async_session_factory"]
        bot: Bot = app["bot"]
        settings: Settings = app["settings"]
        i18n: JsonI18n = app["i18n"]
        subscription_service: SubscriptionService = app["subscription_service"]
        referral_service: ReferralService = app["referral_service"]

        async with async_session_factory() as session:
            try:
                await payment_dal.update_provider_payment_and_status(
                    session,
                    payment_db_id,
                    str(invoice.invoice_id),
                    "succeeded",
                )
                activation = await subscription_service.activate_subscription(
                    session,
                    user_id,
                    months,
                    float(invoice.amount),
                    payment_db_id,
                    provider="cryptopay",
                )
                referral_bonus = await referral_service.apply_referral_bonuses_for_payment(
                    session, user_id, months
                )
                await session.commit()
            except Exception as e:
                await session.rollback()
                logging.error(f"Failed to process CryptoPay invoice: {e}", exc_info=True)
                return

            db_user = await user_dal.get_user_by_id(session, user_id)
            lang = db_user.language_code if db_user and db_user.language_code else settings.DEFAULT_LANGUAGE
            _ = lambda k, **kw: i18n.gettext(lang, k, **kw)

            config_link = activation.get("subscription_url") or _("config_link_not_available")
            final_end = activation.get("end_date")
            applied_days = 0
            if referral_bonus and referral_bonus.get("referee_new_end_date"):
                final_end = referral_bonus["referee_new_end_date"]
                applied_days = referral_bonus.get("referee_bonus_applied_days", 0)

            if applied_days:
                inviter_name_display = _("friend_placeholder")
                if db_user and db_user.referred_by_id:
                    inviter = await user_dal.get_user_by_id(session, db_user.referred_by_id)
                    if inviter and inviter.first_name:
                        inviter_name_display = inviter.first_name
                    elif inviter and inviter.username:
                        inviter_name_display = f"@{inviter.username}"
                text = _("payment_successful_with_referral_bonus_full",
                         months=months,
                         base_end_date=activation["end_date"].strftime('%Y-%m-%d'),
                         bonus_days=applied_days,
                         final_end_date=final_end.strftime('%Y-%m-%d'),
                         inviter_name=inviter_name_display,
                         config_link=config_link)
            else:
                text = _("payment_successful_full",
                         months=months,
                         end_date=final_end.strftime('%Y-%m-%d'),
                         config_link=config_link)

            markup = get_connect_and_main_keyboard(lang, i18n, settings, config_link)
            try:
                await bot.send_message(
                    user_id,
                    text,
                    reply_markup=markup,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logging.error(f"Failed to send CryptoPay success message: {e}")

            await notify_admin_new_payment(
                bot,
                settings,
                i18n,
                user_id,
                months,
                float(invoice.amount),
                currency=invoice.asset or settings.DEFAULT_CURRENCY_SYMBOL,
            )

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured or not self.client:
            return web.Response(status=503, text="cryptopay_disabled")
        return await self.client.get_updates(request)


async def cryptopay_webhook_route(request: web.Request) -> web.Response:
    service: CryptoPayService = request.app["cryptopay_service"]
    return await service.webhook_route(request)
