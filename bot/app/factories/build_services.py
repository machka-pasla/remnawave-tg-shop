from aiogram import Bot
from sqlalchemy.orm import sessionmaker

from config.settings import Settings
from bot.middlewares.i18n import JsonI18n
from bot.services.yookassa_service import YooKassaService
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service import SubscriptionService
from bot.services.referral_service import ReferralService
from bot.services.promo_code_service import PromoCodeService
from bot.services.stars_service import StarsService
from bot.services.tribute_service import TributeService
from bot.services.crypto_pay_service import CryptoPayService
from bot.services.panel_webhook_service import PanelWebhookService


def build_core_services(
    settings: Settings,
    bot: Bot,
    async_session_factory: sessionmaker,
    i18n: JsonI18n,
    bot_username_for_default_return: str,
):
    panel_service = PanelApiService(settings)
    subscription_service = SubscriptionService(settings, panel_service, bot, i18n)
    referral_service = ReferralService(settings, subscription_service, bot, i18n)
    promo_code_service = PromoCodeService(settings, subscription_service, bot, i18n)
    stars_service = StarsService(bot, settings, i18n, subscription_service, referral_service)
    cryptopay_service = CryptoPayService(
        settings.CRYPTOPAY_TOKEN,
        settings.CRYPTOPAY_NETWORK,
        bot,
        settings,
        i18n,
        async_session_factory,
        subscription_service,
        referral_service,
    )
    tribute_service = TributeService(
        bot,
        settings,
        i18n,
        async_session_factory,
        panel_service,
        subscription_service,
        referral_service,
    )
    panel_webhook_service = PanelWebhookService(bot, settings, i18n, async_session_factory, panel_service)
    yookassa_service = YooKassaService(
        shop_id=settings.YOOKASSA_SHOP_ID,
        secret_key=settings.YOOKASSA_SECRET_KEY,
        configured_return_url=settings.YOOKASSA_RETURN_URL,
        bot_username_for_default_return=bot_username_for_default_return,
        settings_obj=settings,
    )

    # Wire services that depend on each other
    try:
        # Attach YooKassa to subscription service for auto-renew charges
        setattr(subscription_service, "yookassa_service", yookassa_service)
        # Allow panel webhook to trigger renewals through subscription service
        setattr(panel_webhook_service, "subscription_service", subscription_service)
    except Exception:
        pass

    return {
        "panel_service": panel_service,
        "subscription_service": subscription_service,
        "referral_service": referral_service,
        "promo_code_service": promo_code_service,
        "stars_service": stars_service,
        "cryptopay_service": cryptopay_service,
        "tribute_service": tribute_service,
        "panel_webhook_service": panel_webhook_service,
        "yookassa_service": yookassa_service,
    }


