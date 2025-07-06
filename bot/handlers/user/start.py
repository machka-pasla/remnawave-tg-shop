import logging
from aiogram import Router, F, types, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from typing import Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from db.dal import user_dal

from bot.keyboards.inline.user_keyboards import get_main_menu_inline_keyboard, get_language_selection_keyboard
from bot.services.subscription_service import SubscriptionService
from bot.services.panel_api_service import PanelApiService
from bot.services.referral_service import ReferralService
from bot.services.promo_code_service import PromoCodeService
from config.settings import Settings
from bot.middlewares.i18n import JsonI18n

router = Router(name="user_start_router")


async def send_main_menu(target_event: Union[types.Message,
                                             types.CallbackQuery],
                         settings: Settings,
                         i18n_data: dict,
                         subscription_service: SubscriptionService,
                         session: AsyncSession,
                         is_edit: bool = False):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")

    user_id = target_event.from_user.id
    user_full_name = target_event.from_user.full_name

    if not i18n:
        logging.error(
            f"i18n_instance missing in send_main_menu for user {user_id}")
        err_msg_fallback = "Error: Language service unavailable. Please try again later."
        if isinstance(target_event, types.CallbackQuery):
            try:
                await target_event.answer(err_msg_fallback, show_alert=True)
            except Exception:
                pass
        elif isinstance(target_event, types.Message) and hasattr(
                target_event, 'chat') and target_event.chat:
            try:
                await target_event.chat.send_message(err_msg_fallback)
            except Exception:
                pass
        return

    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    show_trial_button_in_menu = False
    if settings.TRIAL_ENABLED:
        if hasattr(
                subscription_service, 'has_had_any_subscription') and callable(
                    getattr(subscription_service, 'has_had_any_subscription')):
            if not await subscription_service.has_had_any_subscription(
                    session, user_id):
                show_trial_button_in_menu = True
        else:
            logging.error(
                "Method has_had_any_subscription is missing in SubscriptionService for send_main_menu!"
            )

    text = _(key="main_menu_greeting", user_name=user_full_name)
    reply_markup = get_main_menu_inline_keyboard(current_lang, i18n, settings,
                                                 show_trial_button_in_menu)

    target_message_obj: Optional[types.Message] = None
    if isinstance(target_event, types.Message):
        target_message_obj = target_event
    elif isinstance(target_event,
                    types.CallbackQuery) and target_event.message:
        target_message_obj = target_event.message

    if not target_message_obj:
        logging.error(
            f"send_main_menu: target_message_obj is None for event from user {user_id}."
        )
        if isinstance(target_event, types.CallbackQuery):
            await target_event.answer(_("error_displaying_menu"),
                                      show_alert=True)
        return

    try:
        if is_edit:
            await target_message_obj.edit_text(text, reply_markup=reply_markup)
        else:
            await target_message_obj.answer(text, reply_markup=reply_markup)

        if isinstance(target_event, types.CallbackQuery):
            await target_event.answer()
    except Exception as e_send_edit:
        logging.warning(
            f"Failed to send/edit main menu (user: {user_id}, is_edit: {is_edit}): {type(e_send_edit).__name__} - {e_send_edit}."
        )
        if is_edit and target_message_obj and hasattr(
                target_message_obj, 'chat') and target_message_obj.chat:
            try:
                await target_message_obj.chat.send_message(
                    text, reply_markup=reply_markup)
            except Exception as e_send_new:
                logging.error(
                    f"Also failed to send new main menu message for user {user_id}: {e_send_new}"
                )
        if isinstance(target_event, types.CallbackQuery):
            await target_event.answer(
                _("error_occurred_try_again") if is_edit else None)


@router.message(CommandStart())
async def start_command_handler(message: types.Message,
                                state: FSMContext,
                                settings: Settings,
                                i18n_data: dict,
                                subscription_service: SubscriptionService,
                                session: AsyncSession,
                                command: Optional[CommandStart] = None):
    await state.clear()
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs
                                           ) if i18n else key

    user = message.from_user
    user_id = user.id

    referred_by_user_id: Optional[int] = None
    if command and command.args:
        arg_payload = command.args
        if arg_payload.startswith("ref_"):
            try:
                potential_referrer_id_str = arg_payload.split("_")[1]
                if potential_referrer_id_str.isdigit():
                    potential_referrer_id = int(potential_referrer_id_str)
                    if potential_referrer_id != user_id:
                        referred_by_user_id = potential_referrer_id
            except (IndexError, ValueError) as e:
                logging.warning(
                    f"Could not parse referral from /start args '{arg_payload}': {e}"
                )

    db_user = await user_dal.get_user_by_id(session, user_id)
    if not db_user:
        user_data_to_create = {
            "user_id": user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "language_code": current_lang,
            "referred_by_id": referred_by_user_id,
            "registration_date": datetime.now(timezone.utc)
        }
        try:
            db_user = await user_dal.create_user(session, user_data_to_create)

            logging.info(
                f"New user {user_id} added to session. Referred by: {referred_by_user_id or 'N/A'}."
            )
        except Exception as e_create:

            logging.error(
                f"Failed to add new user {user_id} to session: {e_create}",
                exc_info=True)
            await message.answer(_("error_occurred_processing_request"))
            return
    else:
        update_payload = {}
        if db_user.language_code != current_lang:
            update_payload["language_code"] = current_lang
        if referred_by_user_id and db_user.referred_by_id is None:
            update_payload["referred_by_id"] = referred_by_user_id
        if user.username != db_user.username:
            update_payload["username"] = user.username
        if user.first_name != db_user.first_name:
            update_payload["first_name"] = user.first_name
        if user.last_name != db_user.last_name:
            update_payload["last_name"] = user.last_name

        if update_payload:
            try:
                await user_dal.update_user(session, user_id, update_payload)

                logging.info(
                    f"Updated existing user {user_id} in session: {update_payload}"
                )
            except Exception as e_update:

                logging.error(
                    f"Failed to update existing user {user_id} in session: {e_update}",
                    exc_info=True)

    await message.answer(_(key="welcome", user_name=user.full_name))
    await send_main_menu(message,
                         settings,
                         i18n_data,
                         subscription_service,
                         session,
                         is_edit=False)


@router.message(Command("language"))
@router.callback_query(F.data == "main_action:language")
async def language_command_handler(
    event: Union[types.Message, types.CallbackQuery],
    i18n_data: dict,
    settings: Settings,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs
                                           ) if i18n else key

    text_to_send = _(key="choose_language")
    reply_markup = get_language_selection_keyboard(i18n, current_lang)

    target_message_obj = event.message if isinstance(
        event, types.CallbackQuery) else event
    if not target_message_obj:
        if isinstance(event, types.CallbackQuery):
            await event.answer(_("error_occurred_try_again"), show_alert=True)
        return

    if isinstance(event, types.CallbackQuery):
        if event.message:
            try:
                await event.message.edit_text(text_to_send,
                                              reply_markup=reply_markup)
            except Exception:
                await target_message_obj.answer(text_to_send,
                                                reply_markup=reply_markup)
        await event.answer()
    else:
        await target_message_obj.answer(text_to_send,
                                        reply_markup=reply_markup)


@router.callback_query(F.data.startswith("set_lang_"))
async def select_language_callback_handler(
        callback: types.CallbackQuery, i18n_data: dict, settings: Settings,
        subscription_service: SubscriptionService, session: AsyncSession):
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Service error or message context lost.",
                              show_alert=True)
        return

    try:
        lang_code = callback.data.split("_")[2]
    except IndexError:
        await callback.answer("Error processing language selection.",
                              show_alert=True)
        return

    user_id = callback.from_user.id
    try:
        updated = await user_dal.update_user_language(session, user_id,
                                                      lang_code)
        if updated:

            i18n_data["current_language"] = lang_code
            _ = lambda key, **kwargs: i18n.gettext(lang_code, key, **kwargs)
            await callback.answer(_(key="language_set_alert"))
            logging.info(
                f"User {user_id} language updated to {lang_code} in session.")
        else:
            await callback.answer("Could not set language.", show_alert=True)
            return
    except Exception as e_lang_update:

        logging.error(
            f"Error updating lang for user {user_id}: {e_lang_update}",
            exc_info=True)
        await callback.answer("Error setting language.", show_alert=True)
        return
    await send_main_menu(callback,
                         settings,
                         i18n_data,
                         subscription_service,
                         session,
                         is_edit=True)


@router.callback_query(F.data.startswith("main_action:"))
async def main_action_callback_handler(
        callback: types.CallbackQuery, state: FSMContext, settings: Settings,
        i18n_data: dict, bot: Bot, subscription_service: SubscriptionService,
        referral_service: ReferralService, panel_service: PanelApiService,
        promo_code_service: PromoCodeService, session: AsyncSession):
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id

    from . import subscription as user_subscription_handlers
    from . import referral as user_referral_handlers
    from . import promo_user as user_promo_handlers
    from . import trial_handler as user_trial_handlers

    if not callback.message:
        await callback.answer("Error: message context lost.", show_alert=True)
        return

    if action == "subscribe":
        await user_subscription_handlers.display_subscription_options(
            callback, i18n_data, settings, session)
    elif action == "my_subscription":

        await user_subscription_handlers.my_subscription_command_handler(
            callback, i18n_data, settings, panel_service, subscription_service,
            session, bot)
    elif action == "referral":
        await user_referral_handlers.referral_command_handler(
            callback, settings, i18n_data, referral_service, bot, session)
    elif action == "apply_promo":
        await user_promo_handlers.prompt_promo_code_input(
            callback, state, i18n_data, settings, session)
    elif action == "request_trial":
        await user_trial_handlers.request_trial_confirmation_handler(
            callback, settings, i18n_data, subscription_service, session)
    elif action == "language":

        await language_command_handler(callback, i18n_data, settings)
    elif action == "autorenew":
        await user_subscription_handlers.autorenew_menu_callback(
            callback,
            i18n_data,
            settings,
            subscription_service,
            session,
        )
    elif action == "back_to_main":
        await send_main_menu(callback,
                             settings,
                             i18n_data,
                             subscription_service,
                             session,
                             is_edit=True)
    else:
        i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
        _ = lambda key, **kwargs: i18n.gettext(
            i18n_data.get("current_language"), key, **kwargs) if i18n else key
        await callback.answer(_("main_menu_unknown_action"), show_alert=True)
