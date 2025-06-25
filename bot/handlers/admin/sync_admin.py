import logging
from aiogram import Router, types, Bot
from aiogram.filters import Command
from typing import Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from config.settings import Settings
from bot.services.panel_api_service import PanelApiService

from db.dal import user_dal, subscription_dal, panel_sync_dal

from bot.middlewares.i18n import JsonI18n

router = Router(name="admin_sync_router")


@router.message(Command("sync"))
async def sync_command_handler(
    message_event: Union[types.Message, types.CallbackQuery],
    bot: Bot,
    settings: Settings,
    i18n_data: dict,
    panel_service: PanelApiService,
    session: AsyncSession,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n:
        logging.error("i18n missing in sync_command_handler")

        if isinstance(message_event, types.Message):
            await message_event.answer("Language error.")
        elif isinstance(message_event, types.CallbackQuery):
            await message_event.answer("Language error.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    target_chat_id = (
        message_event.chat.id
        if isinstance(message_event, types.Message)
        else (message_event.message.chat.id if message_event.message else None)
    )
    if not target_chat_id:
        logging.error("Sync handler: could not determine target_chat_id.")
        if isinstance(message_event, types.CallbackQuery):
            await message_event.answer("Error initiating sync.", show_alert=True)
        return

    if isinstance(message_event, types.Message):
        await message_event.answer(_("sync_started"))

    logging.info(f"Admin ({message_event.from_user.id}) triggered panel sync.")

    users_processed_count = 0
    users_synced_successfully = 0
    subscriptions_synced_count = 0
    sync_errors = []

    try:
        panel_users_data = await panel_service.get_all_panel_users()

        if panel_users_data is None:
            error_msg = "Failed to fetch users from panel or panel API issue."
            sync_errors.append(error_msg)
            await panel_sync_dal.update_panel_sync_status(session, "failed", error_msg)
            await session.commit()
            await bot.send_message(target_chat_id, _("sync_failed", details=error_msg))
            return

        if not panel_users_data:
            status_msg = "No users found in the panel to sync."
            await panel_sync_dal.update_panel_sync_status(
                session, "success", status_msg, 0, 0
            )
            await session.commit()
            await bot.send_message(
                target_chat_id,
                _("sync_completed", status="Success", details=status_msg),
            )
            return

        total_panel_users = len(panel_users_data)
        logging.info(f"Starting sync for {total_panel_users} panel users.")

        for panel_user_dict in panel_users_data:
            users_processed_count += 1
            panel_uuid = panel_user_dict.get("uuid")
            telegram_id_from_panel_str = panel_user_dict.get("telegramId")
            panel_username = panel_user_dict.get("username")

            if not panel_uuid:
                logging.warning(
                    f"Sync: Panel user data missing 'uuid'. Data: {str(panel_user_dict)[:200]}. Skipping."
                )
                sync_errors.append(
                    f"Panel user data (username: {panel_username or 'N/A'}) missing UUID."
                )
                continue

            telegram_id_from_panel: Optional[int] = None
            if telegram_id_from_panel_str:
                try:
                    telegram_id_from_panel = int(telegram_id_from_panel_str)
                except ValueError:
                    logging.warning(
                        f"Sync: Panel user {panel_uuid} (username: {panel_username}) has invalid 'telegramId': {telegram_id_from_panel_str}. Skipping TG ID based sync."
                    )

            if not telegram_id_from_panel:

                logging.info(
                    f"Sync: Panel user {panel_uuid} (username: {panel_username}) has no valid 'telegramId'. Skipping full sync for this user."
                )

                continue

            bot_user = await user_dal.get_user_by_id(session, telegram_id_from_panel)
            if not bot_user:
                user_data_to_create = {
                    "user_id": telegram_id_from_panel,
                    "username": panel_username,
                    "panel_user_uuid": panel_uuid,
                    "language_code": settings.DEFAULT_LANGUAGE,
                    "registration_date": (
                        datetime.fromisoformat(
                            panel_user_dict["createdAt"].replace("Z", "+00:00")
                        )
                        if panel_user_dict.get("createdAt")
                        else datetime.now(timezone.utc)
                    ),
                }
                bot_user = await user_dal.create_user(session, user_data_to_create)
                logging.info(
                    f"Sync: Created new local user {telegram_id_from_panel} from panel data {panel_uuid}."
                )
            else:
                if bot_user.panel_user_uuid != panel_uuid:
                    if bot_user.panel_user_uuid is not None:
                        logging.warning(
                            f"Sync: Local user {telegram_id_from_panel} was linked to {bot_user.panel_user_uuid}, panel now gives {panel_uuid}. Updating."
                        )

                    conflicting_user = await user_dal.get_user_by_panel_uuid(
                        session, panel_uuid
                    )
                    if (
                        conflicting_user
                        and conflicting_user.user_id != telegram_id_from_panel
                    ):
                        sync_errors.append(
                            f"Panel UUID {panel_uuid} for TG {telegram_id_from_panel} already linked to another TG user {conflicting_user.user_id}."
                        )
                        logging.error(sync_errors[-1])
                        continue

                    await user_dal.update_user(
                        session,
                        telegram_id_from_panel,
                        {"panel_user_uuid": panel_uuid, "username": panel_username},
                    )
                    logging.info(
                        f"Sync: Updated panel_uuid for local user {telegram_id_from_panel} to {panel_uuid}."
                    )

            panel_sub_link_id = panel_user_dict.get(
                "subscriptionUuid"
            ) or panel_user_dict.get("shortUuid")
            if panel_sub_link_id:
                end_date_str = panel_user_dict.get("expireAt")
                start_date_str = panel_user_dict.get("createdAt")

                if end_date_str:
                    try:
                        end_date_obj = datetime.fromisoformat(
                            end_date_str.replace("Z", "+00:00")
                        )
                        start_date_obj = (
                            datetime.fromisoformat(
                                start_date_str.replace("Z", "+00:00")
                            )
                            if start_date_str
                            else datetime.now(timezone.utc)
                        )

                        status_from_panel = panel_user_dict.get(
                            "status", "UNKNOWN"
                        ).upper()
                        is_active_flag = (
                            1
                            if status_from_panel == "ACTIVE"
                            and end_date_obj > datetime.now(timezone.utc)
                            else 0
                        )

                        sub_payload = {
                            "user_id": telegram_id_from_panel,
                            "panel_user_uuid": panel_uuid,
                            "panel_subscription_uuid": panel_sub_link_id,
                            "start_date": start_date_obj,
                            "end_date": end_date_obj,
                            "is_active": is_active_flag,
                            "status_from_panel": status_from_panel,
                            "traffic_limit_bytes": panel_user_dict.get(
                                "trafficLimitBytes"
                            ),
                            "traffic_used_bytes": panel_user_dict.get(
                                "usedTrafficBytes"
                            ),
                        }

                        await subscription_dal.deactivate_other_active_subscriptions(
                            session, panel_uuid, panel_sub_link_id
                        )
                        await subscription_dal.upsert_subscription(session, sub_payload)
                        subscriptions_synced_count += 1
                        users_synced_successfully += 1
                    except ValueError as e_date:
                        logging.warning(
                            f"Sync: Bad date format for panel user {panel_uuid} (TG ID: {telegram_id_from_panel}). Sub data: {str(panel_user_dict)[:100]}. Error: {e_date}"
                        )
                        sync_errors.append(
                            f"Bad date for panel user {panel_uuid} (TG ID: {telegram_id_from_panel})."
                        )
                    except Exception as e_sub_sync:
                        logging.error(
                            f"Sync: Error syncing subscription for panel user {panel_uuid} (TG ID: {telegram_id_from_panel}): {e_sub_sync}",
                            exc_info=True,
                        )
                        sync_errors.append(
                            f"Sub sync error for panel user {panel_uuid} (TG ID: {telegram_id_from_panel})."
                        )
                else:
                    logging.warning(
                        f"Sync: Panel user {panel_uuid} (TG ID: {telegram_id_from_panel}) has sub link but no expireAt date. Skipping subscription sync."
                    )
            else:

                await subscription_dal.deactivate_other_active_subscriptions(
                    session, panel_uuid, None
                )
                logging.info(
                    f"Sync: Panel user {panel_uuid} (TG ID: {telegram_id_from_panel}) has no subscription link on panel. Deactivated local subs if any."
                )
                users_synced_successfully += 1

            if users_processed_count % 20 == 0:
                logging.info(
                    f"Sync progress: {users_processed_count}/{total_panel_users} users processed from panel."
                )

        panel_uuid_set = {u.get("uuid") for u in panel_users_data if u.get("uuid")}
        local_users_with_uuid = await user_dal.get_all_users_with_panel_uuid(session)
        for local_user in local_users_with_uuid:
            if local_user.panel_user_uuid not in panel_uuid_set:
                await subscription_dal.deactivate_other_active_subscriptions(
                    session, local_user.panel_user_uuid, None
                )
                await user_dal.update_user(
                    session, local_user.user_id, {"panel_user_uuid": None}
                )
                logging.info(
                    f"Sync: Local user {local_user.user_id} with panel UUID {local_user.panel_user_uuid} not found on panel. Cleared local data."
                )

        status_msg_key = "sync_completed_details"
        final_status_type = "success"

        if sync_errors:
            final_status_type = "partial_success"
            status_msg_key = "sync_completed_with_errors_details"
            error_preview = "\n".join(sync_errors[:3])
            details_for_db = f"Users processed: {users_processed_count}. Subs synced: {subscriptions_synced_count}. Errors: {len(sync_errors)}. First few: {error_preview}"
        else:
            details_for_db = f"Successfully processed {users_processed_count} users. Synced {subscriptions_synced_count} subscriptions."

        await panel_sync_dal.update_panel_sync_status(
            session,
            final_status_type,
            details_for_db,
            users_processed_count,
            subscriptions_synced_count,
        )
        await session.commit()

        final_user_message = _(
            status_msg_key,
            total_checked=total_panel_users,
            users_synced=users_synced_successfully,
            subs_synced=subscriptions_synced_count,
            errors_count=len(sync_errors),
            error_details_preview=(
                error_preview if sync_errors else _("no_errors_placeholder")
            ),
        )
        await bot.send_message(target_chat_id, final_user_message)

    except Exception as e_sync_global:
        await session.rollback()
        logging.error(
            f"Global error during /sync command: {e_sync_global}", exc_info=True
        )
        error_detail_for_db = (
            f"An unexpected error occurred during sync: {str(e_sync_global)[:200]}"
        )
        await panel_sync_dal.update_panel_sync_status(
            session,
            "failed",
            error_detail_for_db,
            users_processed_count,
            subscriptions_synced_count,
        )

        await bot.send_message(
            target_chat_id, _("sync_failed", details=error_detail_for_db)
        )


@router.message(Command("syncstatus"))
async def sync_status_command_handler(
    message: types.Message, i18n_data: dict, settings: Settings, session: AsyncSession
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n:
        await message.answer("Language error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    status_record_model = await panel_sync_dal.get_panel_sync_status(session)
    response_text = ""
    if status_record_model:
        last_time_val = status_record_model.last_sync_time
        last_time_str = (
            last_time_val.strftime("%Y-%m-%d %H:%M:%S UTC") if last_time_val else "N/A"
        )

        details_val = status_record_model.details
        details_str = (
            (details_val[:200] + "...")
            if details_val and len(details_val) > 200
            else (details_val or "N/A")
        )

        response_text = (
            f"<b>{_('admin_stats_last_sync_header')}</b>\n"
            f"  {_('admin_stats_sync_time')}: {last_time_str}\n"
            f"  {_('admin_stats_sync_status')}: {status_record_model.status}\n"
            f"  {_('admin_stats_sync_users_processed')}: {status_record_model.users_processed_from_panel}\n"
            f"  {_('admin_stats_sync_subs_synced')}: {status_record_model.subscriptions_synced}\n"
            f"  {_('admin_stats_sync_details_label')}: {details_str}"
        )
    else:
        response_text = _("admin_sync_status_never_run")

    await message.answer(response_text, parse_mode="HTML")
