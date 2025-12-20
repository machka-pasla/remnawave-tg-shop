import logging
import csv
import io
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.dal import payment_dal
from db.models import Payment
from bot.keyboards.inline.admin_keyboards import get_back_to_admin_panel_keyboard
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from bot.middlewares.i18n import JsonI18n

router = Router(name="admin_payments_router")


async def get_payments_with_pagination(session: AsyncSession, page: int = 0, 
                                     page_size: int = 10) -> tuple[List[Payment], int]:
    """Get payments with pagination and total count."""
    offset = page * page_size
    
    # Get total count
    total_count = await payment_dal.get_payments_count(session)
    
    # Get payments for current page
    payments = await payment_dal.get_recent_payment_logs_with_user(
        session, limit=page_size, offset=offset
    )
    
    return payments, total_count


def format_payment_text(payment: Payment, i18n: JsonI18n, lang: str, settings: Settings) -> str:
    """Format single payment info as text."""
    _ = lambda key, **kwargs: i18n.gettext(lang, key, **kwargs)
    
    pending_statuses = [
        'pending',
        'pending_yookassa',
        'pending_freekassa',
        'pending_platega',
        'pending_severpay',
        'pending_cryptopay',
    ]
    status_emoji = "✅" if payment.status == 'succeeded' else (
        "⏳" if payment.status in pending_statuses else "❌"
    )
    
    user_info = f"User {payment.user_id}"
    if payment.user and payment.user.username:
        user_info += f" (@{payment.user.username})"
    elif payment.user and payment.user.first_name:
        user_info += f" ({payment.user.first_name})"
    
    payment_date = payment.created_at.strftime('%Y-%m-%d %H:%M') if payment.created_at else "N/A"
    
    provider_text = {
        'yookassa': 'YooKassa',
        'telegram_stars': 'Telegram Stars',
        'cryptopay': 'CryptoPay',
        'freekassa': 'FreeKassa',
        'severpay': 'SeverPay',
        'platega': 'Platega',
    }.get(payment.provider, payment.provider or 'Unknown')

    traffic_mode = getattr(settings, "traffic_sale_mode", False)
    if traffic_mode:
        traffic_val = payment.subscription_duration_months or 0
        traffic_display = str(int(traffic_val)) if float(traffic_val).is_integer() else f"{traffic_val:g}"
        period_line = _("admin_payment_traffic_label", traffic_gb=traffic_display)
    else:
        period_line = _("admin_payment_months_label", months=payment.subscription_duration_months or 0)
    
    return (
        f"{status_emoji} <b>{payment.amount} {payment.currency}</b>\n"
        f"👤 {user_info}\n"
        f"💳 {provider_text}\n"
        f"📅 {payment_date}\n"
        f"{period_line}\n"
        f"📋 {payment.status}\n"
        f"📝 {payment.description or 'N/A'}"
    )


async def view_payments_handler(callback: types.CallbackQuery, i18n_data: dict, 
                              settings: Settings, session: AsyncSession, page: int = 0):
    """Display paginated list of all payments."""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    page_size = 5  # Show 5 payments per page
    payments, total_count = await get_payments_with_pagination(session, page, page_size)
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    if not payments and page == 0:
        await callback.message.edit_text(
            _("admin_no_payments_found"),
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    # Format payments text
    text_parts = [_("admin_payments_header")]
    text_parts.append(_("admin_payments_pagination_info", 
                       shown=len(payments), 
                       total=total_count, 
                       current_page=page + 1, 
                       total_pages=total_pages) + "\n")
    
    for i, payment in enumerate(payments, 1):
        text_parts.append(f"<b>{page * page_size + i}.</b> {format_payment_text(payment, i18n, current_lang, settings)}")
        text_parts.append("")  # Empty line between payments

    # Build keyboard with pagination and export
    builder = InlineKeyboardBuilder()
    
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"payments_page:{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"payments_page:{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    # Export and refresh buttons
    builder.row(
        InlineKeyboardButton(
            text=_("admin_export_payments_csv"), 
            callback_data="payments_export_csv"
        ),
        InlineKeyboardButton(
            text=_("admin_refresh_payments"), 
            callback_data=f"payments_page:{page}"
        )
    )
    
    # Back button
    builder.row(InlineKeyboardButton(
        text=_("back_to_admin_panel_button"), 
        callback_data="admin_section:stats_monitoring"
    ))

    await callback.message.edit_text(
        "\n".join(text_parts),
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("payments_page:"))
async def payments_pagination_handler(callback: types.CallbackQuery, i18n_data: dict, 
                                    settings: Settings, session: AsyncSession):
    """Handle pagination for payments list."""
    try:
        page = int(callback.data.split(":")[1])
        await view_payments_handler(callback, i18n_data, settings, session, page)
    except (ValueError, IndexError):
        await callback.answer("Error processing pagination.", show_alert=True)


@router.callback_query(F.data == "payments_export_csv")
async def export_payments_csv_handler(callback: types.CallbackQuery, i18n_data: dict, 
                                    settings: Settings, session: AsyncSession):
    """Export all successful payments to CSV file."""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n:
        await callback.answer("Language service error.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        # Get all successful payments
        all_payments = await payment_dal.get_all_succeeded_payments_with_user(session)
        
        if not all_payments:
            await callback.answer(
                _("admin_no_payments_to_export"),
                show_alert=True
            )
            return

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            _("admin_csv_payment_id"),
            _("admin_csv_user_id"),
            _("admin_csv_username"),
            _("admin_csv_first_name"),
            _("admin_csv_amount"),
            _("admin_csv_currency"),
            _("admin_csv_provider"),
            _("admin_csv_status"),
            _("admin_csv_description"),
            _("admin_csv_units"),
            _("admin_csv_created_at"),
            _("admin_csv_provider_payment_id")
        ])

        traffic_mode = getattr(settings, "traffic_sale_mode", False)
        
        # Write payment data
        for payment in all_payments:
            units_val = payment.subscription_duration_months or ""
            if traffic_mode and units_val not in ("", None):
                try:
                    units_val = str(int(units_val)) if float(units_val).is_integer() else f"{units_val:g}"
                except Exception:
                    units_val = payment.subscription_duration_months or ""
            writer.writerow([
                payment.payment_id,
                payment.user_id,
                payment.user.username if payment.user and payment.user.username else "",
                payment.user.first_name if payment.user and payment.user.first_name else "",
                payment.amount,
                payment.currency,
                payment.provider or "",
                payment.status,
                payment.description or "",
                units_val,
                payment.created_at.strftime('%Y-%m-%d %H:%M:%S') if payment.created_at else "",
                payment.provider_payment_id or ""
            ])
        
        # Prepare file
        csv_content = output.getvalue().encode('utf-8-sig')  # UTF-8 with BOM for Excel
        output.close()
        
        # Generate filename with current date
        current_time = datetime.now().strftime('%Y-%m-%d_%H-%M')
        filename = f"payments_export_{current_time}.csv"
        
        # Send file
        from aiogram.types import BufferedInputFile
        file = BufferedInputFile(csv_content, filename=filename)
        
        await callback.message.reply_document(
            document=file,
            caption=_("admin_payments_export_success",
                     count=len(all_payments))
        )
        
        await callback.answer(
            _("admin_export_sent"),
            show_alert=False
        )
        
    except Exception as e:
        logging.error(f"Failed to export payments CSV: {e}", exc_info=True)
        await callback.answer(f"❌ Ошибка экспорта: {str(e)}", show_alert=True)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: types.CallbackQuery):
    """Handle no-op callback (for pagination display)."""
    await callback.answer()
