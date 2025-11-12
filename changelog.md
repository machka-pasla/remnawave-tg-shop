`./config/settings.py:1` - Added Telegram ID encryption configuration surface.
- Read TELEGRAM_ID_ENCRYPTION, ECDC_* parameters, updated admin/log/channel parsing, and enforced runtime validation of missing secrets.

`./main.py:10` - Initialized the IdBridge during startup.
- Ensures encryption services are ready before bootstrapping the bot.

`./bot/utils/id_bridge.py:1` - Introduced central IdBridge adapter and helpers.
- Provides UID/UGID ↔ TID conversion, identity helpers, and admin recipient resolution utilities.

`./bot/app/controllers/dispatcher_controller.py:1` - Exposed IdBridge through dispatcher context.
- Makes the adapter available to handlers and middlewares.

`./bot/filters/admin_filter.py:1` - Made admin filter IdBridge-aware.
- Accepts UID lists and resolves incoming Telegram IDs before matching.

`./bot/routers.py:8` - Wired IdBridge into admin router filter construction.
- Prevents mismatches between UID lists and Telegram update IDs.

`./bot/middlewares/ban_check_middleware.py:11` - Reworked admin checks and logging to rely on IdBridge.
- Avoids leaking raw Telegram usernames while logging UID references.

`./bot/middlewares/channel_subscription.py:1` - Normalized required-channel configuration via IdBridge.
- Converts UGID strings to TGIDs on demand and respects UID-based admin bypassing.

`./bot/middlewares/action_logger_middleware.py:11` - Masked PII in action logs and log metadata.
- Stores UID references when encryption is enabled and skips profile fields.

`./bot/handlers/inline_mode.py:11` - Updated inline admin detection and error logging to use IdBridge-derived identifiers.
- Prevents UID-configured admins from being ignored.

`./bot/handlers/admin/user_management.py:1` - Centralized admin authorization checks through IdBridge helpers.
- Keeps destructive actions gated when ADMIN_IDS contain UIDs.

`./bot/handlers/user/start.py:1` - Swapped direct ADMIN_IDS usage for IdBridge helper.
- Maintains correct admin gating under UID mode.

`./bot/services/notification_service.py:1` - Routed admin/log destinations through IdBridge and masked profile data.
- Sends notifications using resolved TGIDs while displaying UID references only.

`./bot/services/subscription_service.py:1` - Reused IdBridge helpers when notifying admins about panel sync issues.
- Presents UID references and resolves recipient chat IDs safely.

`./db/models.py:1` - Added uid column to users and introduced uid_rotation_journal table.
- Prepares the schema for dual storage and future UID rotation tracking.

`./db/dal/user_dal.py:1` - Added UID lookup helper and ensured create_user records the new uid field.
- Enables DAL consumers to persist/read encrypted identifiers.

`./db/migrator.py:1` - Registered migration 0002 to add uid storage plus rotation journal table.
- Handles schema evolution for UID rollout.
