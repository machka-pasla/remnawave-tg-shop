import random
import string
from datetime import datetime, timedelta, timezone

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import promo_code_dal
from bot.states.admin_states import AdminStates
from bot.keyboards.inline.admin_keyboards import (
    get_back_to_admin_panel_keyboard,
    promo_type_choice_kb,
    promo_plan_choice_kb,
)

router = Router()


# ---------- Utils ----------
def generate_code(length=10):
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


# ---------- Step 1: ask quantity ----------
@router.message(F.text, AdminStates.waiting_for_bulk_promo_quantity)
async def bulk_quantity(message: Message, state: FSMContext):
    try:
        quantity = int(message.text.strip())
        if quantity <= 0:
            raise ValueError
    except ValueError:
        return await message.answer(
            "Введите число — сколько промокодов нужно создать.",
            reply_markup=get_back_to_admin_panel_keyboard("ru", None)
        )

    await state.update_data(quantity=quantity)

    await state.set_state(AdminStates.waiting_for_bulk_promo_type)
    await message.answer(
        "Выберите тип создаваемых промокодов:",
        reply_markup=promo_type_choice_kb()
    )


# ---------- Step 2: choose promo type ----------
@router.callback_query(F.data.startswith("promo_type_"), AdminStates.waiting_for_bulk_promo_type)
async def bulk_type_choice(callback: CallbackQuery, state: FSMContext):

    promo_type = callback.data.replace("promo_type_", "")
    await state.update_data(promo_type=promo_type)

    if promo_type == "bonus":
        await callback.message.edit_text("Введите количество бонусных дней:")
        await state.set_state(AdminStates.waiting_for_bulk_promo_bonus_days)
        return

    await callback.message.edit_text(
        "Введите процент скидки (1–99):",
        reply_markup=get_back_to_admin_panel_keyboard("ru", None)
    )
    await state.set_state(AdminStates.waiting_for_bulk_promo_discount_percent)


# ---------- Step 3A: bonus_days ----------
@router.message(F.text, AdminStates.waiting_for_bulk_promo_bonus_days)
async def bulk_bonus_days(message: Message, state: FSMContext):

    try:
        days = int(message.text.strip())
        if days < 1:
            raise ValueError
    except ValueError:
        return await message.answer(
            "Введите корректное количество дней.",
            reply_markup=get_back_to_admin_panel_keyboard("ru", None)
        )

    await state.update_data(bonus_days=days)

    await message.answer(
        "Введите максимальное количество активаций:",
        reply_markup=get_back_to_admin_panel_keyboard("ru", None)
    )
    await state.set_state(AdminStates.waiting_for_bulk_promo_max_activations)


# ---------- Step 3B: discount_percent ----------
@router.message(F.text, AdminStates.waiting_for_bulk_promo_discount_percent)
async def bulk_discount_percent(message: Message, state: FSMContext):

    try:
        discount = int(message.text.strip())
        if discount < 1 or discount > 99:
            raise ValueError
    except ValueError:
        return await message.answer(
            "Введите число от 1 до 99.",
            reply_markup=get_back_to_admin_panel_keyboard("ru", None)
        )

    await state.update_data(discount_percent=discount)

    await message.answer(
        "На какой тариф действует скидка?",
        reply_markup=promo_plan_choice_kb()
    )
    await state.set_state(AdminStates.waiting_for_bulk_promo_plan_months)


# ---------- Step 4: discount_plan_months ----------
@router.callback_query(F.data.startswith("promo_plan_"), AdminStates.waiting_for_bulk_promo_plan_months)
async def bulk_plan_choice(callback: CallbackQuery, state: FSMContext):

    plan = callback.data.replace("promo_plan_", "")

    if plan == "all":
        plan_months = None
    else:
        plan_months = int(plan)

    await state.update_data(discount_plan_months=plan_months)

    await callback.message.edit_text(
        "Введите максимальное количество активаций:",
        reply_markup=get_back_to_admin_panel_keyboard("ru", None)
    )
    await state.set_state(AdminStates.waiting_for_bulk_promo_max_activations)


# ---------- Step 5: max activations ----------
@router.message(F.text, AdminStates.waiting_for_bulk_promo_max_activations)
async def bulk_max_activations(message: Message, state: FSMContext):
    try:
        max_acts = int(message.text.strip())
        if max_acts < 1:
            raise ValueError
    except ValueError:
        return await message.answer(
            "Введите корректное число (минимум 1).",
            reply_markup=get_back_to_admin_panel_keyboard("ru", None)
        )

    await state.update_data(max_activations=max_acts)

    await message.answer(
        "Введите срок действия промокодов (в днях):",
        reply_markup=get_back_to_admin_panel_keyboard("ru", None)
    )
    await state.set_state(AdminStates.waiting_for_bulk_promo_validity_days)


# ---------- Step 6: validity days ----------
@router.message(F.text, AdminStates.waiting_for_bulk_promo_validity_days)
async def bulk_validity(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):

    try:
        validity_days = int(message.text.strip())
        if validity_days < 1:
            raise ValueError
    except ValueError:
        return await message.answer(
            "Введите корректный срок (минимум 1 день).",
            reply_markup=get_back_to_admin_panel_keyboard("ru", None)
        )

    await state.update_data(validity_days=validity_days)

    data = await state.get_data()

    quantity = data["quantity"]
    promo_type = data["promo_type"]
    max_activations = data["max_activations"]

    bonus_days = data.get("bonus_days")
    discount_percent = data.get("discount_percent")
    discount_plan_months = data.get("discount_plan_months")
    validity_days = data["validity_days"]

    codes = []

    for _ in range(quantity):
        code = generate_code()

        promo_data = {
            "code": code,
            "max_activations": max_activations,
            "current_activations": 0,
            "is_active": True,
            "created_by_admin_id": message.from_user.id,
            "created_at": datetime.now(timezone.utc),
            "valid_until": datetime.now(timezone.utc) + timedelta(days=validity_days)
        }

        if promo_type == "bonus":
            promo_data["bonus_days"] = bonus_days
            promo_data["discount_percent"] = None
            promo_data["discount_plan_months"] = None
        else:
            promo_data["bonus_days"] = None
            promo_data["discount_percent"] = discount_percent
            promo_data["discount_plan_months"] = discount_plan_months

        await promo_code_dal.create_promo_code(session, promo_data)

        codes.append(code)

    await session.commit()

    text = (
        f"Создано {quantity} промокодов.\n\nПервые 20:\n" +
        "\n".join(codes[:20])
    )

    await message.answer(text, reply_markup=get_back_to_admin_panel_keyboard("ru", None))
    await state.clear()