import logging
from aiogram import Router, F, types, Bot
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from config.settings import Settings
from bot.services.subscription_service import SubscriptionService
from bot.services.panel_api_service import PanelApiService
from bot.keyboards.inline.user_keyboards import (
    get_trial_confirmation_keyboard,
    get_main_menu_inline_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from .start import send_main_menu

router = Router(name="user_trial_router")


async def request_trial_confirmation_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
):
    user_id = callback.from_user.id
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    if not i18n or not callback.message:
        await callback.answer(_("error_occurred_try_again"), show_alert=True)
        return

    show_trial_btn_in_menu_if_fail = False
    if settings.TRIAL_ENABLED:
        if not await subscription_service.has_had_any_subscription(session, user_id):
            show_trial_btn_in_menu_if_fail = True

    if not settings.TRIAL_ENABLED:
        await callback.message.edit_text(
            _("trial_feature_disabled"),
            reply_markup=get_main_menu_inline_keyboard(
                current_lang, i18n, settings, False
            ),
        )
        await callback.answer()
        return

    if await subscription_service.has_had_any_subscription(session, user_id):
        await callback.message.edit_text(
            _("trial_already_had_subscription_or_trial"),
            reply_markup=get_main_menu_inline_keyboard(
                current_lang, i18n, settings, False
            ),
        )
        await callback.answer()
        return

    traffic_gb_display = (
        str(settings.TRIAL_TRAFFIC_LIMIT_GB)
        if settings.TRIAL_TRAFFIC_LIMIT_GB and settings.TRIAL_TRAFFIC_LIMIT_GB > 0
        else _("traffic_unlimited")
    )

    await callback.message.edit_text(
        text=_(
            "trial_confirm_prompt",
            days=settings.TRIAL_DURATION_DAYS,
            traffic_gb=traffic_gb_display,
        ),
        reply_markup=get_trial_confirmation_keyboard(current_lang, i18n),
    )
    await callback.answer()


@router.callback_query(F.data == "trial_action:confirm_activate")
async def confirm_activate_trial_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    session: AsyncSession,
):
    user_id = callback.from_user.id

    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    if not i18n or not callback.message:
        await callback.answer(_("error_occurred_try_again"), show_alert=True)
        return

    if not settings.TRIAL_ENABLED:
        await callback.answer(_("trial_feature_disabled"), show_alert=True)

        await send_main_menu(
            callback, settings, i18n_data, subscription_service, session, is_edit=True
        )
        return
    if await subscription_service.has_had_any_subscription(session, user_id):
        await callback.answer(
            _("trial_already_had_subscription_or_trial"), show_alert=True
        )
        await send_main_menu(
            callback, settings, i18n_data, subscription_service, session, is_edit=True
        )
        return

    activation_result = await subscription_service.activate_trial_subscription(
        session, user_id
    )

    final_message_text_in_chat = ""
    show_trial_button_after_action = False

    if activation_result and activation_result.get("activated"):
        await callback.answer(_("trial_activated_alert"), show_alert=True)

        end_date_obj = activation_result.get("end_date")
        config_link_for_trial = activation_result.get("subscription_url") or _(
            "config_link_not_available"
        )

        traffic_gb_val = activation_result.get(
            "traffic_gb", settings.TRIAL_TRAFFIC_LIMIT_GB
        )
        traffic_display = (
            f"{traffic_gb_val} GB"
            if traffic_gb_val and traffic_gb_val > 0
            else _("traffic_unlimited")
        )

        final_message_text_in_chat = _(
            "trial_activated_details_message",
            days=activation_result.get("days", settings.TRIAL_DURATION_DAYS),
            end_date=(
                end_date_obj.strftime("%Y-%m-%d")
                if isinstance(end_date_obj, datetime)
                else "N/A"
            ),
            config_link=config_link_for_trial,
            traffic_gb=traffic_display,
        )
    else:
        message_key_from_service = (
            activation_result.get("message_key", "trial_activation_failed")
            if activation_result
            else "trial_activation_failed"
        )
        final_message_text_in_chat = _(message_key_from_service)
        await callback.answer(final_message_text_in_chat, show_alert=True)
        if (
            settings.TRIAL_ENABLED
            and not await subscription_service.has_had_any_subscription(
                session, user_id
            )
        ):
            show_trial_button_after_action = True

    try:
        await callback.message.edit_text(
            final_message_text_in_chat,
            parse_mode="HTML",
            reply_markup=get_main_menu_inline_keyboard(
                current_lang, i18n, settings, show_trial_button_after_action
            ),
            disable_web_page_preview=True,
        )
    except Exception as e_edit:
        logging.warning(
            f"Could not edit trial result message: {e_edit}. Sending new one."
        )

        if (
            callback.message
            and hasattr(callback.message, "chat")
            and callback.message.chat
        ):
            await callback.message.chat.send_message(
                final_message_text_in_chat,
                parse_mode="HTML",
                reply_markup=get_main_menu_inline_keyboard(
                    current_lang, i18n, settings, show_trial_button_after_action
                ),
                disable_web_page_preview=True,
            )


@router.callback_query(F.data == "main_action:cancel_trial")
async def cancel_trial_activation(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    subscription_service: SubscriptionService,
    session: AsyncSession,
):
    await send_main_menu(
        callback, settings, i18n_data, subscription_service, session, is_edit=True
    )
