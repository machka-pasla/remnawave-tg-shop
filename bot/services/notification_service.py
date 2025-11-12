import logging
import asyncio
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.text_decorations import html_decoration as hd
from aiogram.exceptions import TelegramRetryAfter
from datetime import datetime, timezone
from typing import Optional, Union, Dict, Any, Callable

from config.settings import Settings
from sqlalchemy.orm import sessionmaker
from bot.middlewares.i18n import JsonI18n
from bot.utils.message_queue import get_queue_manager
from bot.utils.text_sanitizer import (
    display_name_or_fallback,
    username_for_display,
)
from bot.utils.id_bridge import get_id_bridge, IdBridge, admin_recipient_ids


class NotificationService:
    """Enhanced notification service for sending messages to admins and log channels"""
    
    def __init__(self, bot: Bot, settings: Settings, i18n: Optional[JsonI18n] = None):
        self.bot = bot
        self.settings = settings
        self.i18n = i18n
        try:
            self.id_bridge: Optional[IdBridge] = get_id_bridge()
        except RuntimeError:
            self.id_bridge = None

    def _format_user_display(
        self,
        user_id: Union[int, str],
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> str:
        identifier = self._public_identifier(user_id)
        if self.settings.TELEGRAM_ID_ENCRYPTION:
            return f"<code>{identifier}</code>"
        base_display = display_name_or_fallback(first_name, f"ID {identifier}")
        if username:
            base_display = f"{base_display} ({username_for_display(username)})"
        return base_display

    def _public_identifier(self, user_ref: Union[int, str]) -> str:
        if self.id_bridge and self.id_bridge.enabled:
            if isinstance(user_ref, str):
                try:
                    return self.id_bridge.normalize_uid(user_ref)
                except ValueError:
                    pass
            try:
                return self.id_bridge.tid_to_uid(int(user_ref))
            except (ValueError, TypeError):
                return str(user_ref)
        return str(user_ref)

    def _admin_recipient_ids(self) -> List[int]:
        return admin_recipient_ids(self.settings)

    def _resolve_log_chat_id(self) -> Optional[int]:
        if not self.settings.LOG_CHAT_ID:
            return None
        if self.id_bridge and self.id_bridge.enabled:
            try:
                return self.id_bridge.resolve_chat_reference(self.settings.LOG_CHAT_ID)
            except ValueError as exc:
                logging.error(f"Invalid LOG_CHAT_ID reference: {exc}")
                return None
        try:
            return int(self.settings.LOG_CHAT_ID)
        except (TypeError, ValueError):
            logging.error(f"Invalid LOG_CHAT_ID value: {self.settings.LOG_CHAT_ID}")
            return None
    
    async def _send_to_log_channel(self, message: str, thread_id: Optional[int] = None):
        """Send message to configured log channel/group using message queue"""
        chat_id = self._resolve_log_chat_id()
        if not chat_id:
            return
        
        queue_manager = get_queue_manager()
        if not queue_manager:
            logging.warning("Message queue manager not available, falling back to direct send")
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    message_thread_id=thread_id or self.settings.LOG_THREAD_ID
                )
            except Exception as e:
                logging.error(f"Failed to send notification to log channel {self.settings.LOG_CHAT_ID}: {e}")
            return
        
        try:
            # Use thread_id if provided, otherwise use from settings
            final_thread_id = thread_id or self.settings.LOG_THREAD_ID
            
            kwargs = {
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            if reply_markup:
                kwargs["reply_markup"] = reply_markup
            
            # Add thread ID for supergroups if specified
            if final_thread_id:
                kwargs["message_thread_id"] = final_thread_id
            
            # Queue message for sending (groups are rate limited to 15/minute)
            await queue_manager.send_message(chat_id, **kwargs)
            
        except Exception as e:
            logging.error(f"Failed to queue notification to log channel {chat_id}: {e}")
    
    async def _send_to_admins(self, message: str):
        """Send message to all admin users using message queue"""
        admin_targets = self._admin_recipient_ids()
        if not admin_targets:
            return
        
        queue_manager = get_queue_manager()
        if not queue_manager:
            logging.warning("Message queue manager not available, falling back to direct send")
            for admin_id in admin_targets:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logging.error(f"Failed to send notification to admin {admin_id}: {e}")
            return
        
        for admin_id in admin_targets:
            try:
                await queue_manager.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception as e:
                logging.error(f"Failed to queue notification to admin {admin_id}: {e}")
    
    async def notify_new_user_registration(self, user_id: int, username: Optional[str] = None, 
                                         first_name: Optional[str] = None, 
                                         referred_by_id: Optional[int] = None):
        """Send notification about new user registration"""
        if not self.settings.LOG_NEW_USERS:
            return
        
        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k
        
        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
            first_name=first_name,
        )
        
        referral_text = ""
        if referred_by_id:
            referrer_link = hd.link(str(referred_by_id), f"tg://user?id={referred_by_id}")
            referral_text = _(
                "log_referral_suffix",
                default=" (реферал от {referrer_link})",
                referrer_link=referrer_link,
            )
        
        message = _(
            "log_new_user_registration",
            default="👤 <b>Новый пользователь</b>\n\n"
                   "🆔 ID: <code>{user_id}</code>\n"
                   "👤 Имя: {user_display}{referral_text}\n"
                   "📅 Время: {timestamp}",
            user_id=user_id,
            user_display=user_display,
            referral_text=referral_text,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id, referred_by_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)
    
    async def notify_payment_received(self, user_id: int, amount: float, currency: str,
                                    months: int, payment_provider: str, 
                                    username: Optional[str] = None):
        """Send notification about successful payment"""
        if not self.settings.LOG_PAYMENTS:
            return
        
        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k
        
        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
        )
        
        provider_emoji = {
            "yookassa": "💳",
            "freekassa": "💳",
            "cryptopay": "₿",
            "stars": "⭐",
            "tribute": "💎"
        }.get(payment_provider.lower(), "💰")
        
        message = _(
            "log_payment_received",
            default="{provider_emoji} <b>Получен платеж</b>\n\n"
                   "👤 Пользователь: {user_display}\n"
                   "💰 Сумма: <b>{amount} {currency}</b>\n"
                   "📅 Период: <b>{months} мес.</b>\n"
                   "🏦 Провайдер: {payment_provider}\n"
                   "🕐 Время: {timestamp}",
            provider_emoji=provider_emoji,
            user_display=user_display,
            amount=amount,
            currency=currency,
            months=months,
            payment_provider=payment_provider,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)
    
    async def notify_promo_activation(self, user_id: int, promo_code: str, bonus_days: int,
                                    username: Optional[str] = None):
        """Send notification about promo code activation"""
        if not self.settings.LOG_PROMO_ACTIVATIONS:
            return
        
        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k
        
        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
        )
        
        message = _(
            "log_promo_activation",
            default="🎁 <b>Активирован промокод</b>\n\n"
                   "👤 Пользователь: {user_display}\n"
                   "🏷 Код: <code>{promo_code}</code>\n"
                   "🎯 Бонус: <b>+{bonus_days} дн.</b>\n"
                   "🕐 Время: {timestamp}",
            user_display=user_display,
            promo_code=promo_code,
            bonus_days=bonus_days,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)
    
    async def notify_trial_activation(self, user_id: int, end_date: datetime,
                                    username: Optional[str] = None):
        """Send notification about trial activation"""
        if not self.settings.LOG_TRIAL_ACTIVATIONS:
            return
        
        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k
        
        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
        )
        
        message = _(
            "log_trial_activation",
            default="🆓 <b>Активирован триал</b>\n\n"
                   "👤 Пользователь: {user_display}\n"
                   "⏰ Действует до: <b>{end_date}</b>\n"
                   "🕐 Время: {timestamp}",
            user_display=user_display,
            end_date=end_date.strftime("%Y-%m-%d %H:%M"),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)

    async def notify_panel_sync(self, status: str, details: str, 
                               users_processed: int, subs_synced: int,
                               username: Optional[str] = None):
        """Send notification about panel synchronization"""
        if not getattr(self.settings, 'LOG_PANEL_SYNC', True):
            return
        
        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(admin_lang, k, **kw) if self.i18n else k
        
        # Status emoji based on sync result
        status_emoji = {
            "completed": "✅",
            "completed_with_errors": "⚠️", 
            "failed": "❌"
        }.get(status, "🔄")
        
        message = _(
            "log_panel_sync",
            default="{status_emoji} <b>Синхронизация с панелью</b>\n\n"
                   "📊 Статус: <b>{status}</b>\n"
                   "👥 Обработано пользователей: <b>{users_processed}</b>\n"
                   "📋 Синхронизировано подписок: <b>{subs_synced}</b>\n"
                   "🕐 Время: {timestamp}\n\n"
                   "📝 Детали:\n{details}",
            status_emoji=status_emoji,
            status=status,
            users_processed=users_processed,
            subs_synced=subs_synced,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"),
            details=details
        )
        
        # Send to log channel 
        await self._send_to_log_channel(message)

    async def notify_suspicious_promo_attempt(
            self, user_id: int, suspicious_input: str,
            username: Optional[str] = None, first_name: Optional[str] = None):
        """Send notification about a suspicious promo code attempt."""
        if not self.settings.LOG_SUSPICIOUS_ACTIVITY:
            return

        admin_lang = self.settings.DEFAULT_LANGUAGE
        _ = lambda k, **kw: self.i18n.gettext(
            admin_lang, k, **kw) if self.i18n else k

        user_display = self._format_user_display(
            user_id=user_id,
            username=username,
            first_name=first_name,
        )

        message = _(
            "log_suspicious_promo",
            default="⚠️ <b>Подозрительная попытка ввода промокода</b>\n\n"
            "👤 Пользователь: {user_display}\n"
            "🆔 ID: <code>{user_id}</code>\n"
            "📝 Ввод: <pre>{suspicious_input}</pre>\n"
            "🕐 Время: {timestamp}",
            user_display=hd.quote(user_display),
            user_id=user_id,
            suspicious_input=hd.quote(suspicious_input),
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z"))

        # Send to log channel
        profile_keyboard = self._build_profile_keyboard(_, user_id)
        await self._send_to_log_channel(message, reply_markup=profile_keyboard)
    
    async def send_custom_notification(self, message: str, to_admins: bool = False, 
                                     to_log_channel: bool = True, thread_id: Optional[int] = None):
        """Send custom notification message"""
        if to_log_channel:
            await self._send_to_log_channel(message, thread_id)
        if to_admins:
            await self._send_to_admins(message)

# Removed legacy helper functions that duplicated NotificationService API
