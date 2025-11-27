import logging
import re
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.utils.markdown import hcode

from config.settings import Settings
from bot.states.user_states import UserPromoStates
from bot.services.promo_code_service import PromoCodeService
from bot.services.subscription_service import SubscriptionService
from bot.keyboards.inline.user_keyboards import (
    get_back_to_main_menu_markup,
    get_connect_and_main_keyboard,
)
from datetime import datetime
from bot.middlewares.i18n import JsonI18n

from .start import send_main_menu

router = Router(name="user_promo_router")

SUSPICIOUS_SQL_KEYWORDS_REGEX = re.compile(
    r"\b(DROP\s*TABLE|DELETE\s*FROM|ALTER\s*TABLE|TRUNCATE\s*TABLE|UNION\s*SELECT|"
    r";\s*SELECT|;\s*INSERT|;\s*UPDATE|;\s*DELETE|xp_cmdshell|sysdatabases|sysobjects|INFORMATION_SCHEMA)\b",
    re.IGNORECASE)
SUSPICIOUS_CHARS_REGEX = re.compile(r"(--|#\s|;|\*\/|\/\*)")
MAX_PROMO_CODE_INPUT_LENGTH = 100


# ================================
# ПРЕДЛОЖИТЬ ВВОД ПРОМОКОДА
# ================================
async def prompt_promo_code_input(callback: types.CallbackQuery,
                                  state: FSMContext, i18n_data: dict,
                                  settings: Settings, session: AsyncSession):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n:
        await callback.answer("Language service error.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        await callback.message.edit_text(
            text=_(key="promo_code_prompt"),
            reply_markup=get_back_to_main_menu_markup(current_lang, i18n)
        )
    except:
        await callback.message.answer(
            text=_(key="promo_code_prompt"),
            reply_markup=get_back_to_main_menu_markup(current_lang, i18n)
        )

    await callback.answer()
    await state.set_state(UserPromoStates.waiting_for_promo_code)
    logging.info(f"User {callback.from_user.id} → waiting_for_promo_code")


# ================================
# ОБРАБОТКА ВВЕДЁННОГО ПРОМОКОДА
# ================================
@router.message(UserPromoStates.waiting_for_promo_code, F.text)
async def process_promo_code_input(message: types.Message, state: FSMContext,
                                   settings: Settings, i18n_data: dict,
                                   promo_code_service: PromoCodeService,
                                   subscription_service: SubscriptionService,
                                   bot: Bot, session: AsyncSession):

    user = message.from_user
    code_input = (message.text or "").strip()

    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n = i18n_data["i18n_instance"]
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    # ===========================
    # АНТИ-ИНЪЕКЦИОННАЯ ЗАЩИТА
    # ===========================
    is_suspicious = (
        not code_input
        or len(code_input) > MAX_PROMO_CODE_INPUT_LENGTH
        or SUSPICIOUS_SQL_KEYWORDS_REGEX.search(code_input)
        or SUSPICIOUS_CHARS_REGEX.search(code_input)
    )

    if is_suspicious:
        # уведомляем админов
        if settings.LOG_SUSPICIOUS_ACTIVITY:
            from bot.services.notification_service import NotificationService
            try:
                n = NotificationService(bot, settings, i18n)
                await n.notify_suspicious_promo_attempt(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    suspicious_input=code_input
                )
            except Exception as e:
                logging.error(f"Suspicious promo notify fail: {e}")

        await message.answer(
            _("promo_code_not_found", code=hcode(code_input.upper())),
            reply_markup=get_back_to_main_menu_markup(current_lang, i18n),
            parse_mode="HTML"
        )
        await state.clear()
        return

    # ===========================
    # ПРИМЕНЕНИЕ ПРОМОКОДА
    # ===========================
    success, result = await promo_code_service.apply_promo_code(
        session, user.id, code_input, current_lang
    )

    # --- УСПЕХ ---
    if success:
        await session.commit()
        logging.info(f"Promo '{code_input}' applied for user={user.id}")

        # === CASE 1: BONUS DAYS ===
        if isinstance(result, datetime):
            new_end_date = result
            active = await subscription_service.get_active_subscription_details(session, user.id)
            config_link = active.get("config_link") if active else None
            config_link = config_link or _("config_link_not_available")

            await message.answer(
                _("promo_code_applied_success_full",
                  end_date=new_end_date.strftime("%d.%m.%Y %H:%M:%S"),
                  config_link=config_link),
                reply_markup=get_connect_and_main_keyboard(
                    current_lang, i18n, settings, config_link),
                parse_mode="HTML"
            )
            await state.clear()
            return

        # === CASE 2: DISCOUNT PROMO ===
        if isinstance(result, dict) and result.get("type") == "discount":
            # сохраняем скидку в FSM
            await state.update_data(active_discount=result)

            # сообщение пользователю
            if result.get("discount_percent"):
                discount_text = f"−{result['discount_percent']}%"
            else:
                discount_text = f"Только для тарифа {result['discount_plan_months']} мес."

            await message.answer(
                f"🎉 {_('promo_discount_applied', default='Promo code applied!')}\n"
                f"Скидка: <b>{discount_text}</b>\n\n"
                f"Она будет рассчитана при выборе тарифа.",
                reply_markup=get_back_to_main_menu_markup(current_lang, i18n),
                parse_mode="HTML",
            )
            await state.clear()
            return

        # неизвестный формат — fallback
        await message.answer(
            _("error_applying_promo_bonus"),
            reply_markup=get_back_to_main_menu_markup(current_lang, i18n)
        )
        await state.clear()
        return

    # --- ОШИБКА ---
    await session.rollback()
    logging.info(f"Promo failed for user={user.id}: {result}")

    await message.answer(
        result,
        reply_markup=get_back_to_main_menu_markup(current_lang, i18n),
        parse_mode="HTML"
    )
    await state.clear()


# ================================
# КНОПКА "Назад" ВО ВРЕМЯ ВВОДА
# ================================
@router.callback_query(F.data == "main_action:back_to_main",
                       UserPromoStates.waiting_for_promo_code)
async def cancel_promo_input_via_button(callback: types.CallbackQuery,
                                        state: FSMContext, settings: Settings,
                                        i18n_data: dict,
                                        subscription_service: SubscriptionService,
                                        session: AsyncSession):

    i18n: JsonI18n = i18n_data["i18n_instance"]
    current_lang = i18n_data["current_language"]

    await state.clear()
    logging.info(f"Promo input cancelled by user {callback.from_user.id}")

    await send_main_menu(
        callback,
        settings,
        i18n_data,
        subscription_service,
        session,
        is_edit=True
    )