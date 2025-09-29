import logging
from aiogram import Router, types, Bot
from aiogram.filters import Command
from typing import Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from config.settings import Settings
from bot.services.panel_api_service import PanelApiService
from bot.services.notification_service import NotificationService

from db.dal import user_dal, subscription_dal, panel_sync_dal

from bot.middlewares.i18n import JsonI18n

router = Router(name="admin_sync_router")


async def perform_sync(panel_service: PanelApiService, session: AsyncSession, 
                      settings: Settings, i18n_instance: JsonI18n) -> dict:
    """
    Perform panel synchronization and return results
    Returns dict with status, details, and sync statistics
    """
    panel_records_checked = 0
    users_found_in_db = 0
    users_updated = 0
    subscriptions_synced_count = 0
    sync_errors = []
    
    # Additional counters for detailed logging
    users_without_telegram_id = 0
    users_not_found_in_db = 0
    users_created = 0
    users_uuid_updated = 0
    subscriptions_created = 0
    subscriptions_updated = 0

    try:
        panel_users_data = await panel_service.get_all_panel_users()

        if panel_users_data is None:
            error_msg = "Failed to fetch users from panel or panel API issue."
            sync_errors.append(error_msg)
            await panel_sync_dal.update_panel_sync_status(session, "failed", error_msg)
            await session.commit()
            return {"status": "failed", "details": error_msg, "errors": sync_errors}

        if not panel_users_data:
            status_msg = "No users found in the panel to sync."
            await panel_sync_dal.update_panel_sync_status(
                session, "success", status_msg, 0, 0
            )
            await session.commit()
            return {"status": "success", "details": status_msg, "users_synced": 0, "subs_synced": 0}

        total_panel_users = len(panel_users_data)
        logging.info(f"Starting sync for {total_panel_users} panel users.")

        for panel_user_dict in panel_users_data:
            try:
                panel_records_checked += 1
                panel_uuid = panel_user_dict.get("uuid")
                panel_subscription_uuid = panel_user_dict.get("subscriptionUuid") or panel_user_dict.get("shortUuid")
                telegram_id_from_panel = panel_user_dict.get("telegramId")

                if not panel_uuid:
                    sync_errors.append(f"Panel user missing UUID: {panel_user_dict}")
                    logging.warning(f"Skipping panel user without UUID: {panel_user_dict}")
                    continue

                # Track users without telegram ID
                if not telegram_id_from_panel:
                    users_without_telegram_id += 1

                # Try to find existing user in local DB
                existing_user = None
                
                # First, try to find by telegram ID if available
                if telegram_id_from_panel:
                    existing_user = await user_dal.get_user_by_id(session, telegram_id_from_panel)
                    if existing_user:
                        logging.debug(f"Found user by telegramId {telegram_id_from_panel}")
                
                # If not found by telegram ID, try to find by panel UUID
                if not existing_user:
                    existing_user = await user_dal.get_user_by_panel_uuid(session, panel_uuid)
                    if existing_user:
                        logging.info(f"Found user by panel UUID {panel_uuid}, telegramId: {existing_user.user_id}")
                        # Update telegram ID if it was missing in panel data but we have local user
                        if telegram_id_from_panel and existing_user.user_id != telegram_id_from_panel:
                            logging.warning(f"TelegramId mismatch: panel={telegram_id_from_panel}, local={existing_user.user_id}")
                
                if not existing_user:
                    users_not_found_in_db += 1
                    if telegram_id_from_panel:
                        # Create new user if they have telegram_id
                        try:
                            user_data = {
                                "user_id": telegram_id_from_panel,
                                "username": None,  # Username will be updated when user interacts with bot
                                "first_name": None,  # Panel doesn't provide this info
                                "last_name": None,   # Panel doesn't provide this info
                                "language_code": "ru",  # Default language
                                "panel_user_uuid": panel_uuid,
                                "is_banned": False,
                                "referred_by_id": None
                            }
                            
                            new_user, was_created = await user_dal.create_user(session, user_data)
                            if was_created:
                                users_created += 1
                                logging.info(f"Created new user {telegram_id_from_panel} from panel sync with UUID {panel_uuid}")
                            
                            existing_user = new_user
                            
                        except Exception as e_create:
                            sync_errors.append(f"Error creating user {telegram_id_from_panel}: {str(e_create)}")
                            logging.error(f"Error creating user {telegram_id_from_panel}: {e_create}")
                            continue
                    else:
                        logging.debug(f"Panel user with UUID {panel_uuid} (no telegramId) not found in local DB - skipping")
                        continue

                # User found in local DB
                users_found_in_db += 1
                user_was_updated = False

                # Get the actual user_id for subscription operations
                actual_user_id = existing_user.user_id

                # Update panel UUID if different
                if existing_user.panel_user_uuid != panel_uuid:
                    existing_user.panel_user_uuid = panel_uuid
                    user_was_updated = True
                    users_uuid_updated += 1
                    logging.info(f"Updated panel UUID for user {actual_user_id}: {panel_uuid}")

                # Ensure panel description contains Telegram fields
                try:
                    if panel_uuid and existing_user:
                        description_text = "\n".join([
                            existing_user.username or "",
                            existing_user.first_name or "",
                            existing_user.last_name or "",
                        ])
                        # Update description only when it differs from the current one on panel
                        current_panel_description = (panel_user_dict.get("description") or "").strip()
                        desired_description = description_text.strip()
                        if desired_description and desired_description != current_panel_description:
                            await panel_service.update_user_details_on_panel(
                                panel_uuid, {"description": description_text}
                            )
                except Exception as e_desc:
                    logging.warning(
                        f"Sync: Failed to update description for panel user {panel_uuid} (tg {actual_user_id}): {e_desc}"
                    )

                # Sync subscription data
                panel_expire_at_iso = panel_user_dict.get("expireAt")
                panel_status = panel_user_dict.get("status", "UNKNOWN")
                
                if panel_expire_at_iso:
                    try:
                        panel_expire_at = datetime.fromisoformat(
                            panel_expire_at_iso.replace("Z", "+00:00")
                        )
                        
                        # Prefer syncing by concrete subscription UUID (shortUuid/subscriptionUuid)
                        subscription_uuid_from_panel = (
                            panel_user_dict.get("subscriptionUuid")
                            or panel_user_dict.get("shortUuid")
                        )

                        if subscription_uuid_from_panel:
                            # Try to find subscription by its panel_subscription_uuid first (idempotent)
                            existing_sub_by_uuid = (
                                await subscription_dal.get_subscription_by_panel_subscription_uuid(
                                    session, subscription_uuid_from_panel
                                )
                            )

                            if existing_sub_by_uuid:
                                # Atomic update of all relevant fields
                                await subscription_dal.update_subscription(
                                    session,
                                    existing_sub_by_uuid.subscription_id,
                                    {
                                        "user_id": actual_user_id,
                                        "panel_user_uuid": panel_uuid,
                                        "end_date": panel_expire_at,
                                        "is_active": panel_status == "ACTIVE",
                                        "status_from_panel": panel_status,
                                    },
                                )
                                subscriptions_synced_count += 1
                                subscriptions_updated += 1
                                user_was_updated = True
                                logging.info(
                                    f"Synced existing subscription {existing_sub_by_uuid.subscription_id} for user {actual_user_id}: expires {panel_expire_at}, status {panel_status}"
                                )
                            else:
                                # Create a new subscription only when we have a concrete subscription UUID
                                sub_payload = {
                                    "user_id": actual_user_id,
                                    "panel_user_uuid": panel_uuid,
                                    "panel_subscription_uuid": subscription_uuid_from_panel,
                                    # Do not guess precise start_date from panel; keep nullable
                                    "start_date": None,
                                    "end_date": panel_expire_at,
                                    "duration_months": None,
                                    "is_active": panel_status == "ACTIVE",
                                    "status_from_panel": panel_status,
                                    "traffic_limit_bytes": settings.user_traffic_limit_bytes,
                                }
                                created_sub = await subscription_dal.upsert_subscription(
                                    session, sub_payload
                                )
                                subscriptions_synced_count += 1
                                subscriptions_created += 1
                                user_was_updated = True
                                logging.info(
                                    f"Created subscription {created_sub.subscription_id} for user {actual_user_id} by panel_sub_uuid {subscription_uuid_from_panel}"
                                )
                        else:
                            # No subscription UUID from panel: only update an already active subscription for this user/panel UUID
                            active_sub = await subscription_dal.get_active_subscription_by_user_id(
                                session, actual_user_id, panel_uuid
                            )
                            if active_sub:
                                await subscription_dal.update_subscription(
                                    session,
                                    active_sub.subscription_id,
                                    {
                                        "end_date": panel_expire_at,
                                        "is_active": panel_status == "ACTIVE",
                                        "status_from_panel": panel_status,
                                    },
                                )
                                subscriptions_synced_count += 1
                                subscriptions_updated += 1
                                user_was_updated = True
                                logging.info(
                                    f"Updated active subscription {active_sub.subscription_id} for user {actual_user_id}: expires {panel_expire_at}, status {panel_status}"
                                )
                            else:
                                # Without a concrete subscription UUID we avoid creating new records to keep sync idempotent
                                logging.debug(
                                    f"No subscriptionUuid for panel user {panel_uuid}; skipped creation for user {actual_user_id}"
                                )
                            
                    except Exception as e:
                        sync_errors.append(f"Error syncing subscription for user {actual_user_id}: {str(e)}")
                        logging.error(f"Error syncing subscription for user {actual_user_id}: {e}")

                if user_was_updated:
                    users_updated += 1
                            
            except Exception as e_user:
                sync_errors.append(f"Error processing panel user {panel_user_dict.get('uuid', 'unknown')}: {str(e_user)}")
                logging.error(f"Error syncing user: {e_user}")

        # Update sync status
        status = "completed_with_errors" if sync_errors else "completed"
        # Build additional stats
        default_lang = settings.DEFAULT_LANGUAGE
        additional_stats = ""
        if users_without_telegram_id > 0:
            additional_stats += i18n_instance.gettext(default_lang, "admin_sync_no_telegram_id", count=users_without_telegram_id)
        if users_not_found_in_db > 0:
            additional_stats += i18n_instance.gettext(default_lang, "admin_sync_not_found_in_db", count=users_not_found_in_db)
        if sync_errors:
            additional_stats += i18n_instance.gettext(default_lang, "admin_sync_errors", count=len(sync_errors))

        # Build full details using localization
        details = i18n_instance.gettext(default_lang, "admin_sync_details", 
            panel_records_checked=panel_records_checked,
            users_found_in_db=users_found_in_db,
            users_created=users_created,
            users_updated=users_updated,
            subscriptions_synced_count=subscriptions_synced_count,
            subscriptions_created=subscriptions_created,
            subscriptions_updated=subscriptions_updated,
            additional_stats=additional_stats
        )

        await panel_sync_dal.update_panel_sync_status(
            session, status, details, panel_records_checked, subscriptions_synced_count
        )
        await session.commit()

        # Detailed logging summary
        logging.info(f"Sync completed - Summary:")
        logging.info(f"  Panel records checked: {panel_records_checked}")
        logging.info(f"  Users without telegramId: {users_without_telegram_id}")
        logging.info(f"  Users not found in local DB: {users_not_found_in_db}")
        logging.info(f"  Users found in local DB: {users_found_in_db}")
        logging.info(f"  Users created: {users_created}")
        logging.info(f"  Users with UUID updated: {users_uuid_updated}")
        logging.info(f"  Users updated overall: {users_updated}")
        logging.info(f"  Subscriptions total synced: {subscriptions_synced_count}")
        logging.info(f"  Subscriptions created: {subscriptions_created}")
        logging.info(f"  Subscriptions updated: {subscriptions_updated}")
        logging.info(f"  Sync errors: {len(sync_errors)}")

        return {
            "status": status,
            "details": details,
            "users_processed": panel_records_checked,
            "users_synced": users_found_in_db,
            "users_created": users_created,
            "subs_synced": subscriptions_synced_count,
            "errors": sync_errors
        }

    except Exception as e_sync_global:
        await session.rollback()
        logging.error(f"Global error during sync: {e_sync_global}", exc_info=True)
        error_detail = f"Unexpected error during sync: {str(e_sync_global)}"
        
        await panel_sync_dal.update_panel_sync_status(
            session, "failed", error_detail, panel_records_checked, subscriptions_synced_count
        )
        
        return {"status": "failed", "details": error_detail, "errors": [str(e_sync_global)]}


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
        await message_event.answer(_("sync_started_simple"))

    logging.info(f"Admin ({message_event.from_user.id}) triggered panel sync.")

    # Use the extracted perform_sync function
    try:
        sync_result = await perform_sync(panel_service, session, settings, i18n)
        
        status = sync_result.get("status")
        details = sync_result.get("details", "No details available")
        errors = sync_result.get("errors", [])
        
        # Simple confirmation message to admin
        if status == "failed":
            await bot.send_message(target_chat_id, _("sync_failed_simple"))
        elif status == "completed_with_errors":
            await bot.send_message(target_chat_id, _("sync_errors_simple", errors_count=len(errors)))
        else:
            await bot.send_message(target_chat_id, _("sync_success_simple"))
        
        # Send notification to log channel with proper thread handling
        try:
            notification_service = NotificationService(bot, settings, i18n)
            await notification_service.notify_panel_sync(
                status, details,
                sync_result.get("users_processed", 0),
                sync_result.get("subs_synced", 0)
            )
        except Exception as e_notification:
            logging.error(f"Failed to send sync notification: {e_notification}")
            
    except Exception as e_sync_global:
        logging.error(f"Global error during /sync command: {e_sync_global}", exc_info=True)
        await bot.send_message(target_chat_id, _("sync_critical_error"))
        
        # Send notification to log channel about failure
        try:
            notification_service = NotificationService(bot, settings, i18n)
            await notification_service.notify_panel_sync(
                "failed", str(e_sync_global), 0, 0
            )
        except Exception as e_notification:
            logging.error(f"Failed to send sync failure notification: {e_notification}")


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
        details_str = details_val or "N/A"

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