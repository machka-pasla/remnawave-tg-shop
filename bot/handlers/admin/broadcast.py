import logging
import asyncio
from aiogram import Router, F, types, Bot
from aiogram.exceptions import TelegramRetryAfter

from aiogram.fsm.context import FSMContext
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings

from db.dal import user_dal, message_log_dal

from bot.states.admin_states import AdminStates
from bot.keyboards.inline.admin_keyboards import (
    get_broadcast_confirmation_keyboard,
    get_back_to_admin_panel_keyboard,
    get_admin_panel_keyboard,
)
from bot.middlewares.i18n import JsonI18n

router = Router(name="admin_broadcast_router")


async def broadcast_message_prompt_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n:
        logging.error("i18n missing in broadcast_message_prompt_handler")
        await callback.answer("Language service error.", show_alert=True)
        return

    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)
    prompt_text = _("admin_broadcast_enter_message")

    if callback.message:
        try:
            await callback.message.edit_text(
                prompt_text,
                reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            )
        except Exception as e:
            logging.warning(
                f"Could not edit message for broadcast prompt: {e}. Sending new."
            )
            await callback.message.answer(
                prompt_text,
                reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            )
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_broadcast_message)


@router.message(AdminStates.waiting_for_broadcast_message, F.text)
async def process_broadcast_message_handler(
    message: types.Message,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n:
        logging.error("i18n missing in process_broadcast_message_handler")
        await message.reply("Language service error.")
        return

    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    # Сохраняем в state исходный текст и entities
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []

    await state.update_data(
        broadcast_text=text,
        broadcast_entities=entities,
    )

    preview_snippet = (text[:200] + "...") if len(text) > 200 else text
    confirmation_prompt = _("admin_broadcast_confirm_prompt", message_preview=preview_snippet)

    await message.answer(
        confirmation_prompt,
        reply_markup=get_broadcast_confirmation_keyboard(current_lang, i18n),
    )
    await state.set_state(AdminStates.confirming_broadcast)


@router.callback_query(
    F.data == "admin_action:main", AdminStates.waiting_for_broadcast_message
)
async def cancel_broadcast_at_prompt_stage(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error cancelling.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        await callback.message.edit_text(
            _("admin_broadcast_cancelled_nav_back"), reply_markup=None
        )
    except Exception:
        await callback.message.answer(_("admin_broadcast_cancelled_nav_back"))

    await callback.answer(_("admin_broadcast_cancelled_alert"))
    await state.clear()

    await callback.message.answer(
        _(key="admin_panel_title"),
        reply_markup=get_admin_panel_keyboard(i18n, current_lang, settings),
    )


@router.callback_query(
    F.data.startswith("broadcast_final_action:"),
    AdminStates.confirming_broadcast,
)
async def confirm_broadcast_callback_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error processing broadcast confirmation.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    action = callback.data.split(":")[1]
    user_fsm_data = await state.get_data()

    if action == "send":
        text = user_fsm_data.get("broadcast_text")
        entities = user_fsm_data.get("broadcast_entities", [])

        if not text:
            await callback.message.edit_text(_("admin_broadcast_error_no_message"))
            await state.clear()
            await callback.answer(
                _("admin_broadcast_error_no_message_alert"), show_alert=True
            )
            return

        await callback.message.edit_text(_("admin_broadcast_sending_started"), reply_markup=None)
        await callback.answer()

        user_ids = await user_dal.get_all_active_user_ids_for_broadcast(session)

        sent_count = 0
        failed_count = 0
        admin_user = callback.from_user
        logging.info(
            f"Admin {admin_user.id} broadcasting '{text[:50]}...' to {len(user_ids)} users."
        )

        for uid in user_ids:
            try:
                await bot.send_message(
                    chat_id=uid,
                    text=text,
                    entities=entities,
                )
                sent_count += 1

                await message_log_dal.create_message_log(
                    session,
                    {
                        "user_id": admin_user.id,
                        "telegram_username": admin_user.username,
                        "telegram_first_name": admin_user.first_name,
                        "event_type": "admin_broadcast_sent",
                        "content": f"To user {uid}: {text[:70]}...",
                        "is_admin_event": True,
                        "target_user_id": uid,
                    },
                )
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                failed_count += 1
                logging.warning(
                    f"RetryAfter sending to {uid}: {e.retry_after}s"
                )
                await message_log_dal.create_message_log(
                    session,
                    {
                        "user_id": admin_user.id,
                        "telegram_username": admin_user.username,
                        "telegram_first_name": admin_user.first_name,
                        "event_type": "admin_broadcast_failed",
                        "content": f"For user {uid}: RetryAfter {e.retry_after}s",
                        "is_admin_event": True,
                        "target_user_id": uid,
                    },
                )
            except Exception as e:
                failed_count += 1
                logging.warning(
                    f"Failed to send broadcast to {uid}: {type(e).__name__} – {e}"
                )
                await message_log_dal.create_message_log(
                    session,
                    {
                        "user_id": admin_user.id,
                        "telegram_username": admin_user.username,
                        "telegram_first_name": admin_user.first_name,
                        "event_type": "admin_broadcast_failed",
                        "content": f"For user {uid}: {type(e).__name__} – {str(e)[:70]}...",
                        "is_admin_event": True,
                        "target_user_id": uid,
                    },
                )
            await asyncio.sleep(2.1 if uid < 0 else 0.05)

        try:
            await session.commit()
        except Exception as e_commit:
            await session.rollback()
            logging.error(f"Error committing broadcast logs: {e_commit}")

        result_message = _("admin_broadcast_finished_stats", sent_count=sent_count, failed_count=failed_count)
        await callback.message.answer(
            result_message,
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
        )

    elif action == "cancel":
        await callback.message.edit_text(
            _("admin_broadcast_cancelled"),
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
        )
        await callback.answer()

    await state.clear()
