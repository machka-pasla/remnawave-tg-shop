import json
import logging
import hmac
import hashlib
from aiohttp import web
from aiogram import Bot
from sqlalchemy.orm import sessionmaker
from typing import Optional
from config.settings import Settings
from bot.middlewares.i18n import JsonI18n
from db.dal import user_dal

EVENT_MAP = {
    "user.expires_in_72_hours": (3, "subscription_72h_notification"),
    "user.expires_in_48_hours": (2, "subscription_48h_notification"),
    "user.expires_in_24_hours": (1, "subscription_24h_notification"),
}

class PanelWebhookService:
    def __init__(self, bot: Bot, settings: Settings, i18n: JsonI18n, async_session_factory: sessionmaker):
        self.bot = bot
        self.settings = settings
        self.i18n = i18n
        self.async_session_factory = async_session_factory

    async def _send_message(self, user_id: int, lang: str, message_key: str, **kwargs):
        _ = lambda k, **kw: self.i18n.gettext(lang, k, **kw)
        try:
            await self.bot.send_message(user_id, _(message_key, **kwargs))
        except Exception as e:
            logging.error(f"Failed to send notification to {user_id}: {e}")

    async def handle_event(self, event_name: str, user_payload: dict):
        telegram_id = user_payload.get("telegramId")
        if not telegram_id:
            logging.warning("Panel webhook without telegramId received")
            return
        user_id = int(telegram_id)

        if not self.settings.SUBSCRIPTION_NOTIFICATIONS_ENABLED:
            return

        async with self.async_session_factory() as session:
            db_user = await user_dal.get_user_by_id(session, user_id)
            lang = db_user.language_code if db_user and db_user.language_code else self.settings.DEFAULT_LANGUAGE
            first_name = db_user.first_name or f"User {user_id}" if db_user else f"User {user_id}"

        if event_name in EVENT_MAP:
            days_left, msg_key = EVENT_MAP[event_name]
            if days_left == self.settings.SUBSCRIPTION_NOTIFY_DAYS_BEFORE:
                await self._send_message(
                    user_id,
                    lang,
                    msg_key,
                    user_name=first_name,
                    end_date=user_payload.get("expireAt", "")[:10],
                )
        elif event_name == "user.expired" and self.settings.SUBSCRIPTION_NOTIFY_ON_EXPIRE:
            await self._send_message(user_id, lang, "subscription_expired_notification")
        elif event_name == "user.expired_24_hours_ago" and self.settings.SUBSCRIPTION_NOTIFY_AFTER_EXPIRE:
            await self._send_message(user_id, lang, "subscription_expired_yesterday_notification")

    async def handle_webhook(self, raw_body: bytes, signature_header: Optional[str]) -> web.Response:
        if self.settings.PANEL_WEBHOOK_SECRET:
            if not signature_header:
                return web.Response(status=403, text="no_signature")
            expected_sig = hmac.new(
                self.settings.PANEL_WEBHOOK_SECRET.encode(),
                raw_body,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected_sig, signature_header):
                return web.Response(status=403, text="invalid_signature")

        try:
            payload = json.loads(raw_body.decode())
        except Exception:
            return web.Response(status=400, text="bad_request")

        event_name = payload.get("name") or payload.get("event")
        user_data = payload.get("payload", {}).get("user") or payload.get("payload", {})
        if not event_name:
            return web.Response(status=200, text="ok_no_event")

        await self.handle_event(event_name, user_data)
        return web.Response(status=200, text="ok")

async def panel_webhook_route(request: web.Request):
    service: PanelWebhookService = request.app["panel_webhook_service"]
    raw = await request.read()
    signature_header = request.headers.get("X-Remnawave-Signature")
    return await service.handle_webhook(raw, signature_header)
