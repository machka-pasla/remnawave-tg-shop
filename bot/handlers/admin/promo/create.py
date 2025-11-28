import logging
from datetime import datetime, timezone, timedelta
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext

from bot.states.admin_states import AdminStates
from bot.keyboards.inline.admin_keyboards import (
    get_promo_type_keyboard,
    get_back_to_admin_menu_keyboard,
)
from db.dal import promo_code_dal

router = Router()

# -----------------------------------------------------------------------------
# 1. START PROMO CREATION
# -----------------------------------------------------------------------------

@router.callback_query(F.data == "admin_action:create_promo")
async def create_promo_start(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите тип промокода:",
        reply_markup=get_promo_type_keyboard()
    )
    await state.set_state(AdminStates.promo_waiting_type)
    await callback.answer()

# -----------------------------------------------------------------------------
# 2. CHOOSE PROMO TYPE
# -----------------------------------------------------------------------------

@router.callback_query(F.data.startswith("promo_type:"), AdminStates.promo_waiting_type)
async def promo_choose_type(callback: types.CallbackQuery, state: FSMContext):
    promo_type = callback.data.split(":")[1]  # discount_all / discount_plan / bonus
    await state.update_data(promo_type=promo_type)

    if promo_type in ("discount_all", "discount_plan"):
        text = "Введите размер скидки в процентах (например: 10):"
    else:
        text = "Введите количество бонусных дней (например: 7):"

    await callback.message.edit_text(text)
    await state.set_state(AdminStates.promo_waiting_value)
    await callback.answer()

# -----------------------------------------------------------------------------
# 3. ENTER VALUE (PERCENT OR BONUS DAYS)
# -----------------------------------------------------------------------------

@router.message(AdminStates.promo_waiting_value)
async def promo_enter_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    promo_type = data["promo_type"]

    try:
        value = int(message.text.strip())
        if value <= 0:
            raise ValueError
    except:
        return await message.answer("Введите корректное число > 0.")

    if promo_type in ("discount_all", "discount_plan"):
        await state.update_data(discount_percent=value, bonus_days=None)

        if promo_type == "discount_plan":
            await message.answer(
                "Для какого тарифа действует промокод?\n"
                "Введите 1, 3, 6 или 12."
            )
            await state.set_state(AdminStates.promo_waiting_plan_months)
            return

        await message.answer("Введите максимальное количество активаций:")
        await state.set_state(AdminStates.promo_waiting_max_activations)
        return

    else:
        await state.update_data(discount_percent=None, bonus_days=value)
        await message.answer("Введите максимальное количество активаций:")
        await state.set_state(AdminStates.promo_waiting_max_activations)

# -----------------------------------------------------------------------------
# 4. ENTER PLAN MONTHS (IF discount_plan)
# -----------------------------------------------------------------------------

@router.message(AdminStates.promo_waiting_plan_months)
async def promo_enter_plan_months(message: types.Message, state: FSMContext):
    try:
        months = int(message.text.strip())
        if months not in (1, 3, 6, 12):
            raise ValueError
    except:
        return await message.answer("Введите одно из значений: 1, 3, 6 или 12.")

    await state.update_data(discount_plan_months=months)

    await message.answer("Введите максимальное количество активаций:")
    await state.set_state(AdminStates.promo_waiting_max_activations)

# -----------------------------------------------------------------------------
# 5. ENTER MAX ACTIVATIONS
# -----------------------------------------------------------------------------

@router.message(AdminStates.promo_waiting_max_activations)
async def promo_enter_max(message: types.Message, state: FSMContext):
    try:
        max_act = int(message.text.strip())
        if max_act <= 0:
            raise ValueError
    except:
        return await message.answer("Введите корректное число (>0).")

    await state.update_data(max_activations=max_act)

    await message.answer(
        "Введите срок действия промокода в днях:",
        reply_markup=get_back_to_admin_menu_keyboard()
    )
    await state.set_state(AdminStates.promo_waiting_expire)

# -----------------------------------------------------------------------------
# 6. ENTER EXPIRATION DAYS
# -----------------------------------------------------------------------------

@router.message(AdminStates.promo_waiting_expire)
async def promo_enter_expire(message: types.Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except:
        return await message.answer("Введите корректное число (>0).")

    expire_date = datetime.now(timezone.utc) + timedelta(days=days)
    await state.update_data(valid_until=expire_date)

    await message.answer(
        "Введите текст промокода (например: SUPER2024):",
        reply_markup=get_back_to_admin_menu_keyboard()
    )

    await state.set_state(AdminStates.promo_waiting_code)

# -----------------------------------------------------------------------------
# 7. ENTER PROMO CODE AND CREATE
# -----------------------------------------------------------------------------

@router.message(AdminStates.promo_waiting_code)
async def promo_enter_code(message: types.Message, state: FSMContext, session):
    code_raw = message.text.strip().upper()

    if len(code_raw) < 3:
        return await message.answer("Минимальная длина — 3 символа.")

    existing = await promo_code_dal.get_promo_code_by_code(session, code_raw)
    if existing:
        return await message.answer("Такой промокод уже существует.")

    data = await state.get_data()

    promo_data = {
        "code": code_raw,
        "discount_percent": data.get("discount_percent"),
        "discount_plan_months": data.get("discount_plan_months"),
        "bonus_days": data.get("bonus_days"),
        "max_activations": data["max_activations"],
        "current_activations": 0,
        "valid_until": data["valid_until"],
        "is_active": True,
        "created_by_admin_id": message.from_user.id,
    }

    new_promo = await promo_code_dal.create_promo_code(session, promo_data)

    promo_type = data["promo_type"]
    if promo_type == "bonus":
        type_text = "Бонусные дни"
    elif promo_type == "discount_all":
        type_text = f"Скидка {data.get('discount_percent')}% на все тарифы"
    elif promo_type == "discount_plan":
        type_text = (
            f"Скидка {data.get('discount_percent')}% "
            f"на тариф {data.get('discount_plan_months')} мес"
        )
    else:
        type_text = "Неизвестный тип"

    await message.answer(
        f"✅ Промокод создан!\n\n"
        f"Код: <b>{new_promo.code}</b>\n"
        f"Тип: {type_text}\n"
        f"Макс. активаций: {new_promo.max_activations}\n"
        f"Действует до: {new_promo.valid_until.strftime('%Y-%m-%d')}",
        parse_mode="HTML",
        reply_markup=get_back_to_admin_menu_keyboard(),
    )