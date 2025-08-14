import logging
import csv
import io
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from config.settings import Settings
from db.dal import payment_dal
from db.models import Payment, PhoneTransferPayment
from bot.keyboards.inline.admin_keyboards import get_back_to_admin_panel_keyboard, get_phone_transfer_approval_keyboard, get_phone_transfer_rejection_reason_keyboard
from bot.services.phone_transfer_service import PhoneTransferService
from bot.services.subscription_service import SubscriptionService
from bot.services.referral_service import ReferralService
from bot.services.panel_api_service import PanelApiService
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from bot.middlewares.i18n import JsonI18n
from aiogram import Bot

router = Router(name="admin_payments_router")


async def get_payments_with_pagination(session: AsyncSession, page: int = 0, 
                                     page_size: int = 10) -> tuple[List[Payment], int]:
    """Get payments with pagination and total count."""
    offset = page * page_size
    
    # Get total count of regular payments
    regular_count = await payment_dal.get_payments_count(session)
    
    # Get total count of phone transfer payments
    phone_transfer_count_result = await session.execute(
        select(func.count(PhoneTransferPayment.payment_id))
    )
    phone_transfer_count = phone_transfer_count_result.scalar() or 0
    
    total_count = regular_count + phone_transfer_count
    
    # Get payments for current page
    payments = await payment_dal.get_recent_payment_logs_with_user(
        session, limit=page_size, offset=offset
    )
    
    # Also get phone transfer payments
    phone_transfer_payments_result = await session.execute(
        select(PhoneTransferPayment).options(
            selectinload(PhoneTransferPayment.user)
        ).order_by(PhoneTransferPayment.created_at.desc()).limit(page_size).offset(offset)
    )
    phone_transfer_payments = phone_transfer_payments_result.scalars().all()
    
    # Convert phone transfer payments to Payment format for display
    for pt_payment in phone_transfer_payments:
        # Create a mock Payment object for display purposes
        mock_payment = Payment(
            payment_id=pt_payment.payment_id,
            user_id=pt_payment.user_id,
            amount=pt_payment.amount,
            currency=pt_payment.currency,
            status=pt_payment.status,
            provider='phone_transfer',
            description=pt_payment.description,
            subscription_duration_months=pt_payment.subscription_duration_months,
            created_at=pt_payment.created_at,
            user=pt_payment.user
        )
        payments.append(mock_payment)
    
    # Sort all payments by creation date
    payments.sort(key=lambda x: x.created_at, reverse=True)
    
    return payments, total_count


def format_payment_text(payment: Payment, i18n: JsonI18n, lang: str) -> str:
    """Format single payment info as text."""
    _ = lambda key, **kwargs: i18n.gettext(lang, key, **kwargs)
    
    # Handle phone transfer payments status
    if payment.provider == 'phone_transfer':
        status_emoji = "✅" if payment.status == 'approved' else (
            "⏳" if payment.status == 'pending' else "❌"
        )
    else:
        status_emoji = "✅" if payment.status == 'succeeded' else (
            "⏳" if payment.status in ['pending', 'pending_yookassa'] else "❌"
        )
    
    user_info = f"User {payment.user_id}"
    if payment.user and payment.user.username:
        user_info += f" (@{payment.user.username})"
    elif payment.user and payment.user.first_name:
        user_info += f" ({payment.user.first_name})"
    
    payment_date = payment.created_at.strftime('%Y-%m-%d %H:%M') if payment.created_at else "N/A"
    
    provider_text = {
        'yookassa': 'YooKassa',
        'tribute': 'Tribute', 
        'telegram_stars': 'Telegram Stars',
        'cryptopay': 'CryptoPay',
        'phone_transfer': 'Перевод по номеру'
    }.get(payment.provider, payment.provider or 'Unknown')
    
    return (
        f"{status_emoji} <b>{payment.amount} {payment.currency}</b>\n"
        f"👤 {user_info}\n"
        f"💳 {provider_text}\n"
        f"📅 {payment_date}\n"
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

    page_size = 5  # Показываем по 5 платежей на странице
    payments, total_count = await get_payments_with_pagination(session, page, page_size)
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    if not payments and page == 0:
        await callback.message.edit_text(
            _("admin_no_payments_found", default="Платежи не найдены."),
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    # Format payments text
    text_parts = [_("admin_payments_header", default="💰 <b>Все платежи</b>")]
    text_parts.append(f"📊 Показано {len(payments)} из {total_count} платежей (стр. {page + 1}/{total_pages})\n")
    
    for i, payment in enumerate(payments, 1):
        text_parts.append(f"<b>{page * page_size + i}.</b> {format_payment_text(payment, i18n, current_lang)}")
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
            text=_("admin_export_payments_csv", default="📊 Экспорт CSV"), 
            callback_data="payments_export_csv"
        ),
        InlineKeyboardButton(
            text=_("admin_refresh_payments", default="🔄 Обновить"), 
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
                _("admin_no_payments_to_export", default="Нет платежей для экспорта."),
                show_alert=True
            )
            return

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            _("admin_csv_payment_id", default="ID"),
            _("admin_csv_user_id", default="User ID"),
            _("admin_csv_username", default="Username"),
            _("admin_csv_first_name", default="First Name"),
            _("admin_csv_amount", default="Amount"),
            _("admin_csv_currency", default="Currency"),
            _("admin_csv_provider", default="Provider"),
            _("admin_csv_status", default="Status"),
            _("admin_csv_description", default="Description"),
            _("admin_csv_months", default="Months"),
            _("admin_csv_created_at", default="Created At"),
            _("admin_csv_provider_payment_id", default="Provider Payment ID")
        ])
        
        # Write payment data
        for payment in all_payments:
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
                payment.subscription_duration_months or "",
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
                     default="📊 Экспорт платежей завершен!\nВсего записей: {count}",
                     count=len(all_payments))
        )
        
        await callback.answer(
            _("admin_export_sent", default="Файл отправлен!"),
            show_alert=False
        )
        
    except Exception as e:
        logging.error(f"Failed to export payments CSV: {e}", exc_info=True)
        await callback.answer(f"❌ Ошибка экспорта: {str(e)}", show_alert=True)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: types.CallbackQuery):
    """Handle no-op callback (for pagination display)."""
    await callback.answer()


@router.callback_query(F.data.startswith("approve_phone_transfer:"))
async def approve_phone_transfer_handler(
        callback: types.CallbackQuery, i18n_data: dict, session: AsyncSession,
        phone_transfer_service: PhoneTransferService, subscription_service: SubscriptionService,
        referral_service: ReferralService, panel_service: PanelApiService):
    """Approve a phone transfer payment"""
    current_lang = i18n_data.get("current_language", "ru")
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    
    if not i18n or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return
    
    try:
        payment_id = int(callback.data.split(":")[-1])
        logging.info(f"Admin {callback.from_user.id} attempting to approve phone transfer payment {payment_id}")
    except (ValueError, IndexError):
        await callback.answer("Invalid payment ID.", show_alert=True)
        return
    
    # Get payment details
    payment = await session.get(PhoneTransferPayment, payment_id)
    if not payment:
        logging.error(f"Payment {payment_id} not found in database")
        await callback.answer("Payment not found.", show_alert=True)
        return
    
    if payment.status != "pending":
        logging.warning(f"Payment {payment_id} is not in pending status. Current status: {payment.status}")
        await callback.answer("Payment is not in pending status.", show_alert=True)
        return
    
    logging.info(f"Approving payment {payment_id} for user {payment.user_id}")
    
    # Approve payment
    success = await phone_transfer_service.approve_payment(
        session, payment_id, callback.from_user.id, "Approved by admin"
    )
    
    if not success:
        logging.error(f"Failed to approve payment {payment_id} via phone_transfer_service")
        await callback.answer("Failed to approve payment.", show_alert=True)
        return
    
    logging.info(f"Payment {payment_id} approved successfully, now activating subscription")
    
    # Activate subscription
    try:
        activation_details = await subscription_service.activate_subscription(
            session,
            payment.user_id,
            payment.subscription_duration_months,
            payment.amount,
            None,  # No payment_id for phone transfer
            promo_code_id_from_payment=payment.promo_code_id,
            provider="phone_transfer"
        )
        
        if not activation_details or not activation_details.get('end_date'):
            logging.error(f"Failed to activate subscription for payment {payment_id}")
            await callback.answer("Failed to activate subscription.", show_alert=True)
            return
        
        logging.info(f"Subscription activated successfully for payment {payment_id}")
        
        # Apply referral bonuses if applicable
        try:
            await referral_service.apply_referral_bonuses_for_payment(
                session, payment.user_id, payment.subscription_duration_months
            )
            logging.info(f"Referral bonuses applied for payment {payment_id}")
        except Exception as ref_error:
            logging.warning(f"Failed to apply referral bonuses for payment {payment_id}: {ref_error}")
        
        # Notify user about successful payment
        logging.info(f"Attempting to notify user {payment.user_id} about approved payment {payment_id}")
        await notify_user_about_approved_payment(
            callback.bot, payment, activation_details
        )
        
        # Update admin message
        await callback.message.edit_text(
            f"✅ Платеж {payment_id} подтвержден!\n"
            f"Подписка активирована для пользователя {payment.user_id}.\n"
            f"Срок: {payment.subscription_duration_months} мес.\n"
            f"Сумма: {payment.amount} {payment.currency}",
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n)
        )
        
        await callback.answer("Payment approved successfully!")
        logging.info(f"Payment {payment_id} approval process completed successfully")
        
    except Exception as e:
        logging.error(f"Error activating subscription for phone transfer payment {payment_id}: {e}")
        await callback.answer("Payment approved but subscription activation failed.", show_alert=True)


@router.callback_query(F.data.startswith("reject_phone_transfer:"))
async def reject_phone_transfer_handler(
        callback: types.CallbackQuery, i18n_data: dict, session: AsyncSession,
        phone_transfer_service: PhoneTransferService):
    """Show rejection reason selection for phone transfer payment"""
    current_lang = i18n_data.get("current_language", "ru")
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    
    if not i18n or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return
    
    try:
        payment_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Invalid payment ID.", show_alert=True)
        return
    
    # Show rejection reason keyboard
    reply_markup = get_phone_transfer_rejection_reason_keyboard(payment_id)
    await callback.message.edit_text(
        "Выберите причину отклонения платежа:",
        reply_markup=reply_markup
    )
    
    await callback.answer()


@router.callback_query(F.data.startswith("reject_reason:"))
async def reject_reason_handler(
        callback: types.CallbackQuery, i18n_data: dict, session: AsyncSession,
        phone_transfer_service: PhoneTransferService):
    """Handle rejection reason selection and reject payment"""
    current_lang = i18n_data.get("current_language", "ru")
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    
    if not i18n or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return
    
    try:
        _, payment_id_str, reason_code = callback.data.split(":")
        payment_id = int(payment_id_str)
        logging.info(f"Admin {callback.from_user.id} attempting to reject phone transfer payment {payment_id} with reason: {reason_code}")
    except (ValueError, IndexError):
        await callback.answer("Invalid data.", show_alert=True)
        return
    
    # Map reason codes to human-readable text
    reason_map = {
        "wrong_amount": "Неверная сумма перевода",
        "wrong_recipient": "Неверный номер получателя",
        "unreadable_receipt": "Чек нечитаем или неполный",
        "wrong_date": "Неверная дата перевода",
        "other_reason": "Другая причина"
    }
    
    reason_text = reason_map.get(reason_code, "Неизвестная причина")
    
    # Reject payment
    success = await phone_transfer_service.reject_payment(
        session, payment_id, callback.from_user.id, reason_text, f"Rejected by admin: {reason_text}"
    )
    
    if not success:
        logging.error(f"Failed to reject payment {payment_id} via phone_transfer_service")
        await callback.answer("Failed to reject payment.", show_alert=True)
        return
    
    logging.info(f"Payment {payment_id} rejected successfully, now notifying user")
    
    # Get payment details for user notification
    payment = await session.get(PhoneTransferPayment, payment_id)
    if payment:
        # Notify user about rejected payment
        await notify_user_about_rejected_payment(
            callback.bot, payment, reason_text
        )
        logging.info(f"User {payment.user_id} notified about rejected payment {payment_id}")
    else:
        logging.warning(f"Payment {payment_id} not found when trying to notify user")
    
    # Update admin message
    await callback.message.edit_text(
        f"❌ Платеж {payment_id} отклонен!\n"
        f"Причина: {reason_text}\n"
        f"Пользователь уведомлен об отклонении.",
        reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n)
    )
    
    await callback.answer("Payment rejected successfully!")
    logging.info(f"Payment {payment_id} rejection process completed successfully")


@router.callback_query(F.data.startswith("view_phone_transfer:"))
async def view_phone_transfer_handler(
        callback: types.CallbackQuery, i18n_data: dict, session: AsyncSession):
    """View detailed information about phone transfer payment"""
    current_lang = i18n_data.get("current_language", "ru")
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    
    if not i18n or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return
    
    try:
        payment_id = int(callback.data.split(":")[-1])
        logging.info(f"Admin {callback.from_user.id} viewing phone transfer payment {payment_id}")
    except (ValueError, IndexError):
        await callback.answer("Invalid payment ID.", show_alert=True)
        return
    
    # Get payment details
    payment = await session.get(PhoneTransferPayment, payment_id)
    if not payment:
        logging.error(f"Payment {payment_id} not found when admin tried to view it")
        await callback.answer("Payment not found.", show_alert=True)
        return
    
    logging.info(f"Payment {payment_id} details retrieved successfully for admin view")
    
    # Format payment details
    user_info = f"User {payment.user_id}"
    if payment.user and payment.user.username:
        user_info += f" (@{payment.user.username})"
    elif payment.user and payment.user.first_name:
        user_info += f" ({payment.user.first_name})"
    
    payment_date = payment.created_at.strftime('%Y-%m-%d %H:%M') if payment.created_at else "N/A"
    
    details_text = (
        f"📱 <b>Детали платежа по переводу</b>\n\n"
        f"🆔 ID: {payment.payment_id}\n"
        f"👤 {user_info}\n"
        f"💰 Сумма: {payment.amount} {payment.currency}\n"
        f"📅 Срок подписки: {payment.subscription_duration_months} мес.\n"
        f"📅 Дата создания: {payment_date}\n"
        f"📋 Статус: {payment.status}\n"
        f"📝 Описание: {payment.description or 'N/A'}\n"
    )
    
    if payment.receipt_photo_id:
        details_text += f"\n📸 Чек загружен: Да"
    
    if payment.admin_notes:
        details_text += f"\n📝 Заметки админа: {payment.admin_notes}"
    
    # Show details with approval keyboard
    reply_markup = get_phone_transfer_approval_keyboard(payment_id)
    await callback.message.edit_text(
        details_text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    
    await callback.answer()
    logging.info(f"Payment {payment_id} details displayed to admin successfully")


@router.callback_query(F.data.startswith("cancel_rejection:"))
async def cancel_rejection_handler(
        callback: types.CallbackQuery, i18n_data: dict, session: AsyncSession):
    """Cancel payment rejection and return to approval keyboard"""
    current_lang = i18n_data.get("current_language", "ru")
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    
    if not i18n or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return
    
    try:
        payment_id = int(callback.data.split(":")[-1])
        logging.info(f"Admin {callback.from_user.id} cancelled rejection for payment {payment_id}")
    except (ValueError, IndexError):
        await callback.answer("Invalid payment ID.", show_alert=True)
        return
    
    # Get payment details
    payment = await session.get(PhoneTransferPayment, payment_id)
    if not payment:
        await callback.answer("Payment not found.", show_alert=True)
        return
    
    # Show approval keyboard again
    reply_markup = get_phone_transfer_approval_keyboard(payment_id)
    await callback.message.edit_text(
        f"📱 <b>Платеж по переводу {payment_id}</b>\n\n"
        f"👤 User {payment.user_id}\n"
        f"💰 Сумма: {payment.amount} {payment.currency}\n"
        f"📅 Срок: {payment.subscription_duration_months} мес.\n"
        f"📋 Статус: {payment.status}\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    
    await callback.answer("Rejection cancelled")
    logging.info(f"Rejection cancelled for payment {payment_id}, returned to approval keyboard")


async def notify_user_about_approved_payment(
        bot: Bot, payment: PhoneTransferPayment, activation_details: dict):
    """Notify user about approved phone transfer payment"""
    try:
        logging.info(f"Attempting to notify user {payment.user_id} about approved payment {payment.payment_id}")
        
        user_lang = "ru"  # Default language
        if payment.user and payment.user.language_code:
            user_lang = payment.user.language_code
        
        # Get i18n instance
        from bot.middlewares.i18n import JsonI18n
        i18n = JsonI18n()
        
        _ = lambda key, **kwargs: i18n.gettext(user_lang, key, **kwargs)
        
        config_link = activation_details.get("subscription_url") or _("config_link_not_available")
        
        message_text = _(
            "phone_transfer_payment_approved",
            default="✅ Ваш платеж по переводу подтвержден!\n\n"
            f"Подписка на {payment.subscription_duration_months} мес. активирована.\n"
            f"Активна до: {activation_details['end_date'].strftime('%Y-%m-%d')}\n\n"
            f"Ключ подключения:\n<code>{config_link}</code>\n\n"
            "Чтобы подключиться, перейдите по ссылке и следуйте инструкции 👇"
        )
        
        # Get keyboard
        from bot.keyboards.inline.user_keyboards import get_connect_and_main_keyboard
        from config.settings import get_settings
        settings = get_settings()
        
        reply_markup = get_connect_and_main_keyboard(
            user_lang, i18n, settings, config_link
        )
        
        # Send message to user
        sent_message = await bot.send_message(
            payment.user_id,
            message_text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
        logging.info(f"Successfully notified user {payment.user_id} about approved payment {payment.payment_id}. Message ID: {sent_message.message_id}")
        
    except Exception as e:
        logging.error(f"Error notifying user {payment.user_id} about approved phone transfer payment {payment.payment_id}: {e}")
        # Try to send a simple message without markup
        try:
            await bot.send_message(
                payment.user_id,
                f"✅ Ваш платеж по переводу подтвержден! Подписка активирована на {payment.subscription_duration_months} мес.",
                parse_mode="HTML"
            )
            logging.info(f"Sent fallback notification to user {payment.user_id}")
        except Exception as fallback_error:
            logging.error(f"Failed to send fallback notification to user {payment.user_id}: {fallback_error}")


async def notify_user_about_rejected_payment(
        bot: Bot, payment: PhoneTransferPayment, reason: str):
    """Notify user about rejected phone transfer payment"""
    try:
        logging.info(f"Attempting to notify user {payment.user_id} about rejected payment {payment.payment_id}")
        
        user_lang = "ru"  # Default language
        if payment.user and payment.user.language_code:
            user_lang = payment.user.language_code
        
        # Get i18n instance
        from bot.middlewares.i18n import JsonI18n
        i18n = JsonI18n()
        
        _ = lambda key, **kwargs: i18n.gettext(user_lang, key, **kwargs)
        
        message_text = _(
            "phone_transfer_payment_rejected",
            default="❌ Ваш платеж по переводу отклонен.\n\n"
            f"Причина: {reason}\n\n"
            "Пожалуйста, проверьте детали перевода и попробуйте еще раз.\n"
            "Если у вас есть вопросы, обратитесь в поддержку."
        )
        
        # Get keyboard
        from bot.keyboards.inline.user_keyboards import get_back_to_main_menu_markup
        
        reply_markup = get_back_to_main_menu_markup(user_lang, i18n)
        
        # Send message to user
        sent_message = await bot.send_message(
            payment.user_id,
            message_text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        
        logging.info(f"Successfully notified user {payment.user_id} about rejected payment {payment.payment_id}. Message ID: {sent_message.message_id}")
        
    except Exception as e:
        logging.error(f"Error notifying user {payment.user_id} about rejected phone transfer payment {payment.payment_id}: {e}")
        # Try to send a simple message without markup
        try:
            await bot.send_message(
                payment.user_id,
                f"❌ Ваш платеж по переводу отклонен. Причина: {reason}",
                parse_mode="HTML"
            )
            logging.info(f"Sent fallback rejection notification to user {payment.user_id}")
        except Exception as fallback_error:
            logging.error(f"Failed to send fallback rejection notification to user {payment.user_id}: {fallback_error}")