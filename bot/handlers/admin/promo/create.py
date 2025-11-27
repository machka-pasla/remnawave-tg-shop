import logging
from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.admin_states import AdminStates
from bot.keyboards.inline.admin_keyboards import get_back_to_admin_panel_keyboard
from bot.middlewares.i18n import JsonI18n
from bot.services.promo_code_service import promo_code_service

from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

router = Router(name="promo_create")


# ---------------------------------------------
# STEP 1 — REQUEST PROMO CODE
# ---------------------------------------------
@router.callback_query(F.data == "admin_action:create_promo")
async def admin_start_promo_creation(callback: types.CallbackQuery,
                                     state: FSMContext,
                                     i18n_data: dict):
    lang = i18n_data["current_language"]
    i18n: JsonI18n = i18n_data["i18n_instance"]
    _ = lambda key, **kw: i18n.gettext(lang, key, **kw)

    text = _("admin_promo_step1_code")

    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_back_to_admin_panel_keyboard(lang, i18n),
            parse_mode="HTML"
        )
    except:
        await callback.message.answer(
            text,
            reply_markup=get_back_to_admin_panel_keyboard(lang, i18n),
            parse_mode="HTML"
        )

    await state.set_state(AdminStates.waiting_for_promo_code)
    await callback.answer()


# ---------------------------------------------
# STEP 2 — ENTER PROMO CODE STRING
# ---------------------------------------------
@router.message(AdminStates.waiting_for_promo_code, F.text)
async def process_promo_code(message: types.Message,
                             state: FSMContext,
                             session: AsyncSession,
                             i18n_data: dict):
    lang = i18n_data["current_language"]
    i18n: JsonI18n = i18n_data["i18n_instance"]
    _ = lambda key, **kw: i18n.gettext(lang, key, **kw)

    code = message.text.strip().upper()

    if not (3 <= len(code) <= 30 and code.isalnum()):
        return await message.answer(_("admin_promo_invalid_code_format"))

    # check exists
    from db.dal.promo_code_dal import promo_code_dal
    exists = await promo_code_dal.get_promo_code_by_code(session, code)
    if exists:
        return await message.answer(_("admin_promo_code_already_exists"))

    await state.update_data(code=code)

    # ask promo type
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🎁 Бонусные дни", callback_data="promo_type:bonus"))
    kb.row(InlineKeyboardButton(text="💸 Скидка %", callback_data="promo_type:discount"))
    kb.row(InlineKeyboardButton(text="🗓 Скидка на тариф", callback_data="promo_type:plan"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_action:main"))

    await message.answer(
        _("admin_promo_choose_type", default="Выберите тип промокода:"),
        reply_markup=kb.as_markup()
    )

    await state.set_state(AdminStates.waiting_for_promo_type)


# ---------------------------------------------
# STEP 3 — PROMO TYPE SELECTED
# ---------------------------------------------
@router.callback_query(F.data.startswith("promo_type:"), StateFilter(AdminStates.waiting_for_promo_type))
async def promo_type_selected(callback: types.CallbackQuery,
                              state: FSMContext,
                              i18n_data: dict):
    lang = i18n_data["current_language"]
    i18n: JsonI18n = i18n_data["i18n_instance"]
    _ = lambda key, **kw: i18n.gettext(lang, key, **kw)

    promo_type = callback.data.split(":")[1]
    await state.update_data(promo_type=promo_type)

    if promo_type == "bonus":
        text = _("admin_promo_step2_bonus_days")
        await callback.message.edit_text(
            text,
            reply_markup=get_back_to_admin_panel_keyboard(lang, i18n),
            parse_mode="HTML"
        )
        await state.set_state(AdminStates.waiting_for_promo_bonus_days)

    elif promo_type == "discount":
        text = _("admin_promo_edit_discount_percent", default="Введите процент скидки (1–99):")
        await callback.message.edit_text(
            text,
            reply_markup=get_back_to_admin_panel_keyboard(lang, i18n)
        )
        await state.set_state(AdminStates.waiting_for_promo_discount_percent)

    elif promo_type == "plan":
        text = _("admin_promo_edit_discount_months", default="Введите количество месяцев тарифа (1/3/6/12):")
        await callback.message.edit_text(
            text,
            reply_markup=get_back_to_admin_panel_keyboard(lang, i18n)
        )
        await state.set_state(AdminStates.waiting_for_promo_plan_months)

    await callback.answer()


# BONUS DAYS
@router.message(AdminStates.waiting_for_promo_bonus_days, F.text)
async def bonus_days_step(message: types.Message,
                          state: FSMContext,
                          i18n_data: dict):
    lang = i18n_data["current_language"]
    i18n = i18n_data["i18n_instance"]
    _ = lambda key, **kw: i18n.gettext(lang, key, **kw)

    try:
        days = int(message.text.strip())
        if not (1 <= days <= 365):
            return await message.answer(_("admin_promo_invalid_bonus_days"))
        await state.update_data(bonus_days=days)
    except:
        return await message.answer(_("admin_promo_invalid_input"))

    await message.answer(_("admin_promo_step3_max_activations"))
    await state.set_state(AdminStates.waiting_for_promo_max_activations)


# DISCOUNT PERCENT
@router.message(AdminStates.waiting_for_promo_discount_percent, F.text)
async def discount_percent_step(message: types.Message,
                                state: FSMContext,
                                i18n_data: dict):
    lang = i18n_data["current_language"]
    i18n = i18n_data["i18n_instance"]
    _ = lambda key, **kw: i18n.gettext(lang, key, **kw)

    try:
        percent = int(message.text.strip())
        if not (1 <= percent <= 99):
            return await message.answer(_("admin_promo_invalid_input"))
        await state.update_data(discount_percent=percent)
    except:
        return await message.answer(_("admin_promo_invalid_input"))

    await message.answer(_("admin_promo_step3_max_activations"))
    await state.set_state(AdminStates.waiting_for_promo_max_activations)


# DISCOUNT PLAN MONTHS
@router.message(AdminStates.waiting_for_promo_plan_months, F.text)
async def discount_plan_months_step(message: types.Message,
                                    state: FSMContext,
                                    i18n_data: dict):
    lang = i18n_data["current_language"]
    i18n = i18n_data["i18n_instance"]
    _ = lambda key, **kw: i18n.gettext(lang, key, **kw)

    try:
        months = int(message.text.strip())
        if months not in (1, 3, 6, 12):
            return await message.answer(_("admin_promo_invalid_input"))
        await state.update_data(discount_plan_months=months)
    except:
        return await message.answer(_("admin_promo_invalid_input"))

    await message.answer(_("admin_promo_edit_discount_percent"))
    await state.set_state(AdminStates.waiting_for_promo_discount_percent)


# ---------------------------------------------
# MAX ACTIVATIONS
# ---------------------------------------------
@router.message(AdminStates.waiting_for_promo_max_activations, F.text)
async def max_activations_step(message: types.Message,
                               state: FSMContext,
                               i18n_data: dict):
    lang = i18n_data["current_language"]
    i18n = i18n_data["i18n_instance"]
    _ = lambda key, **kw: i18n.gettext(lang, key, **kw)

    try:
        maxa = int(message.text.strip())
        if not (1 <= maxa <= 10000):
            return await message.answer(_("admin_promo_invalid_max_activations"))
        await state.update_data(max_activations=maxa)
    except:
        return await message.answer(_("admin_promo_invalid_input"))

    # ask validity
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=_("admin_promo_unlimited_validity"), callback_data="validity:unlimit"))
    kb.row(InlineKeyboardButton(text=_("admin_promo_set_validity_days"), callback_data="validity:set"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_action:main"))

    await message.answer(_("admin_promo_step4_validity"), reply_markup=kb.as_markup())
    await state.set_state(AdminStates.waiting_for_promo_validity_days)


# ---------------------------------------------
# VALIDITY — UNLIMITED
# ---------------------------------------------
@router.callback_query(F.data == "validity:unlimit",
                       StateFilter(AdminStates.waiting_for_promo_validity_days))
async def promo_unlimited(callback: types.CallbackQuery,
                          state: FSMContext,
                          session: AsyncSession,
                          i18n_data: dict):
    await state.update_data(validity_days=None)
    await finalize_promo(callback, state, session, i18n_data)


# ---------------------------------------------
# VALIDITY — SET DAYS
# ---------------------------------------------
@router.callback_query(F.data == "validity:set",
                       StateFilter(AdminStates.waiting_for_promo_validity_days))
async def promo_enter_days(callback: types.CallbackQuery,
                           i18n_data: dict,
                           state: FSMContext):
    lang = i18n_data["current_language"]
    i18n = i18n_data["i18n_instance"]
    _ = lambda key, **kw: i18n.gettext(lang, key, **kw)

    await callback.message.edit_text(
        _("admin_promo_enter_validity_days"),
        reply_markup=get_back_to_admin_panel_keyboard(lang, i18n)
    )
    await state.set_state(AdminStates.waiting_for_promo_validity_days)
    await callback.answer()


@router.message(AdminStates.waiting_for_promo_validity_days, F.text)
async def promo_days_input(message: types.Message,
                           state: FSMContext,
                           session: AsyncSession,
                           i18n_data: dict):
    lang = i18n_data["current_language"]
    i18n = i18n_data["i18n_instance"]
    _ = lambda key, **kw: i18n.gettext(lang, key, **kw)

    try:
        days = int(message.text.strip())
        if not (1 <= days <= 365):
            return await message.answer(_("admin_promo_invalid_validity_days"))
        await state.update_data(validity_days=days)
    except:
        return await message.answer(_("admin_promo_invalid_input"))

    await finalize_promo(message, state, session, i18n_data)


# ---------------------------------------------
# FINAL CREATION
# ---------------------------------------------
async def finalize_promo(event,
                         state: FSMContext,
                         session: AsyncSession,
                         i18n_data: dict):
    lang = i18n_data["current_language"]
    i18n = i18n_data["i18n_instance"]
    _ = lambda key, **kw: i18n.gettext(lang, key, **kw)

    data = await state.get_data()

    promo_kwargs = {
        "code": data["code"],
        "max_activations": data["max_activations"],
        "valid_until": (
            datetime.now(timezone.utc) + timedelta(days=data["validity_days"])
            if data.get("validity_days") else None
        ),
        "created_by_admin_id": event.from_user.id
    }

    promo_type = data["promo_type"]
    if promo_type == "bonus":
        promo_kwargs["bonus_days"] = data["bonus_days"]
        promo_kwargs["discount_percent"] = None
        promo_kwargs["discount_plan_months"] = None
    elif promo_type == "discount":
        promo_kwargs["bonus_days"] = None
        promo_kwargs["discount_percent"] = data["discount_percent"]
        promo_kwargs["discount_plan_months"] = None
    else:  # discount on specific plan
        promo_kwargs["bonus_days"] = None
        promo_kwargs["discount_percent"] = data["discount_percent"]
        promo_kwargs["discount_plan_months"] = data["discount_plan_months"]

    try:
        created = await promo_code_service.create_promo_code(session, promo_kwargs)
        await session.commit()

        msg = _("admin_promo_created_success").format(
            code=created.code
        )

        await event.message.answer(
            msg,
            reply_markup=get_back_to_admin_panel_keyboard(lang, i18n),
            parse_mode="HTML"
        )

    except Exception as e:
        logging.exception("Promo creation failed")
        await event.message.answer(_("error_occurred_try_again"))

    await state.clear()