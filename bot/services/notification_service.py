import logging
import asyncio
from aiogram import Bot
from aiogram.utils.text_decorations import html_decoration as hd
from datetime import datetime, timezone

from config.settings import Settings

from sqlalchemy.orm import sessionmaker
from bot.middlewares.i18n import JsonI18n


async def notify_admins(bot: Bot, settings: Settings, i18n: JsonI18n,
                        message_key: str, parse_mode: str | None = None,
                        **kwargs) -> None:
    if not settings.ADMIN_IDS:
        return
    admin_lang = settings.DEFAULT_LANGUAGE
    msg = i18n.gettext(admin_lang, message_key, **kwargs)
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, msg, parse_mode=parse_mode)
        except Exception as e:
            logging.error(f"Failed to send admin notification to {admin_id}: {e}")


async def notify_admin_new_trial(bot: Bot, settings: Settings, i18n: JsonI18n,
                                 user_id: int, end_date: datetime) -> None:
    end_date_str = end_date.strftime('%Y-%m-%d') if isinstance(end_date, datetime) else str(end_date)
    await notify_admins(
        bot,
        settings,
        i18n,
        "admin_new_trial_notification",
        user_id=user_id,
        end_date=end_date_str,
    )


async def notify_admin_new_payment(bot: Bot, settings: Settings, i18n: JsonI18n,
                                   user_id: int, months: int, amount: float,
                                   currency: str | None = None) -> None:
    currency_symbol = currency or settings.DEFAULT_CURRENCY_SYMBOL
    await notify_admins(
        bot,
        settings,
        i18n,
        "admin_new_payment_notification",
        user_id=user_id,
        months=months,
        amount=f"{amount:.2f}",
        currency=currency_symbol,
    )


async def notify_admin_promo_activation(bot: Bot, settings: Settings,
                                        i18n: JsonI18n, user_id: int,
                                        code: str,
                                        bonus_days: int) -> None:
    await notify_admins(
        bot,
        settings,
        i18n,
        "admin_promo_activation_notification",
        user_id=user_id,
        code=code,
        bonus_days=bonus_days,
    )
