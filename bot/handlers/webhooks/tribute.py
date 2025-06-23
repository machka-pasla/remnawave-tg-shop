import logging
import hmac
import hashlib
import json
from aiohttp import web
from aiogram import Bot
from sqlalchemy.orm import sessionmaker

from config.settings import Settings
from bot.middlewares.i18n import JsonI18n
from bot.services.subscription_service import SubscriptionService
from bot.services.panel_api_service import PanelApiService
from bot.services.referral_service import ReferralService
from db.dal import payment_dal, user_dal, subscription_dal

async def tribute_webhook_route(request: web.Request):
    bot: Bot = request.app['bot']
    settings: Settings = request.app['settings']
    i18n: JsonI18n = request.app['i18n']
    async_session_factory: sessionmaker = request.app['async_session_factory']
    panel_service: PanelApiService = request.app['panel_service']
    subscription_service: SubscriptionService = request.app['subscription_service']
    referral_service: ReferralService = request.app['referral_service']

    raw_body = await request.read()
    signature_header = request.headers.get('trbt-signature')
    if settings.TRIBUTE_API_KEY:
        if not signature_header:
            return web.Response(status=403, text="no_signature")
        expected_sig = hmac.new(
            settings.TRIBUTE_API_KEY.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, signature_header):
            return web.Response(status=403, text="invalid_signature")

    try:
        payload = json.loads(raw_body.decode())
    except Exception:
        return web.Response(status=400, text="bad_request")

    event_name = payload.get('name')
    data = payload.get('payload', {})
    user_id = data.get('telegram_user_id')
    price_val = data.get('price')

    if not user_id or price_val is None:
        return web.Response(status=200, text="ok_missing_fields")

    months_map = {int(v): m for m, v in settings.subscription_options.items()}
    months = months_map.get(int(price_val))
    if not months:
        logging.warning(f"Tribute webhook: price {price_val} not mapped to months")
        return web.Response(status=200, text="ok_price_unmapped")

    async with async_session_factory() as session:
        if event_name == 'new_subscription':
            payment_record = await payment_dal.create_payment_record(
                session,
                {
                    'user_id': user_id,
                    'amount': float(price_val),
                    'currency': 'RUB',
                    'status': 'succeeded',
                    'description': 'Tribute subscription',
                    'subscription_duration_months': months,
                    'provider_payment_id': str(data.get('subscription_id')),
                    'provider': 'tribute',
                },
            )
            await subscription_service.activate_subscription(
                session,
                user_id,
                months,
                float(price_val),
                payment_record.payment_id,
                provider='tribute',
            )
            await referral_service.apply_referral_bonuses_for_payment(
                session, user_id, months
            )
            await session.commit()
        elif event_name == 'cancelled_subscription':
            db_user = await user_dal.get_user_by_id(session, user_id)
            lang = db_user.language_code if db_user and db_user.language_code else settings.DEFAULT_LANGUAGE
            _ = lambda k, **kw: i18n.gettext(lang, k, **kw)
            try:
                await bot.send_message(user_id, _("subscription_cancelled_notification"))
            except Exception as e:
                logging.warning(f"Failed to notify user {user_id} about cancellation: {e}")
            await subscription_dal.set_skip_notifications_for_provider(
                session, user_id, 'tribute', False)
            await session.commit()
        else:
            await session.commit()
    return web.Response(status=200, text="ok")
