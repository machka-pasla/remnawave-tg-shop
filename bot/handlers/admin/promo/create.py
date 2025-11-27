import logging
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.admin_states import AdminStates
from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import promo_code_dal
from bot.keyboards.inline.admin_keyboards import get_back_to_admin_panel_keyboard

router = Router(name="promo_create_router")

# -------------------------------
# 1) ПЕРВЫЙ ЭТАП — запросить тип
# -------------------------------
@router.callback_query(F.data == "admin_action:create_promo")
async def create_promo_prompt_handler(callback: types.CallbackQuery,
                                      state: FSMContext,
                                      i18n_data: dict,
                                      settings: Settings,
                                      session: AsyncSession):
    i18n = i18n_data.get("i18n_instance")
    lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)

    await state.set_state(AdminStates.promo_waiting_type)

    text = i18n.gettext(lang, "admin_promo_create_step1",
                        default="Выберите тип промокода:")

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(
                text="💸 Скидка", callback_data="promo_type:discount"),
            types.InlineKeyboardButton(
                text="🎁 Бонус дни", callback_data="promo_type:bonus")
        ],
        [types.InlineKeyboardButton(
            text="⬅️ Назад", callback_data="admin_action:main")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


# -------------------------------
# 2) Выбор типа промокода
# -------------------------------
@router.callback_query(F.data.startswith("promo_type:"))
async def promo_type_selected(callback: types.CallbackQuery,
                              state: FSMContext,
                              i18n_data: dict,
                              settings: Settings,
                              session: AsyncSession):

    promo_type = callback.data.split(":")[1]
    await state.update_data(promo_type=promo_type)
    await state.set_state(AdminStates.promo_waiting_code)

    i18n = i18n_data.get("i18n_instance")
    lang = i18n_data.get("current_language")

    text = i18n.gettext(lang,
                        "admin_promo_create_step2",
                        default="Введите код промокода (только латиница и цифры):")

    await callback.message.edit_text(text)
    await callback.answer()


# -------------------------------
# 3) Ввод кода
# -------------------------------
@router.message(AdminStates.promo_waiting_code)
async def promo_enter_code(message: types.Message,
                           state: FSMContext,
                           settings: Settings,
                           i18n_data: dict):
    code = message.text.strip().upper()

    if not code.isalnum():
        await message.answer("❌ Код должен содержать только буквы/цифры.")
        return

    await state.update_data(code=code)
    await state.set_state(AdminStates.promo_waiting_value)

    await message.answer("Введите % скидки или количество бонусных дней:")


# -------------------------------
# 4) Ввод значения
# -------------------------------
@router.message(AdminStates.promo_waiting_value)
async def promo_enter_value(message: types.Message,
                            state: FSMContext,
                            settings: Settings,
                            session: AsyncSession,
                            i18n_data: dict):

    data = await state.get_data()
    promo_type = data["promo_type"]
    code = data["code"]

    try:
        value = int(message.text.strip())
    except:
        await message.answer("Введите целое число.")
        return

    if value <= 0:
        await message.answer("Число должно быть больше нуля.")
        return

    # Создаём промокод
    if promo_type == "discount":
        new_promo = await promo_code_dal.create_promo_code(
            session,
            code=code,
            discount_percent=value,
            bonus_days=None,
            created_by_admin_id=message.from_user.id
        )
    else:
        new_promo = await promo_code_dal.create_promo_code(
            session,
            code=code,
            bonus_days=value,
            discount_percent=None,
            created_by_admin_id=message.from_user.id
        )

    await session.commit()
    await state.clear()

    await message.answer(
        f"🎉 Промокод <b>{code}</b> создан!",
        reply_markup=get_back_to_admin_panel_keyboard(
            i18n_data["current_language"], i18n_data["i18n_instance"]),
        parse_mode="HTML"
    )