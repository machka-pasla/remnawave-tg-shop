import logging
from pathlib import Path
from typing import Optional

from aiogram import types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InputMediaPhoto, LinkPreviewOptions


MENU_IMAGES_ROOT = Path("/app/bot/static/images")


async def update_menu_message(
    message: Optional[types.Message],
    text: str,
    image_filename: Optional[str],
    reply_markup=None,
    parse_mode: Optional[str] = ParseMode.HTML,
    disable_link_preview: bool = True,
) -> bool:
    """Update a menu message with an image background when possible.

    Returns True if an image was used as the background, False if the text fallback
    was used or the update failed.
    """

    if not message:
        logging.error("update_menu_message called without a message instance")
        return False

    link_preview_options = None
    if disable_link_preview:
        link_preview_options = LinkPreviewOptions(is_disabled=True)

    if image_filename:
        image_path = MENU_IMAGES_ROOT / image_filename
        if image_path.is_file():
            try:
                media = InputMediaPhoto(
                    media=FSInputFile(str(image_path)),
                    caption=text,
                    parse_mode=parse_mode,
                )
                await message.edit_media(media=media, reply_markup=reply_markup)
                return True
            except TelegramBadRequest as media_error:
                logging.warning(
                    "Failed to edit media for menu using %s: %s",
                    image_path,
                    media_error,
                )
                if message.photo:
                    try:
                        await message.edit_caption(
                            caption=text,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode,
                        )
                        return True
                    except TelegramBadRequest as caption_error:
                        logging.warning(
                            "Failed to edit caption for menu image %s: %s",
                            image_path,
                            caption_error,
                        )
                    except Exception as caption_error:
                        logging.error(
                            "Unexpected error while editing caption for %s: %s",
                            image_path,
                            caption_error,
                        )
            except Exception as media_error:
                logging.error(
                    "Unexpected error while editing menu media %s: %s",
                    image_path,
                    media_error,
                )
        else:
            logging.warning("Menu image file not found: %s", image_path)

    try:
        await message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            link_preview_options=link_preview_options,
        )
    except TelegramBadRequest as text_error:
        if "message is not modified" in str(text_error).lower():
            logging.debug("Menu text not modified for message %s", message.message_id)
        else:
            logging.error("Failed to edit menu text: %s", text_error)
    except Exception as text_error:
        logging.error("Unexpected error while editing menu text: %s", text_error)
    return False
