import logging
from typing import Callable, Dict, Any, Awaitable, Optional

from aiogram import BaseMiddleware
from aiogram.types import Update, User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import user_dal
from bot.utils.text_sanitizer import sanitize_username, sanitize_display_name, username_for_display


class ProfileSyncMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        session: AsyncSession = data.get("session")
        tg_user: Optional[TgUser] = data.get("event_from_user")

        if session and tg_user:
            try:
                db_user = await user_dal.get_user_by_id(session, tg_user.id)
                if db_user:
                    update_payload: Dict[str, Any] = {}
                    sanitized_username = sanitize_username(tg_user.username)
                    sanitized_first_name = sanitize_display_name(tg_user.first_name)
                    sanitized_last_name = sanitize_display_name(tg_user.last_name)

                    if db_user.username != sanitized_username:
                        update_payload["username"] = sanitized_username
                    if db_user.first_name != sanitized_first_name:
                        update_payload["first_name"] = sanitized_first_name
                    if db_user.last_name != sanitized_last_name:
                        update_payload["last_name"] = sanitized_last_name

                    if update_payload:
                        await user_dal.update_user(session, tg_user.id, update_payload)
                        logging.info(
                            f"ProfileSyncMiddleware: Updated user {tg_user.id} profile fields: {list(update_payload.keys())}"
                        )

                        # Also update description on panel if linked
                        try:
                            panel_service = data.get("panel_service")
                            if panel_service and db_user.panel_user_uuid:
                                description_text = "\n".join([
                                    username_for_display(tg_user.username, with_at=False) if sanitized_username is not None else "",
                                    sanitized_first_name or "",
                                    sanitized_last_name or "",
                                ]).strip()
                                await panel_service.update_user_details_on_panel(
                                    db_user.panel_user_uuid,
                                    {"description": description_text},
                                )
                        except Exception as e_upd_desc:
                            logging.warning(
                                f"ProfileSyncMiddleware: Failed to update panel description for user {tg_user.id}: {e_upd_desc}"
                            )
            except Exception as e:
                logging.error(
                    f"ProfileSyncMiddleware: Failed to sync profile for user {getattr(tg_user, 'id', 'N/A')}: {e}",
                    exc_info=True,
                )

        return await handler(event, data)

