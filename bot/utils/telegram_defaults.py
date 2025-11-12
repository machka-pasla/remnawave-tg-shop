"""Utilities with shared defaults for Telegram messages."""

from __future__ import annotations

from typing import Any, Dict

from aiogram.enums import ParseMode
from aiogram.types import LinkPreviewOptions


_TEXT_CONTENT_TYPES = {"text"}
_CAPTION_CONTENT_TYPES = {"photo", "video", "animation", "document", "audio", "voice"}


def apply_default_formatting(content_type: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Return kwargs extended with default parse mode and link preview options.

    For text messages the HTML parse mode is enforced and link previews are
    disabled unless explicitly overridden. For captionable media only the parse
    mode is enforced. When callers pass explicit values they are preserved.
    """

    prepared = dict(kwargs)

    if content_type in _TEXT_CONTENT_TYPES:
        prepared.setdefault("parse_mode", ParseMode.HTML)
        if (
            "link_preview_options" not in prepared
            and "disable_web_page_preview" not in prepared
        ):
            prepared["link_preview_options"] = LinkPreviewOptions(is_disabled=True)
    elif content_type in _CAPTION_CONTENT_TYPES:
        prepared.setdefault("parse_mode", ParseMode.HTML)

    return prepared

