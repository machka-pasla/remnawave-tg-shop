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
# 1. ENTER CREATE PROMO FLOW
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
# 2. CHOOSE PROMO TYPE (discount / bonus days)
# -----------------------------------------------------------------------------

@router.callback_query(F.data.startswith("promo_type:"), AdminStates.promo_waiting_type)
async def promo_choose_type(callback: types.CallbackQuery, state: FSMContext):
    promo_type = callback.data.split(":")[1]  # discount / bonus

    await state.update_data(promo_type=promo_type)

    if promo_type == "discount":
        text = "Введите размер скидки в процентах (например: 10):"
    else:
        text = "Введите количество бонусных дней (например: 7):"

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_admin_menu_keyboard()
    )
    await state.set_state(AdminStates.promo_waiting_value)
    await callback.answer()


# -----------------------------------------------------------------------------
# 3. ENTER VALUE: percent OR bonus_days
# -----------------------------------------------------------------------------

@router.message(AdminStates.promo_waiting_value)
async def promo_enter_value(message: types.Message, state: FSMContext, session):
    data = await state.get_data()
    promo_type = data["promo_type"]

    # Validate number
    try:
        value = int(message.text.strip())
        if value <= 0:
            raise ValueError
    except Exception:
        return await message.answer("Введите корректное число > 0.")

    # Store value
    if promo_type == "discount":
        await state.update_data(discount_percent=value, bonus_days=None)
    else:
        await state.update_data(discount_percent=None, bonus_days=value)

    await message.answer(
        "Введите максимальное количество активаций (например: 100):",
        reply_markup=get_back_to_admin_menu_keyboard()
    )

    await state.set_state(AdminStates.promo_waiting_limit)


# -----------------------------------------------------------------------------
# 4. ENTER MAX ACTIVATIONS
# -----------------------------------------------------------------------------

@router.message(AdminStates.promo_waiting_limit)
async def promo_enter_limit(message: types.Message, state: FSMContext):
    try:
        limit = int(message.text.strip())
        if limit <= 0:
            raise ValueError
    except:
        return await message.answer("Введите корректное число (>0).")

    await state.update_data(max_activations=limit)

    await message.answer(
        "Введите срок действия промокода в днях (например: 30):",
        reply_markup=get_back_to_admin_menu_keyboard()
    )

    await state.set_state(AdminStates.promo_waiting_expire)


# -----------------------------------------------------------------------------
# 5. ENTER EXPIRATION DAYS
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
# 6. ENTER PROMO CODE TEXT
# -----------------------------------------------------------------------------

@router.message(AdminStates.promo_waiting_code)
async def promo_enter_code(message: types.Message, state: FSMContext, session):
    code_raw = message.text.strip().upper()

    # Validate length
    if len(code_raw) < 3:
        return await message.answer("Минимальная длина промокода — 3 символа.")

    # Check if exists
    existing = await promo_code_dal.get_promo_code_by_code(session, code_raw)
    if existing:
        return await message.answer("Такой промокод уже существует, выберите другой.")

    data = await state.get_data()

    # BUILD CORRECT PAYLOAD FOR DAL
    promo_data = {
        "code": code_raw,
        "promo_type": data["promo_type"],
        "discount_percent": data.get("discount_percent"),
        "bonus_days": data.get("bonus_days"),
        "max_activations": data["max_activations"],
        "current_activations": 0,
        "valid_until": data["valid_until"],
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }

    new_promo = await promo_code_dal.create_promo_code(session, promo_data)
    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ Промокод создан!\n\n"
        f"Код: <b>{new_promo.code}</b>\n"
        f"Тип: {new_promo.promo_type}\n"
        f"Скидка: {new_promo.discount_percent}%\n"
        f"Бонус дней: {new_promo.bonus_days}\n"
        f"Макс. активаций: {new_promo.max_activations}\n"
        f"Действует до: {new_promo.valid_until.strftime('%Y-%m-%d')}",
        parse_mode="HTML",
        reply_markup=get_back_to_admin_menu_keyboard()
    )