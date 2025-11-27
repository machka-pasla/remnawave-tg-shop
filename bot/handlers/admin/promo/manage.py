import logging
import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any

from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.dal import promo_code_dal
from db.models import PromoCode
from bot.states.admin_states import AdminStates
from bot.keyboards.inline.admin_keyboards import (
    get_back_to_admin_panel_keyboard,
)
from bot.middlewares.i18n import JsonI18n

router = Router(name="promo_manage_router")


# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================================

def _get_i18n_from_data(
    i18n_data: Dict[str, Any],
) -> Tuple[Optional[JsonI18n], Optional[str]]:
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    current_lang: Optional[str] = i18n_data.get("current_language")
    return i18n, current_lang


def _t(i18n: JsonI18n, lang: str, key: str, **kwargs) -> str:
    """
    Короткий хелпер для перевода.
    Поддерживает параметр default=... для новых ключей.
    """
    return i18n.gettext(lang, key, **kwargs)


def get_promo_status_emoji_and_text(
    promo: PromoCode,
    i18n: JsonI18n,
    lang: str,
) -> Tuple[str, str]:
    """Определяем статус промокода и возвращаем (emoji, текст статуса)."""
    now = datetime.now(timezone.utc)
    _ = lambda key, **kwargs: _t(i18n, lang, key, **kwargs)

    if promo.valid_until and promo.valid_until < now:
        return "⏰", _("admin_promo_status_expired", default="Expired")
    if promo.current_activations >= promo.max_activations:
        return "🔄", _("admin_promo_status_used_up", default="Used up")
    if promo.is_active:
        return "✅", _("admin_promo_status_active", default="Active")
    return "🚫", _("admin_promo_status_inactive", default="Inactive")


async def get_promo_detail_text_and_keyboard(
    promo_id: int,
    session: AsyncSession,
    i18n: JsonI18n,
    lang: str,
) -> Tuple[Optional[str], Optional[types.InlineKeyboardMarkup]]:
    """Формируем подробную карточку промокода + клавиатуру действий."""
    _ = lambda key, **kwargs: _t(i18n, lang, key, **kwargs)

    promo = await promo_code_dal.get_promo_code_by_id(session, promo_id)
    if not promo:
        return None, None

    status_emoji, status_text = get_promo_status_emoji_and_text(promo, i18n, lang)

    # Валидность
    validity = _("admin_promo_valid_indefinitely", default="Indefinitely")
    if promo.valid_until:
        validity = promo.valid_until.strftime("%d.%m.%Y %H:%M")

    created_str = promo.created_at.strftime("%d.%m.%Y %H:%M") if promo.created_at else "N/A"

    # Описание промо (бонус или скидка)
    if promo.discount_percent:
        # Скидочный промо
        discount_line = f"💸 {promo.discount_percent}%"
        if promo.discount_plan_months:
            discount_line += " " + _(
                "admin_promo_applicable_to_plan",
                months=promo.discount_plan_months,
                default=f"— applicable to {promo.discount_plan_months} month(s)",
            )
        else:
            discount_line += " " + _(
                "admin_promo_applicable_to_all",
                default="— applicable to all plans",
            )
        promo_main_line = discount_line
    else:
        # Бонусные дни (по умолчанию 0, если None)
        days = promo.bonus_days or 0
        promo_main_line = _(
            "admin_promo_card_bonus_days",
            days=days,
            default=f"🎁 Bonus days: <b>{days}</b>",
        )

    text_lines = [
        _(
            "admin_promo_card_title",
            code=promo.code,
            default=f"🎟 <b>Promo code: {promo.code}</b>",
        ),
        promo_main_line,
        _(
            "admin_promo_card_activations",
            current=promo.current_activations,
            max=promo.max_activations,
            default=f"🔢 Activations: <b>{promo.current_activations}/{promo.max_activations}</b>",
        ),
        _(
            "admin_promo_card_validity",
            validity=validity,
            default=f"⏰ Valid until: <b>{validity}</b>",
        ),
        _(
            "admin_promo_card_status",
            status=status_text,
            default=f"📊 Status: <b>{status_text}</b>",
        ),
        _(
            "admin_promo_card_created",
            created=created_str,
            default=f"📅 Created: <b>{created_str}</b>",
        ),
        _(
            "admin_promo_card_created_by",
            creator=promo.created_by_admin_id,
            default=f"👤 Created by: <b>{promo.created_by_admin_id}</b>",
        ),
    ]
    text = "\n".join(text_lines)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_edit_button", default="✏️ Edit"),
            callback_data=f"promo_edit_select:{promo_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_toggle_status_button", default="🔄 On/Off"),
            callback_data=f"promo_toggle:{promo_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_view_activations_button", default="📋 Activations"),
            callback_data=f"promo_activations:{promo_id}:0",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_delete_button", default="🗑 Delete"),
            callback_data=f"promo_delete:{promo_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_back_to_list_button", default="⬅️ Back to list"),
            callback_data="admin_action:promo_management",
        )
    )

    return text, builder.as_markup()


# =====================================================================
# ПРОСМОТР АКТИВНЫХ ПРОМОКОДОВ (КОРОТКИЙ СПИСОК)
# =====================================================================

async def view_promo_codes_handler(
    callback: types.CallbackQuery,
    i18n_data: Dict[str, Any],
    settings: Settings,
    session: AsyncSession,
):
    i18n, lang = _get_i18n_from_data(i18n_data)
    if not i18n or not lang or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return

    _ = lambda key, **kwargs: _t(i18n, lang, key, **kwargs)

    promo_models = await promo_code_dal.get_all_active_promo_codes(
        session, limit=50, offset=0
    )

    if not promo_models:
        text = (
            _(
                "admin_active_promos_list_header",
                default="Active promo codes:",
            )
            + "\n\n"
            + _(
                "admin_no_active_promos",
                default="No active promo codes.",
            )
        )
    else:
        lines = [
            _(
                "admin_active_promos_list_header",
                default="Active promo codes:",
            ),
            "",
        ]
        for p in promo_models:
            status_emoji, _status = get_promo_status_emoji_and_text(p, i18n, lang)

            if p.discount_percent:
                promo_desc = f"💸 {p.discount_percent}%"
                if p.discount_plan_months:
                    promo_desc += f" ({p.discount_plan_months}m)"
                else:
                    promo_desc += " (all)"
            else:
                promo_desc = f"🎁 {p.bonus_days or 0}d"

            valid_str = (
                p.valid_until.strftime("%d.%m.%Y")
                if p.valid_until
                else _(
                    "admin_promo_valid_indefinitely",
                    default="Indefinitely",
                )
            )

            lines.append(
                f"{status_emoji} <code>{p.code}</code> | {promo_desc} | "
                f"📊 {p.current_activations}/{p.max_activations} | ⏰ {valid_str}"
            )
        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_admin_panel_keyboard(lang, i18n),
        parse_mode="HTML",
    )
    await callback.answer()


# =====================================================================
# УПРАВЛЕНИЕ ПРОМОКОДАМИ (СПИСОК + ПАГИНАЦИЯ)
# =====================================================================

async def promo_management_handler(
    callback: types.CallbackQuery,
    i18n_data: Dict[str, Any],
    settings: Settings,
    session: AsyncSession,
    page: int = 0,
):
    i18n, lang = _get_i18n_from_data(i18n_data)
    if not i18n or not lang or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return

    _ = lambda key, **kwargs: _t(i18n, lang, key, **kwargs)

    page_size = 10
    offset = page * page_size

    total_count = await promo_code_dal.get_promo_codes_count(session)
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    promo_models = await promo_code_dal.get_all_promo_codes_with_details(
        session, limit=page_size, offset=offset
    )

    if not promo_models and page == 0:
        await callback.message.edit_text(
            _("admin_promo_management_empty", default="No promo codes found."),
            reply_markup=get_back_to_admin_panel_keyboard(lang, i18n),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for promo in promo_models:
        status_emoji, _status = get_promo_status_emoji_and_text(promo, i18n, lang)

        if promo.discount_percent:
            # discount
            extra = f"{promo.discount_percent}%"
            if promo.discount_plan_months:
                extra += f" ({promo.discount_plan_months}m)"
            else:
                extra += " (all)"
        else:
            # bonus
            extra = f"{promo.bonus_days or 0}d"

        button_text = (
            f"{status_emoji} {promo.code} ({extra}) "
            f"{promo.current_activations}/{promo.max_activations}"
        )
        builder.row(
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"promo_detail:{promo.promo_code_id}",
            )
        )

    # Пагинация
    if total_pages > 1:
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text=_("prev_page_button", default="⬅️ Prev."),
                    callback_data=f"promo_management:{page - 1}",
                )
            )
        if page < total_pages - 1:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text=_("next_page_button", default="Next ➡️"),
                    callback_data=f"promo_management:{page + 1}",
                )
            )
        if pagination_buttons:
            builder.row(*pagination_buttons)

    # Экспорт всех + назад
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_export_csv_button", default="📄 Export to CSV"),
            callback_data="promo_export_all",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("back_to_admin_panel_button", default="⬅️ To Admin"),
            callback_data="admin_action:main",
        )
    )

    title = _(
        "admin_promo_management_title",
        default="🎟 <b>Promo Code Management</b>\n\nSelect a promo code for details:",
    )
    if total_pages > 1:
        title += "\n" + _(
            "admin_promo_list_page_info",
            current=page + 1,
            total=total_pages,
            count=total_count,
            default=f"Page {page + 1}/{total_pages} ({total_count} promo codes)",
        )

    await callback.message.edit_text(
        title,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("promo_management:"))
async def promo_management_pagination_handler(
    callback: types.CallbackQuery,
    i18n_data: Dict[str, Any],
    settings: Settings,
    session: AsyncSession,
):
    try:
        page = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Error processing pagination.", show_alert=True)
        return

    await promo_management_handler(callback, i18n_data, settings, session, page)


# =====================================================================
# КАРТОЧКА ПРОМОКОДА
# =====================================================================

@router.callback_query(F.data.startswith("promo_detail:"))
async def promo_detail_handler(
    callback: types.CallbackQuery,
    i18n_data: Dict[str, Any],
    session: AsyncSession,
):
    i18n, lang = _get_i18n_from_data(i18n_data)
    if not i18n or not lang or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return

    _ = lambda key, **kwargs: _t(i18n, lang, key, **kwargs)

    try:
        promo_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(
            _("admin_promo_not_found", default="Promo not found."),
            show_alert=True,
        )
        return

    text, keyboard = await get_promo_detail_text_and_keyboard(
        promo_id, session, i18n, lang
    )
    if not text:
        await callback.answer(
            _("admin_promo_not_found", default="Promo not found."),
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


# =====================================================================
# ВКЛ/ВЫКЛ ПРОМОКОДА
# =====================================================================

@router.callback_query(F.data.startswith("promo_toggle:"))
async def promo_toggle_handler(
    callback: types.CallbackQuery,
    i18n_data: Dict[str, Any],
    session: AsyncSession,
):
    i18n, lang = _get_i18n_from_data(i18n_data)
    if not i18n or not lang or not callback.message:
        await callback.answer("Language service error.", show_alert=True)
        return

    _ = lambda key, **kwargs: _t(i18n, lang, key, **kwargs)

    try:
        promo_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(
            _("admin_promo_not_found", default="Promo not found."),
            show_alert=True,
        )
        return

    promo = await promo_code_dal.get_promo_code_by_id(session, promo_id)
    if not promo:
        await callback.answer(
            _("admin_promo_not_found", default="Promo not found."),
            show_alert=True,
        )
        return

    new_status = not promo.is_active
    updated = await promo_code_dal.update_promo_code(
        session, promo_id, {"is_active": new_status}
    )
    if not updated:
        await callback.answer(
            _("error_occurred_try_again", default="Error occurred, try again."),
            show_alert=True,
        )
        return

    await session.commit()

    status_text = (
        _("admin_promo_status_activated", default="activated")
        if new_status
        else _("admin_promo_status_deactivated", default="deactivated")
    )

    await callback.answer(
        _(
            "admin_promo_toggle_success",
            code=promo.code,
            status=status_text,
            default=f"Promo {promo.code} {status_text}",
        ),
        show_alert=True,
    )

    text, keyboard = await get_promo_detail_text_and_keyboard(
        promo_id, session, i18n, lang
    )
    if text:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )


# =====================================================================
# АКТИВАЦИИ ПРОМОКОДА + ЭКСПОРТ
# =====================================================================

@router.callback_query(F.data.startswith("promo_activations:"))
async def promo_activations_handler(
    callback: types.CallbackQuery,
    i18n_data: Dict[str, Any],
    settings: Settings,
    session: AsyncSession,
):
    i18n, lang = _get_i18n_from_data(i18n_data)
    if not i18n or not lang or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return

    _ = lambda key, **kwargs: _t(i18n, lang, key, **kwargs)

    try:
        parts = callback.data.split(":")
        promo_id = int(parts[1])
        page = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer(
            _("admin_promo_not_found", default="Promo not found."),
            show_alert=True,
        )
        return

    page_size = settings.LOGS_PAGE_SIZE

    promo = await promo_code_dal.get_promo_code_by_id(session, promo_id)
    if not promo:
        await callback.answer(
            _("admin_promo_not_found", default="Promo not found."),
            show_alert=True,
        )
        return

    total_activations = await promo_code_dal.count_promo_activations_by_code_id(
        session, promo_id
    )
    activations = await promo_code_dal.get_promo_activations_by_code_id(
        session, promo_id, limit=page_size, offset=page * page_size
    )

    builder = InlineKeyboardBuilder()

    if not activations:
        text = _(
            "admin_promo_no_activations",
            code=promo.code,
            default=f"No activations for {promo.code}",
        )
    else:
        header = _(
            "admin_promo_activations_header",
            code=promo.code,
            default=f"📋 Activations for promo code: {promo.code}\n\n",
        )
        items = []
        for a in activations:
            items.append(
                _(
                    "admin_promo_activation_item",
                    user_id=a.user_id,
                    date=a.activated_at.strftime("%d.%m.%Y %H:%M"),
                    default=f"👤 User ID: {a.user_id}\n📅 Date: {a.activated_at.strftime('%d.%m.%Y %H:%M')}\n",
                )
            )
        text = header + "\n".join(items)

    # Пагинация активаций
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️", callback_data=f"promo_activations:{promo_id}:{page - 1}"
            )
        )
    if (page + 1) * page_size < total_activations:
        nav_buttons.append(
            InlineKeyboardButton(
                text="➡️", callback_data=f"promo_activations:{promo_id}:{page + 1}"
            )
        )
    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_export_csv_button", default="📄 Export to CSV"),
            callback_data=f"promo_export:{promo_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=_("admin_promo_back_to_detail_button", default="⬅️ Back to promo"),
            callback_data=f"promo_detail:{promo_id}",
        )
    )

    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("promo_export:"))
async def promo_export_activations_handler(
    callback: types.CallbackQuery,
    i18n_data: Dict[str, Any],
    session: AsyncSession,
):
    i18n, lang = _get_i18n_from_data(i18n_data)
    if not i18n or not lang or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return

    _ = lambda key, **kwargs: _t(i18n, lang, key, **kwargs)
    export_lang = "en"

    try:
        promo_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(
            _("admin_promo_not_found", default="Promo not found."),
            show_alert=True,
        )
        return

    promo = await promo_code_dal.get_promo_code_by_id(session, promo_id)
    if not promo:
        await callback.answer(
            _("admin_promo_not_found", default="Promo not found."),
            show_alert=True,
        )
        return

    activations = await promo_code_dal.get_promo_activations_by_code_id(
        session, promo_id
    )
    if not activations:
        await callback.answer(
            _(
                "admin_promo_no_activations",
                code=promo.code,
                default="No activations",
            ),
            show_alert=True,
        )
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["User ID", "Activation Date"])
    for act in activations:
        writer.writerow(
            [
                act.user_id,
                act.activated_at.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )

    output.seek(0)
    file = types.BufferedInputFile(
        output.getvalue().encode("utf-8"),
        filename=f"promo_{promo.code}_activations.csv",
    )

    caption = i18n.gettext(
        export_lang,
        "admin_promo_export_caption",
        code=promo.code,
        default=f"📄 Activations for promo code {promo.code}",
    )

    await callback.message.answer_document(file, caption=caption)
    await callback.answer()


@router.callback_query(F.data == "promo_export_all")
async def promo_export_all_handler(
    callback: types.CallbackQuery,
    i18n_data: Dict[str, Any],
    session: AsyncSession,
):
    i18n, lang = _get_i18n_from_data(i18n_data)
    if not i18n or not lang or not callback.message:
        await callback.answer("Error processing request.", show_alert=True)
        return

    export_lang = "en"

    try:
        await callback.answer(
            i18n.gettext(
                export_lang,
                "admin_promo_export_all_generating",
                default="📄 Generating export...",
            ),
            show_alert=True,
        )

        all_promos = await promo_code_dal.get_all_promo_codes_with_details(
            session, limit=10000, offset=0
        )

        output = io.StringIO()
        writer = csv.writer(output)

        # Заголовки CSV (всегда EN)
        writer.writerow(
            [
                i18n.gettext(
                    export_lang,
                    "admin_promo_csv_code",
                    default="Code",
                ),
                i18n.gettext(
                    export_lang,
                    "admin_promo_csv_bonus_days",
                    default="Bonus days",
                ),
                i18n.gettext(
                    export_lang,
                    "admin_promo_csv_discount_percent",
                    default="Discount %",
                ),
                i18n.gettext(
                    export_lang,
                    "admin_promo_csv_discount_plan_months",
                    default="Discount plan months",
                ),
                i18n.gettext(
                    export_lang,
                    "admin_promo_csv_max_activations",
                    default="Max activations",
                ),
                i18n.gettext(
                    export_lang,
                    "admin_promo_csv_current_activations",
                    default="Current activations",
                ),
                i18n.gettext(
                    export_lang,
                    "admin_promo_csv_status",
                    default="Status",
                ),
                i18n.gettext(
                    export_lang,
                    "admin_promo_csv_is_active",
                    default="Is active",
                ),
                i18n.gettext(
                    export_lang,
                    "admin_promo_csv_valid_until",
                    default="Valid until",
                ),
                i18n.gettext(
                    export_lang,
                    "admin_promo_csv_created_at",
                    default="Created at",
                ),
                i18n.gettext(
                    export_lang,
                    "admin_promo_csv_created_by_admin_id",
                    default="Created by admin id",
                ),
            ]
        )

        for promo in all_promos:
            _status_emoji, status_text = get_promo_status_emoji_and_text(
                promo, i18n, export_lang
            )

            writer.writerow(
                [
                    promo.code,
                    promo.bonus_days if promo.bonus_days is not None else "",
                    promo.discount_percent
                    if promo.discount_percent is not None
                    else "",
                    promo.discount_plan_months
                    if promo.discount_plan_months is not None
                    else "",
                    promo.max_activations,
                    promo.current_activations,
                    status_text,
                    i18n.gettext(
                        export_lang,
                        "csv_yes",
                        default="Yes",
                    )
                    if promo.is_active
                    else i18n.gettext(
                        export_lang,
                        "csv_no",
                        default="No",
                    ),
                    promo.valid_until.strftime("%Y-%m-%d %H:%M:%S")
                    if promo.valid_until
                    else i18n.gettext(
                        export_lang,
                        "admin_promo_valid_indefinitely",
                        default="Indefinitely",
                    ),
                    promo.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if promo.created_at
                    else "N/A",
                    promo.created_by_admin_id or "N/A",
                ]
            )

        output.seek(0)
        filename = f"promo_codes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file = types.BufferedInputFile(
            output.getvalue().encode("utf-8-sig"), filename=filename
        )

        caption = i18n.gettext(
            export_lang,
            "admin_promo_export_all_caption",
            count=len(all_promos),
            default=f"📄 Exported {len(all_promos)} promo codes",
        )
        await callback.message.answer_document(file, caption=caption)

    except Exception:
        logging.exception("promo_export_all_handler error")
        await callback.answer("❌ Export error.", show_alert=True)


# =====================================================================
# УДАЛЕНИЕ ПРОМОКОДА
# =====================================================================

@router.callback_query(F.data.startswith("promo_delete:"))
async def promo_delete_handler(
    callback: types.CallbackQuery,
    i18n_data: Dict[str, Any],
    settings: Settings,
    session: AsyncSession,
):
    i18n, lang = _get_i18n_from_data(i18n_data)
    if not i18n or not lang or not callback.message:
        await callback.answer("Language service error.", show_alert=True)
        return

    _ = lambda key, **kwargs: _t(i18n, lang, key, **kwargs)

    try:
        promo_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(
            _("admin_promo_not_found", default="Promo not found."),
            show_alert=True,
        )
        return

    promo = await promo_code_dal.delete_promo_code(session, promo_id)
    if not promo:
        await callback.answer(
            _("admin_promo_not_found", default="Promo not found."),
            show_alert=True,
        )
        return

    await session.commit()

    await callback.answer(
        _(
            "admin_promo_deleted_success",
            code=promo.code,
            default=f"Promo {promo.code} deleted.",
        ),
        show_alert=True,
    )
    # после удаления возвращаемся на первую страницу списка
    await promo_management_handler(callback, i18n_data, settings, session, page=0)


# =====================================================================
# ХЕЛПЕР ДЛЯ ВНЕШНЕГО ВХОДА
# =====================================================================

async def manage_promo_codes_handler(
    callback: types.CallbackQuery,
    i18n_data: Dict[str, Any],
    settings: Settings,
    session: AsyncSession,
):
    """Внешняя точка входа из админ-панели."""
    await promo_management_handler(callback, i18n_data, settings, session)