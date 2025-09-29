from aiogram import Router, F

from bot.handlers.user import user_router_aggregate
from bot.handlers import inline_mode
from bot.handlers.admin import admin_router_aggregate
from bot.filters.admin_filter import AdminFilter
from config.settings import Settings


def build_root_router(settings: Settings) -> Router:
    root = Router(name="root")

    # Allow all updates only in private chats (messages, callback queries, etc.)
    root.message.filter(F.chat.type == "private")
    root.callback_query.filter(F.message.chat.type == "private")

    # Public routers
    root.include_router(user_router_aggregate)
    root.include_router(inline_mode.router)

    # Admin routers behind filter
    admin_main_router = Router(name="admin_main_filtered_router")
    admin_filter_instance = AdminFilter(admin_ids=settings.ADMIN_IDS)
    admin_main_router.message.filter(admin_filter_instance)
    admin_main_router.callback_query.filter(admin_filter_instance)
    admin_main_router.include_router(admin_router_aggregate)
    root.include_router(admin_main_router)

    return root

