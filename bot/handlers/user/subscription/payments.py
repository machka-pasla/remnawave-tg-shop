import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal.payment_dal import create_payment_record
from bot.services.promo_code_service import PromoCodeService
from bot.services.yookassa_service import YooKassaService
from bot.services.freekassa_service import FreeKassaService
from bot.services.panel_api_service import PanelApiService
from bot.keyboards import user_keyboards

router = Router()


# ---------------------------------------------------------------------
#   INTERNAL UTILS
# ---------------------------------------------------------------------

def _parse_months_and_price(payload: str):
    """
    Example payload: 'months:3|price:490'
    """
    parts = payload.split("|")
    months = int(parts[0].split(":")[1])
    price = float(parts[1].split(":")[1])
    return months, price


async def _apply_promo_discount(
    session: AsyncSession,
    user_id: int,
    months: int,
    base_price: float,
    promo_code_service: PromoCodeService,
):
    """
    Возвращает (final_price, promo_obj_or_None, discount_info_str_or_None)
    """
    promo = await promo_code_service.get_active_promo(session, user_id)

    if not promo:
        return base_price, None, None

    final_price, discount_info = await promo_code_service.apply_promo_to_price(
        base_price=base_price,
        months=months,
        promo=promo,
    )

    return final_price, promo, discount_info


# =====================================================================
#   Y O O K A S S A
# =====================================================================

@router.callback_query(F.data.startswith("pay_yk:"))
async def pay_yk_callback_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    yookassa_service: YooKassaService,
    promo_code_service: PromoCodeService,
):
    user_id = callback.from_user.id

    # Parse incoming tariff info
    data_payload = callback.data.replace("pay_yk:", "")
    months, price_rub = _parse_months_and_price(data_payload)

    # Apply promo discount (if exists)
    final_price, promo_obj, discount_info = await _apply_promo_discount(
        session=session,
        user_id=user_id,
        months=months,
        base_price=price_rub,
        promo_code_service=promo_code_service,
    )
    price_rub = final_price

    # Form description
    description = f"Покупка подписки {months} мес"
    if discount_info:
        description += f" ({discount_info})"

    try:
        payment_url, yk_payment_id = await yookassa_service.create_yk_payment(
            amount=price_rub,
            description=description,
            user_id=user_id,
            months=months,
            promo_code_id=promo_obj.promo_code_id if promo_obj else None,
        )
    except Exception as e:
        logging.error(f"Ошибка инициализации YooKassa: {e}", exc_info=True)
        return await callback.answer("Ошибка создания платежа", show_alert=True)

    # Save pending payment
    await create_payment_record(
        session,
        {
            "user_id": user_id,
            "amount": price_rub,
            "currency": "RUB",
            "status": "pending",
            "description": description,
            "subscription_duration_months": months,
            "provider": "yookassa",
            "provider_payment_id": yk_payment_id,
            "promo_code_id": promo_obj.promo_code_id if promo_obj else None,
        },
    )

    await callback.message.answer(
        f"💳 Оплата через ЮKassa\nСумма: {price_rub}₽",
        reply_markup=user_keyboards.payment_open_link(payment_url),
    )
    await callback.answer()


# =====================================================================
#   F R E E K A S S A
# =====================================================================

@router.callback_query(F.data.startswith("pay_fk:"))
async def pay_fk_callback_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    freekassa_service: FreeKassaService,
    promo_code_service: PromoCodeService,
):
    user_id = callback.from_user.id

    data_payload = callback.data.replace("pay_fk:", "")
    months, price_rub = _parse_months_and_price(data_payload)

    # Promo
    final_price, promo_obj, discount_info = await _apply_promo_discount(
        session=session,
        user_id=user_id,
        months=months,
        base_price=price_rub,
        promo_code_service=promo_code_service,
    )
    price_rub = final_price

    description = f"Покупка подписки {months} мес"
    if discount_info:
        description += f" ({discount_info})"

    try:
        payment_url, order_id = await freekassa_service.create_fk_payment(
            amount=price_rub,
            user_id=user_id,
            months=months,
            description=description,
        )
    except Exception as e:
        logging.error("Ошибка FreeKassa", exc_info=True)
        return await callback.answer("Ошибка создания платежа", show_alert=True)

    await create_payment_record(
        session,
        {
            "user_id": user_id,
            "amount": price_rub,
            "currency": "RUB",
            "status": "pending",
            "description": description,
            "subscription_duration_months": months,
            "provider": "freekassa",
            "provider_payment_id": order_id,
            "promo_code_id": promo_obj.promo_code_id if promo_obj else None,
        },
    )

    await callback.message.answer(
        f"💳 Оплата через FreeKassa\nСумма: {price_rub}₽",
        reply_markup=user_keyboards.payment_open_link(payment_url),
    )
    await callback.answer()


# =====================================================================
#   C R Y P T O P A Y
# =====================================================================

@router.callback_query(F.data.startswith("pay_crypto:"))
async def pay_crypto_callback_handler(
    callback: CallbackQuery,
    session: AsyncSession,
    panel_api_service: PanelApiService,
    promo_code_service: PromoCodeService,
):
    user_id = callback.from_user.id

    data_payload = callback.data.replace("pay_crypto:", "")
    months, price_rub = _parse_months_and_price(data_payload)

    final_price, promo_obj, discount_info = await _apply_promo_discount(
        session=session,
        user_id=user_id,
        months=months,
        base_price=price_rub,
        promo_code_service=promo_code_service,
    )
    price_rub = final_price

    description = f"Подписка {months} мес"
    if discount_info:
        description += f" ({discount_info})"

    payment_url, crypto_invoice_id = await panel_api_service.create_crypto_invoice(
        user_id=user_id,
        amount_rub=price_rub,
        months=months,
        description=description,
    )

    await create_payment_record(
        session,
        {
            "user_id": user_id,
            "amount": price_rub,
            "currency": "RUB",
            "status": "pending",
            "description": description,
            "subscription_duration_months": months,
            "provider": "crypto",
            "provider_payment_id": crypto_invoice_id,
            "promo_code_id": promo_obj.promo_code_id if promo_obj else None,
        },
    )

    await callback.message.answer(
        f"💳 Оплата CryptoPay\nСумма: {price_rub}₽",
        reply_markup=user_keyboards.payment_open_link(payment_url),
    )
    await callback.answer()