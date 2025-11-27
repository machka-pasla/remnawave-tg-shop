import logging
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.admin_states import AdminStates
from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import promo_code_dal

router = Router(name="promo_bulk_router")

# -----------------------------------
# 1) Запуск массового создания
# -----------------------------------
@router.callback_query(F.data == "admin_action:create_bulk_promo")
async def create_bulk_promo_prompt_handler(callback: types.CallbackQuery,
                                           state: FSMContext,
                                           i18n_data: dict,
                                           settings: Settings,
                                           session: AsyncSession):
    i18n = i18n_data["i18n_instance"]
    lang = i18n_data["current_language"]

    await state.set_state(AdminStates.bulk_promo_waiting_input)

    text = i18n.gettext(
        lang,
        "admin_promo_bulk_step1",
        default="Введите список промокодов.\n\nФормат:\n<код> <значение>\n\nПример:\nSUMMER10 10\nWEEKEND 7\nVIP100 100"
    )

    await callback.message.edit_text(text)
    await callback.answer()


# -----------------------------------
# 2) Принимаем много строк
# -----------------------------------
@router.message(AdminStates.bulk_promo_waiting_input)
async def bulk_promo_process(message: types.Message,
                             state: FSMContext,
                             settings: Settings,
                             session: AsyncSession,
                             i18n_data: dict):

    lines = message.text.strip().split("\n")
    created = 0
    failed = 0

    for line in lines:
        parts = line.split()
        if len(parts) != 2:
            failed += 1
            continue

        code, val_str = parts
        code = code.upper()

        if not code.isalnum():
            failed += 1
            continue

        try:
            value = int(val_str)
        except:
            failed += 1
            continue

        try:
            await promo_code_dal.create_promo_code(
                session,
                code=code,
                discount_percent=value,
                bonus_days=None,
                created_by_admin_id=message.from_user.id
            )
            created += 1
        except Exception:
            failed += 1
            continue

    await session.commit()
    await state.clear()

    await message.answer(f"Готово!\nСоздано: {created}\nОшибки: {failed}")