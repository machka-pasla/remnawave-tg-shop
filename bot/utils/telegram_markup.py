from typing import Optional

from aiogram import types

PROFILE_BUTTON_ERROR_CODES = ("BUTTON_USER_INVALID", "BUTTON_USER_PRIVACY_RESTRICTED")
TG_USER_LINK_PREFIX = "tg://user?id="


def remove_profile_link_buttons(
    markup: Optional[types.InlineKeyboardMarkup],
) -> Optional[types.InlineKeyboardMarkup]:
    """Remove buttons that point to tg://user links to avoid privacy-related errors."""
    inline_keyboard = getattr(markup, "inline_keyboard", None)
    if not markup or not inline_keyboard:
        return None

    cleaned_rows = []
    for row in inline_keyboard:
        filtered_row = [
            button
            for button in row
            if not (
                getattr(button, "url", None)
                and str(button.url).startswith(TG_USER_LINK_PREFIX)
            )
        ]
        if filtered_row:
            cleaned_rows.append(filtered_row)

    if not cleaned_rows:
        return None

    return types.InlineKeyboardMarkup(inline_keyboard=cleaned_rows)


def is_profile_link_error(exc: BaseException) -> bool:
    """Return True if Telegram rejected markup because of profile link buttons."""
    message = getattr(exc, "message", "") or str(exc)
    return any(code in message for code in PROFILE_BUTTON_ERROR_CODES)
