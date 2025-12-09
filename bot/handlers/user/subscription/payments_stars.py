import logging
from typing import Optional

from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.stars_service import StarsService
from config.settings import Settings

router = Router(name="user_subscription_payments_stars_router")


@router.callback_query(F.data.startswith("pay_stars:"))
async def pay_stars_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    stars_service: StarsService,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    get_text = (lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key)

    if not i18n or not callback.message:
        try:
            await callback.answer(get_text("error_occurred_try_again"), show_alert=True)
        except Exception:
            pass
        return

    if not settings.STARS_ENABLED:
        try:
            await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
        except Exception:
            pass
        return

    try:
        _, data_payload = callback.data.split(":", 1)
        months_str, stars_price_str = data_payload.split(":")
        months = int(months_str)
        stars_price = int(stars_price_str)
    except (ValueError, IndexError):
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    user_id = callback.from_user.id
    payment_description = get_text("payment_description_subscription", months=months)

    payment_db_id = await stars_service.create_invoice(
        session=session,
        user_id=user_id,
        months=months,
        stars_price=stars_price,
        description=payment_description,
    )

    if payment_db_id:
        try:
            await callback.message.edit_text(
                get_text("payment_invoice_sent_message", months=months),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=get_text("back_to_payment_methods_button"),
                        callback_data=f"subscribe_period:{months}",
                    )]
                ]),
            )
        except Exception as e_edit:
            logging.warning(f"Stars payment: failed to show invoice info message ({e_edit})")
        try:
            await callback.answer()
        except Exception:
            pass
        return

    try:
        await callback.answer(get_text("error_payment_gateway"), show_alert=True)
    except Exception:
        pass


@router.pre_checkout_query()
async def handle_pre_checkout_query(query: types.PreCheckoutQuery):
    try:
        await query.answer(ok=True)
    except Exception:
        # Nothing else to do here; Telegram will show an error if not answered
        pass


@router.message(F.successful_payment)
async def handle_successful_stars_payment(
    message: types.Message,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    stars_service: StarsService,
):
    payload = (message.successful_payment.invoice_payload
               if message and message.successful_payment else "")
    try:
        payment_db_id_str, months_str = (payload or "").split(":", 1)
        payment_db_id = int(payment_db_id_str)
        months = int(months_str)
    except Exception:
        return

    stars_amount = int(message.successful_payment.total_amount) if message.successful_payment else 0
    await stars_service.process_successful_payment(
        session=session,
        message=message,
        payment_db_id=payment_db_id,
        months=months,
        stars_amount=stars_amount,
        i18n_data=i18n_data,
    )
