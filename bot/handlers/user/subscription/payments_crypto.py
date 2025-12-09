from typing import Optional

from aiogram import F, Router, types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards import get_payment_url_keyboard
from bot.middlewares.i18n import JsonI18n
from bot.services.crypto_pay_service import CryptoPayService
from config.settings import Settings

router = Router(name="user_subscription_payments_crypto_router")


@router.callback_query(F.data.startswith("pay_crypto:"))
async def pay_crypto_callback_handler(
    callback: types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
    cryptopay_service: CryptoPayService,
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

    if not cryptopay_service or not getattr(cryptopay_service, "configured", False):
        try:
            await callback.answer(get_text("payment_service_unavailable_alert"), show_alert=True)
        except Exception:
            pass
        return

    try:
        _, data_payload = callback.data.split(":", 1)
        months_str, price_str = data_payload.split(":")
        months = int(months_str)
        price_amount = float(price_str)
    except (ValueError, IndexError):
        try:
            await callback.answer(get_text("error_try_again"), show_alert=True)
        except Exception:
            pass
        return

    user_id = callback.from_user.id
    payment_description = get_text("payment_description_subscription", months=months)

    invoice_url = await cryptopay_service.create_invoice(
        session=session,
        user_id=user_id,
        months=months,
        amount=price_amount,
        description=payment_description,
    )

    if invoice_url:
        try:
            await callback.message.edit_text(
                get_text(key="payment_link_message", months=months),
                reply_markup=get_payment_url_keyboard(
                    invoice_url,
                    current_lang,
                    i18n,
                    back_callback=f"subscribe_period:{months}",
                    back_text_key="back_to_payment_methods_button",
                ),
                disable_web_page_preview=False,
            )
        except Exception:
            try:
                await callback.message.answer(
                    get_text(key="payment_link_message", months=months),
                    reply_markup=get_payment_url_keyboard(
                        invoice_url,
                        current_lang,
                        i18n,
                        back_callback=f"subscribe_period:{months}",
                        back_text_key="back_to_payment_methods_button",
                    ),
                    disable_web_page_preview=False,
                )
            except Exception:
                pass
        try:
            await callback.answer()
        except Exception:
            pass
        return

    try:
        await callback.answer(get_text("error_payment_gateway"), show_alert=True)
    except Exception:
        pass
