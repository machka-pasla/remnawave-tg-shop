import logging
from typing import Callable, Dict, Any, Awaitable, Optional, Union

from aiogram import BaseMiddleware, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    User,
    Update,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
)
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramBadRequest, AiogramError

from config.settings import Settings
from db.dal import user_dal

from .i18n import JsonI18n
from ..keyboards.inline.user_keyboards import get_user_banned_keyboard


class BanCheckMiddleware(BaseMiddleware):

    def __init__(self, settings: Settings, i18n_instance: JsonI18n):
        super().__init__()
        self.settings = settings
        self.i18n_main_instance = i18n_instance

    async def __call__(self, handler: Callable[[Update, Dict[str, Any]],
                                               Awaitable[Any]], event: Update,
                       data: Dict[str, Any]) -> Any:
        session: AsyncSession = data["session"]
        event_user: Optional[User] = data.get("event_from_user")
        bot_instance: Bot = data["bot"]

        if not event_user:
            return await handler(event, data)

        if event_user.id in self.settings.ADMIN_IDS:
            return await handler(event, data)

        try:
            db_user_model = await user_dal.get_user_by_id(
                session, event_user.id)
        except Exception as e_db:
            logging.error(
                f"BanCheckMiddleware: DB error fetching user {event_user.id}: {e_db}",
                exc_info=True)
            return await handler(event, data)

        if db_user_model and db_user_model.is_banned:
            logging.info(
                f"User {event_user.id} ({event_user.username or 'NoUsername'}) is banned. Blocking access."
            )

            i18n_data_from_event = data.get("i18n_data", {})
            current_lang = i18n_data_from_event.get(
                "current_language", self.settings.DEFAULT_LANGUAGE)
            i18n_to_use: Optional[JsonI18n] = i18n_data_from_event.get(
                "i18n_instance", self.i18n_main_instance)

            ban_message_text = "You are banned. Please contact support."
            keyboard: Optional[InlineKeyboardMarkup] = None

            if i18n_to_use:
                _ = lambda k, **kw: i18n_to_use.gettext(current_lang, k, **kw)
                ban_message_text = _("user_is_banned")
                keyboard = get_user_banned_keyboard(self.settings.SUPPORT_LINK,
                                                    current_lang, i18n_to_use)
            elif self.settings.SUPPORT_LINK:
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                builder = InlineKeyboardBuilder()
                builder.button(text="Support", url=self.settings.SUPPORT_LINK)
                keyboard = builder.as_markup()

            actual_event_object: Optional[Union[Message, CallbackQuery]] = None
            if event.message: actual_event_object = event.message
            elif event.callback_query:
                actual_event_object = event.callback_query

            try:
                if isinstance(actual_event_object, Message):
                    await actual_event_object.answer(
                        ban_message_text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    )
                elif isinstance(actual_event_object, CallbackQuery):
                    await actual_event_object.answer(ban_message_text,
                                                     show_alert=True)
                    if actual_event_object.message:
                        try:
                            await actual_event_object.message.edit_text(
                                ban_message_text,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                link_preview_options=LinkPreviewOptions(is_disabled=True),
                            )
                        except (TelegramAPIError, AiogramError):
                            await bot_instance.send_message(
                                actual_event_object.from_user.id,
                                ban_message_text,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                link_preview_options=LinkPreviewOptions(is_disabled=True),
                            )
                    else:
                        await bot_instance.send_message(
                            actual_event_object.from_user.id,
                            ban_message_text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            link_preview_options=LinkPreviewOptions(is_disabled=True),
                        )
                else:
                    await bot_instance.send_message(event_user.id,
                                                    ban_message_text,
                                                    reply_markup=keyboard,
                                                    parse_mode="HTML",
                                                    link_preview_options=LinkPreviewOptions(is_disabled=True))
                logging.info(f"Ban notification sent to user {event_user.id}.")
            except TelegramForbiddenError:
                logging.warning(
                    f"BanCheck: Bot is blocked by user {event_user.id}.")
            except Exception as e_send:
                logging.error(
                    f"BanCheck: Failed to notify banned user {event_user.id}: {type(e_send).__name__} - {e_send}",
                    exc_info=True)

            return
        return await handler(event, data)
