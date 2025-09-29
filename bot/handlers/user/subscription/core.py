import logging
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from typing import Optional, Union
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config.settings import Settings
from bot.keyboards.inline.user_keyboards import (
    get_subscription_options_keyboard,
    get_back_to_main_menu_markup,
    get_autorenew_confirm_keyboard,
)
from bot.services.subscription_service import SubscriptionService
from bot.services.panel_api_service import PanelApiService
from bot.middlewares.i18n import JsonI18n
from db.dal import subscription_dal
from db.models import Subscription

router = Router(name="user_subscription_core_router")


async def display_subscription_options(event: Union[types.Message, types.CallbackQuery], i18n_data: dict, settings: Settings, session: AsyncSession):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")

    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    if not i18n:
        err_msg = "Language service error."
        if isinstance(event, types.CallbackQuery):
            try:
                await event.answer(err_msg, show_alert=True)
            except Exception:
                pass
        elif isinstance(event, types.Message):
            await event.answer(err_msg)
        return

    currency_symbol_val = settings.DEFAULT_CURRENCY_SYMBOL
    text_content = get_text("select_subscription_period") if settings.subscription_options else get_text("no_subscription_options_available")

    reply_markup = (
        get_subscription_options_keyboard(settings.subscription_options, currency_symbol_val, current_lang, i18n)
        if settings.subscription_options
        else get_back_to_main_menu_markup(current_lang, i18n)
    )

    target_message_obj = event.message if isinstance(event, types.CallbackQuery) else event
    if not target_message_obj:
        if isinstance(event, types.CallbackQuery):
            try:
                await event.answer(get_text("error_occurred_try_again"), show_alert=True)
            except Exception:
                pass
        return

    if isinstance(event, types.CallbackQuery):
        try:
            await target_message_obj.edit_text(text_content, reply_markup=reply_markup)
        except Exception:
            await target_message_obj.answer(text_content, reply_markup=reply_markup)
        try:
            await event.answer()
        except Exception:
            pass
    else:
        await target_message_obj.answer(text_content, reply_markup=reply_markup)


@router.callback_query(F.data == "main_action:subscribe")
async def reshow_subscription_options_callback(callback: types.CallbackQuery, i18n_data: dict, settings: Settings, session: AsyncSession):
    await display_subscription_options(callback, i18n_data, settings, session)


async def my_subscription_command_handler(
    event: Union[types.Message, types.CallbackQuery],
    i18n_data: dict,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    bot: Bot,
):
    target = event.message if isinstance(event, types.CallbackQuery) else event
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data.get("i18n_instance")
    get_text = lambda key, **kw: i18n.gettext(current_lang, key, **kw)

    if not i18n or not target:
        if isinstance(event, types.Message):
            await event.answer(get_text("error_occurred_try_again"))
        return

    if not panel_service or not subscription_service:
        await target.answer(get_text("error_service_unavailable"))
        return

    active = await subscription_service.get_active_subscription_details(session, event.from_user.id)

    if not active:
        text = get_text("subscription_not_active")

        buy_button = InlineKeyboardButton(
            text=get_text("menu_subscribe_inline", default="Купить"), callback_data="main_action:subscribe"
        )
        back_markup = get_back_to_main_menu_markup(current_lang, i18n)

        kb = InlineKeyboardMarkup(inline_keyboard=[[buy_button], *back_markup.inline_keyboard])

        if isinstance(event, types.CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
            try:
                await event.message.edit_text(text, reply_markup=kb)
            except Exception:
                await event.message.answer(text, reply_markup=kb)
        else:
            await event.answer(text, reply_markup=kb)
        return

    end_date = active.get("end_date")
    days_left = (end_date.date() - datetime.now().date()).days if end_date else 0
    tribute_hint = ""
    if active.get("status_from_panel", "").lower() == "active":
        local_sub = await subscription_dal.get_active_subscription_by_user_id(session, event.from_user.id)
        if local_sub:
            if local_sub.provider == "tribute":
                link = None
                link = settings.tribute_payment_links.get(local_sub.duration_months or 1) if hasattr(settings, "tribute_payment_links") else None
                tribute_hint = "\n\n" + (
                    get_text("subscription_tribute_notice_with_link", link=link) if link else get_text("subscription_tribute_notice")
                )

    text = get_text(
        "my_subscription_details",
        end_date=end_date.strftime("%Y-%m-%d") if end_date else "N/A",
        days_left=max(0, days_left),
        status=active.get("status_from_panel", get_text("status_active")).capitalize(),
        config_link=active.get("config_link") or get_text("config_link_not_available"),
        traffic_limit=(f"{active['traffic_limit_bytes'] / 2**30:.2f} GB" if active.get("traffic_limit_bytes") else get_text("traffic_unlimited")),
        traffic_used=(
            f"{active['traffic_used_bytes'] / 2**30:.2f} GB" if active.get("traffic_used_bytes") is not None else get_text("traffic_na")
        ),
    )

    base_markup = get_back_to_main_menu_markup(current_lang, i18n)
    kb = base_markup.inline_keyboard
    try:
        local_sub = await subscription_dal.get_active_subscription_by_user_id(session, event.from_user.id)
        # Build rows to prepend above the base "back" markup
        prepend_rows = []

        # 1) Mini-app connect button on top if enabled, otherwise fall back to config link URL
        if settings.SUBSCRIPTION_MINI_APP_URL:
            prepend_rows.append([
                InlineKeyboardButton(
                    text=get_text("connect_button"),
                    web_app=WebAppInfo(url=settings.SUBSCRIPTION_MINI_APP_URL),
                )
            ])
        else:
            cfg_link_val = (active or {}).get("config_link")
            if cfg_link_val:
                prepend_rows.append([
                    InlineKeyboardButton(
                        text=get_text("connect_button"),
                        url=cfg_link_val,
                    )
                ])

        # 2) Auto-renew toggle (if supported and not tribute)
        if local_sub and local_sub.provider != "tribute" and getattr(settings, 'YOOKASSA_AUTOPAYMENTS_ENABLED', False):
            toggle_text = (
                get_text("autorenew_disable_button") if local_sub.auto_renew_enabled else get_text("autorenew_enable_button")
            )
            prepend_rows.append([
                InlineKeyboardButton(
                    text=toggle_text,
                    callback_data=f"toggle_autorenew:{local_sub.subscription_id}:{1 if not local_sub.auto_renew_enabled else 0}",
                )
            ])

        # 3) Payment methods management (when autopayments enabled)
        if getattr(settings, 'YOOKASSA_AUTOPAYMENTS_ENABLED', False):
            prepend_rows.append([
                InlineKeyboardButton(text=get_text("payment_methods_manage_button"), callback_data="pm:manage")
            ])

        if prepend_rows:
            kb = prepend_rows + kb
    except Exception:
        pass
    markup = InlineKeyboardMarkup(inline_keyboard=kb)

    if isinstance(event, types.CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
        try:
            await event.message.edit_text(text + tribute_hint, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            await bot.send_message(
                chat_id=target.chat.id,
                text=text + tribute_hint,
                reply_markup=markup,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
    else:
        await target.answer(text + tribute_hint, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)


@router.callback_query(F.data.startswith("toggle_autorenew:"))
async def toggle_autorenew_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    try:
        _, payload = callback.data.split(":", 1)
        sub_id_str, enable_str = payload.split(":")
        sub_id = int(sub_id_str)
        enable = bool(int(enable_str))
    except Exception:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    sub = await session.get(Subscription, sub_id)
    if not sub or sub.user_id != callback.from_user.id:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    if sub.provider == "tribute":
        await callback.answer(get_text("subscription_autorenew_not_supported_for_tribute"), show_alert=True)
        return

    # Show confirmation popup and inline buttons
    confirm_text = get_text("autorenew_confirm_enable") if enable else get_text("autorenew_confirm_disable")
    kb = get_autorenew_confirm_keyboard(enable, sub.subscription_id, current_lang, i18n)
    try:
        await callback.message.edit_text(confirm_text, reply_markup=kb)
    except Exception:
        try:
            await callback.message.answer(confirm_text, reply_markup=kb)
        except Exception:
            pass
    try:
        await callback.answer()
    except Exception:
        pass
    return


@router.callback_query(F.data.startswith("autorenew:confirm:"))
async def confirm_autorenew_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    try:
        _, _, sub_id_str, enable_str = callback.data.split(":", 3)
        sub_id = int(sub_id_str)
        enable = bool(int(enable_str))
    except Exception:
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    sub = await session.get(Subscription, sub_id)
    if not sub or sub.user_id != callback.from_user.id:
        await callback.answer(get_text("error_try_again"), show_alert=True)
        return
    if sub.provider == "tribute":
        await callback.answer(get_text("subscription_autorenew_not_supported_for_tribute"), show_alert=True)
        return

    await subscription_dal.update_subscription(session, sub.subscription_id, {"auto_renew_enabled": enable})
    await session.commit()
    try:
        await callback.answer(get_text("subscription_autorenew_updated"))
    except Exception:
        pass
    await my_subscription_command_handler(callback, i18n_data, settings, panel_service, subscription_service, session, bot)


@router.callback_query(F.data == "autorenew:cancel")
async def autorenew_cancel_from_webhook_button(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    subscription_service: SubscriptionService,
    panel_service: PanelApiService,
    bot: Bot,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    # Disable auto-renew on the active subscription (non-tribute)
    from db.dal import subscription_dal
    sub = await subscription_dal.get_active_subscription_by_user_id(session, callback.from_user.id)
    if not sub:
        try:
            await callback.answer(get_text("subscription_not_active"), show_alert=True)
        except Exception:
            pass
        return
    if sub.provider == "tribute":
        try:
            await callback.answer(get_text("subscription_autorenew_not_supported_for_tribute"), show_alert=True)
        except Exception:
            pass
        return
    await subscription_dal.update_subscription(session, sub.subscription_id, {"auto_renew_enabled": False})
    await session.commit()
    try:
        await callback.answer(get_text("subscription_autorenew_updated"))
    except Exception:
        pass
    await my_subscription_command_handler(callback, i18n_data, settings, panel_service, subscription_service, session, bot)


@router.message(Command("connect"))
async def connect_command_handler(
    message: types.Message,
    i18n_data: dict,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    session: AsyncSession,
    bot: Bot,
):
    logging.info(f"User {message.from_user.id} used /connect command.")
    await my_subscription_command_handler(message, i18n_data, settings, panel_service, subscription_service, session, bot)


