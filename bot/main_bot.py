import logging
import asyncio
from typing import Callable, Dict, Any, Awaitable, Optional

from aiogram import Bot, Dispatcher, BaseMiddleware, Router, F
from aiogram.types import (
    Update,
    MenuButtonDefault,
    MenuButtonWebApp,
    WebAppInfo,
    BotCommand,
)
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from bot.services.panel_webhook_service import PanelWebhookService, panel_webhook_route
from sqlalchemy.orm import sessionmaker

from config.settings import Settings

from db.database_setup import init_db_connection

from bot.middlewares.i18n import I18nMiddleware, get_i18n_instance, JsonI18n
from bot.middlewares.ban_check_middleware import BanCheckMiddleware
from bot.middlewares.action_logger_middleware import ActionLoggerMiddleware

from bot.handlers.user import user_router_aggregate
from bot.handlers.admin import admin_router_aggregate
from bot.filters.admin_filter import AdminFilter

from bot.services.yookassa_service import YooKassaService
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service import SubscriptionService
from bot.services.referral_service import ReferralService
from bot.services.promo_code_service import PromoCodeService
from bot.services.stars_service import StarsService
from bot.services.tribute_service import TributeService, tribute_webhook_route
from bot.services.crypto_pay_service import CryptoPayService, cryptopay_webhook_route

from bot.handlers.user import payment as user_payment_webhook_module


class DBSessionMiddleware(BaseMiddleware):

    def __init__(self, async_session_factory: sessionmaker):
        super().__init__()
        self.async_session_factory = async_session_factory

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        if self.async_session_factory is None:
            logging.critical("DBSessionMiddleware: async_session_factory is None!")
            raise RuntimeError(
                "async_session_factory not provided to DBSessionMiddleware"
            )

        async with self.async_session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)

                await session.commit()
                return result
            except Exception:
                await session.rollback()
                logging.error(
                    "DBSessionMiddleware: Exception caused rollback.", exc_info=True
                )
                raise


async def register_all_routers(dp: Dispatcher, settings: Settings):
    dp.include_router(user_router_aggregate)

    admin_main_router = Router(name="admin_main_filtered_router")
    admin_filter_instance = AdminFilter(admin_ids=settings.ADMIN_IDS)

    admin_main_router.message.filter(admin_filter_instance)
    admin_main_router.callback_query.filter(admin_filter_instance)

    admin_main_router.include_router(admin_router_aggregate)

    dp.include_router(admin_main_router)
    logging.info("All application routers registered.")


async def on_startup_configured(dispatcher: Dispatcher):
    bot: Bot = dispatcher["bot_instance"]
    settings: Settings = dispatcher["settings"]
    i18n_instance: JsonI18n = dispatcher["i18n_instance"]
    panel_service: PanelApiService = dispatcher["panel_service"]

    async_session_factory: sessionmaker = dispatcher["async_session_factory"]

    logging.info("STARTUP: on_startup_configured executing...")


    telegram_webhook_url_to_set = settings.WEBHOOK_BASE_URL
    if telegram_webhook_url_to_set:
        full_telegram_webhook_url = (
            f"{str(telegram_webhook_url_to_set).rstrip('/')}/{settings.BOT_TOKEN}"
        )

        logging.info(
            f"STARTUP: Attempting to set Telegram webhook to: {full_telegram_webhook_url if full_telegram_webhook_url != 'ERROR_URL_TOKEN_DETECTED' else 'HIDDEN DUE TO TOKEN'}"
        )

        if full_telegram_webhook_url != "ERROR_URL_TOKEN_DETECTED":
            try:
                current_webhook_info = await bot.get_webhook_info()
                logging.info(
                    f"STARTUP: Current Telegram webhook info BEFORE setting: {current_webhook_info.model_dump_json(exclude_none=True, indent=2)}"
                )

                set_success = await bot.set_webhook(
                    url=full_telegram_webhook_url,
                    drop_pending_updates=True,
                    allowed_updates=dispatcher.resolve_used_update_types(),
                )
                if set_success:
                    logging.info(
                        f"STARTUP: bot.set_webhook to {full_telegram_webhook_url} returned SUCCESS (True)."
                    )
                else:
                    logging.error(
                        f"STARTUP: bot.set_webhook to {full_telegram_webhook_url} returned FAILURE (False)."
                    )

                new_webhook_info = await bot.get_webhook_info()
                logging.info(
                    f"STARTUP: Telegram Webhook info AFTER setting: {new_webhook_info.model_dump_json(exclude_none=True, indent=2)}"
                )
                if not new_webhook_info.url:
                    logging.error(
                        "STARTUP: CRITICAL - Telegram Webhook URL is EMPTY after set attempt. Check bot token and URL validity."
                    )

            except Exception as e_setwebhook:
                logging.error(
                    f"STARTUP: EXCEPTION during set/get Telegram webhook: {e_setwebhook}",
                    exc_info=True,
                )
        else:
            logging.error(
                "STARTUP: Skipped setting Telegram webhook due to security or configuration error."
            )
    else:
        logging.info(
            "STARTUP: WEBHOOK_BASE_URL not set in environment. Running in polling mode and clearing any existing webhook."
        )
        await bot.delete_webhook(drop_pending_updates=True)

    if settings.SUBSCRIPTION_MINI_APP_URL:
        try:
            menu_text = i18n_instance.gettext(
                settings.DEFAULT_LANGUAGE,
                "menu_my_subscription_inline",
            )
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text=menu_text,
                    web_app=WebAppInfo(url=settings.SUBSCRIPTION_MINI_APP_URL),
                )
            )
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
            logging.info(
                "STARTUP: Mini app domain registered and default menu button restored."
            )
        except Exception as e:
            logging.error(
                f"STARTUP: Failed to register mini app domain: {e}", exc_info=True
            )

    if settings.START_COMMAND_DESCRIPTION:
        try:
            await bot.set_my_commands([
                BotCommand(command="start", description=settings.START_COMMAND_DESCRIPTION)
            ])
            logging.info("STARTUP: /start command description set.")
        except Exception as e:
            logging.error(f"STARTUP: Failed to set bot commands: {e}", exc_info=True)

    logging.info("STARTUP: Bot on_startup_configured completed.")


async def on_shutdown_configured(dispatcher: Dispatcher):
    logging.warning("SHUTDOWN: on_shutdown_configured executing...")

    async def close_service(key: str) -> None:
        service = dispatcher.get(key)
        if not service:
            return
        close_coro = getattr(service, "close", None)
        if callable(close_coro):
            try:
                await close_coro()
                logging.info(f"{key} closed on shutdown.")
            except Exception as e:
                logging.warning(f"Failed to close {key}: {e}")
        else:
            close_session = getattr(service, "close_session", None)
            if callable(close_session):
                try:
                    await close_session()
                    logging.info(f"{key} session closed on shutdown.")
                except Exception as e:
                    logging.warning(f"Failed to close session for {key}: {e}")

    for service_key in (
        "panel_service",
        "cryptopay_service",
        "tribute_service",
        "panel_webhook_service",
        "yookassa_service",
        "promo_code_service",
        "stars_service",
        "subscription_service",
        "referral_service",
    ):
        await close_service(service_key)

    bot: Bot = dispatcher["bot_instance"]
    if bot and bot.session:
        try:
            await bot.session.close()
            logging.info("SHUTDOWN: Aiogram Bot session closed.")
        except Exception as e:
            logging.warning(f"SHUTDOWN: Failed to close bot session: {e}")

    from db.database_setup import async_engine as global_async_engine

    if global_async_engine:
        logging.info("SHUTDOWN: Disposing SQLAlchemy engine...")
        await global_async_engine.dispose()
        logging.info("SHUTDOWN: SQLAlchemy engine disposed.")

    logging.info("SHUTDOWN: Bot on_shutdown_configured completed.")


async def run_bot(settings_param: Settings):
    storage = MemoryStorage()
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot = Bot(token=settings_param.BOT_TOKEN, default=default_props)

    local_async_session_factory = init_db_connection(settings_param)
    if local_async_session_factory is None:
        logging.critical(
            "Failed to initialize database connection and session factory. Exiting."
        )
        return

    dp = Dispatcher(storage=storage, settings=settings_param, bot_instance=bot)

    actual_bot_username = "your_bot_username"
    try:
        bot_info = await bot.get_me()
        actual_bot_username = bot_info.username
        logging.info(f"Bot username resolved: @{actual_bot_username}")
    except Exception as e:
        logging.error(
            f"Failed to get bot info (e.g., for YooKassa default URL): {e}. Using fallback: {actual_bot_username}"
        )

    i18n_instance = get_i18n_instance(
        path="locales", default=settings_param.DEFAULT_LANGUAGE
    )

    yookassa_service = YooKassaService(
        shop_id=settings_param.YOOKASSA_SHOP_ID,
        secret_key=settings_param.YOOKASSA_SECRET_KEY,
        configured_return_url=settings_param.YOOKASSA_RETURN_URL,
        bot_username_for_default_return=actual_bot_username,
        settings_obj=settings_param,
    )
    panel_service = PanelApiService(settings_param)

    subscription_service = SubscriptionService(
        settings_param, panel_service, bot, i18n_instance
    )
    referral_service = ReferralService(
        settings_param, subscription_service, bot, i18n_instance
    )
    promo_code_service = PromoCodeService(
        settings_param, subscription_service, bot, i18n_instance
    )
    stars_service = StarsService(
        bot, settings_param, i18n_instance, subscription_service, referral_service
    )
    cryptopay_service = CryptoPayService(
        settings_param.CRYPTOPAY_TOKEN,
        settings_param.CRYPTOPAY_NETWORK,
        bot,
        settings_param,
        i18n_instance,
        local_async_session_factory,
        subscription_service,
        referral_service,
    )
    tribute_service = TributeService(
        bot,
        settings_param,
        i18n_instance,
        local_async_session_factory,
        panel_service,
        subscription_service,
        referral_service,
    )
    panel_webhook_service = PanelWebhookService(
        bot,
        settings_param,
        i18n_instance,
        local_async_session_factory,
    )

    dp["i18n_instance"] = i18n_instance
    dp["yookassa_service"] = yookassa_service
    dp["panel_service"] = panel_service
    dp["subscription_service"] = subscription_service
    dp["referral_service"] = referral_service
    dp["promo_code_service"] = promo_code_service
    dp["stars_service"] = stars_service
    dp["cryptopay_service"] = cryptopay_service
    dp["tribute_service"] = tribute_service
    dp["panel_webhook_service"] = panel_webhook_service
    dp["async_session_factory"] = local_async_session_factory

    dp.update.outer_middleware(DBSessionMiddleware(local_async_session_factory))
    dp.update.outer_middleware(
        I18nMiddleware(i18n=i18n_instance, settings=settings_param)
    )
    dp.update.outer_middleware(
        BanCheckMiddleware(settings=settings_param, i18n_instance=i18n_instance)
    )
    dp.update.outer_middleware(ActionLoggerMiddleware(settings=settings_param))

    dp.startup.register(on_startup_configured)
    # Register shutdown callback directly so Dispatcher instance is provided
    dp.shutdown.register(on_shutdown_configured)

    await register_all_routers(dp, settings_param)

    tg_webhook_base = settings_param.WEBHOOK_BASE_URL
    yk_webhook_base = settings_param.WEBHOOK_BASE_URL

    should_run_aiohttp_server = bool(tg_webhook_base) or (
        bool(yk_webhook_base) and bool(settings_param.yookassa_webhook_path)
    )

    telegram_uses_webhook_mode = bool(tg_webhook_base)
    run_telegram_polling = not telegram_uses_webhook_mode

    logging.info(f"--- Bot Run Mode Decision ---")
    logging.info(
        f"Configured WEBHOOK_BASE_URL: '{tg_webhook_base}' -> Telegram Webhook Mode: {telegram_uses_webhook_mode}"
    )
    logging.info(
        f"YooKassa webhook path: '{settings_param.yookassa_webhook_path}'"
    )
    logging.info(f"Decision: Run AIOHTTP server: {should_run_aiohttp_server}")
    logging.info(f"Decision: Run Telegram Polling: {run_telegram_polling}")
    logging.info(f"--- End Bot Run Mode Decision ---")

    web_app_runner = None
    main_tasks = []

    if should_run_aiohttp_server:
        app = web.Application()
        app["bot"] = bot
        app["dp"] = dp
        app["settings"] = settings_param
        app["i18n"] = i18n_instance
        app["async_session_factory"] = local_async_session_factory

        app["yookassa_service"] = yookassa_service
        app["subscription_service"] = subscription_service
        app["referral_service"] = referral_service
        app["panel_service"] = panel_service
        app["stars_service"] = stars_service
        app["cryptopay_service"] = cryptopay_service
        app["tribute_service"] = tribute_service
        app["panel_webhook_service"] = panel_webhook_service

        setup_application(app, dp, bot=bot)

        if telegram_uses_webhook_mode:
            telegram_webhook_path = f"/{settings_param.BOT_TOKEN}"
            if not telegram_webhook_path.startswith("/"):
                telegram_webhook_path = "/" + telegram_webhook_path
            app.router.add_post(
                telegram_webhook_path, SimpleRequestHandler(dispatcher=dp, bot=bot)
            )
            logging.info(
                f"Telegram webhook route configured at: [POST] {telegram_webhook_path} (relative to base URL)"
            )

        if yk_webhook_base and settings_param.yookassa_webhook_path:
            yk_path = settings_param.yookassa_webhook_path
            if not yk_path or not isinstance(yk_path, str):
                logging.error(
                    f"YooKassa webhook path is invalid or not configured in settings: {yk_path}. Skipping YooKassa webhook setup."
                )
            elif not yk_path.startswith("/"):
                logging.error(
                    f"CRITICAL: YooKassa webhook path '{yk_path}' from settings does not start with '/'. Correct settings.py or .env. Skipping YooKassa webhook."
                )
            else:
                app.router.add_post(
                    yk_path, user_payment_webhook_module.yookassa_webhook_route
                )
                logging.info(f"YooKassa webhook route configured at: [POST] {yk_path}")

        tribute_path = settings_param.tribute_webhook_path
        if tribute_path.startswith("/"):
            app.router.add_post(tribute_path, tribute_webhook_route)
            logging.info(f"Tribute webhook route configured at: [POST] {tribute_path}")

        cp_path = settings_param.cryptopay_webhook_path
        if cp_path.startswith("/"):
            app.router.add_post(cp_path, cryptopay_webhook_route)
            logging.info(f"CryptoPay webhook route configured at: [POST] {cp_path}")

        panel_path = settings_param.panel_webhook_path
        if panel_path.startswith("/"):
            app.router.add_post(panel_path, panel_webhook_route)
            logging.info(f"Panel webhook route configured at: [POST] {panel_path}")

        web_app_runner = web.AppRunner(app)
        await web_app_runner.setup()
        site = web.TCPSite(
            web_app_runner,
            host=settings_param.WEB_SERVER_HOST,
            port=settings_param.WEB_SERVER_PORT,
        )

        async def web_server_task():
            await site.start()
            logging.info(
                f"AIOHTTP server started on http://{settings_param.WEB_SERVER_HOST}:{settings_param.WEB_SERVER_PORT}"
            )
            (
                await asyncio.Event().wait()
                if not run_telegram_polling
                else await asyncio.sleep(31536000)
            )

        main_tasks.append(
            asyncio.create_task(web_server_task(), name="AIOHTTPServerTask")
        )

    if run_telegram_polling:
        logging.info("Starting bot in Telegram Polling mode...")
        main_tasks.append(
            asyncio.create_task(
                dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()),
                name="TelegramPollingTask",
            )
        )

    if not main_tasks:
        logging.error(
            "Bot is not configured for any run mode (neither Webhook nor Polling). Exiting."
        )
        await dp.emit_shutdown()
        return

    logging.info(
        f"Starting bot with main tasks: {[task.get_name() for task in main_tasks]}"
    )

    try:
        await asyncio.gather(*main_tasks)
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError) as e:
        logging.info(f"Main bot loop interrupted/cancelled: {type(e).__name__} - {e}")
    finally:
        logging.info("Initiating final bot shutdown sequence...")
        for task in main_tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logging.info(
                        f"Task '{task.get_name()}' was cancelled successfully."
                    )
                except Exception as e_task_cancel:
                    logging.error(
                        f"Error during cancellation of task '{task.get_name()}': {e_task_cancel}",
                        exc_info=True,
                    )

        if web_app_runner:
            await web_app_runner.cleanup()
            logging.info("AIOHTTP AppRunner cleaned up.")

        await dp.emit_shutdown()
        logging.info("Dispatcher shutdown sequence emitted.")

        logging.info("Bot run_bot function finished.")
