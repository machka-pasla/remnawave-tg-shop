import logging
from aiogram import Router, types, Bot
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.dal import user_dal, payment_dal
from bot.services.referral_service import ReferralService
from bot.middlewares.i18n import JsonI18n

router = Router(name="inline_mode_router")


@router.inline_query()
async def inline_query_handler(inline_query: InlineQuery,
                               settings: Settings,
                               i18n_data: dict,
                               referral_service: ReferralService,
                               bot: Bot,
                               session: AsyncSession):
    """Handle inline queries for referral links and admin statistics"""
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n:
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    user_id = inline_query.from_user.id
    query = inline_query.query.lower().strip()
    
    results: List[InlineQueryResultArticle] = []
    
    # Check if user is admin
    is_admin = user_id in settings.ADMIN_IDS if settings.ADMIN_IDS else False
    
    try:
        # For all users: referral functionality
        if not query or "реф" in query or "ref" in query or "друг" in query or "friend" in query:
            referral_result = await create_referral_result(
                inline_query,
                bot,
                referral_service,
                i18n,
                current_lang,
                settings,
                session,
            )
            if referral_result:
                results.append(referral_result)
        
        # For admins: statistics
        if is_admin and (not query or "стат" in query or "stat" in query or "админ" in query or "admin" in query):
            stats_results = await create_admin_stats_results(
                session, i18n, current_lang, settings
            )
            results.extend(stats_results)
        

        
        # Limit results to 50 (Telegram limit)
        results = results[:50]
        
        await inline_query.answer(
            results=results,
            cache_time=30,  # Cache for 30 seconds
            is_personal=True  # Results are personalized
        )
        
    except Exception as e:
        logging.error(f"Error handling inline query from user {user_id}: {e}")
        # Send empty results in case of error
        await inline_query.answer(results=[], cache_time=10)


async def create_referral_result(
    inline_query: InlineQuery,
    bot: Bot,
    referral_service: ReferralService,
    i18n_instance,
    lang: str,
    settings: Settings,
    session: AsyncSession,
) -> Optional[InlineQueryResultArticle]:
    """Create referral link result for inline query"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    
    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username
        if not bot_username:
            return None
        
        user_id = inline_query.from_user.id
        referral_link = await referral_service.generate_referral_link(
            session, bot_username, user_id
        )

        if not referral_link:
            logging.warning("Could not produce referral link for inline user %s", user_id)
            return None
        
        # Create message content (use same text as friend message)
        message_text = _(
            "referral_friend_message",
            referral_link=referral_link
        )
        
        return InlineQueryResultArticle(
            id="referral_link",
            title=_(
                "inline_referral_title"
            ),
            description=_(
                "inline_referral_description"
            ),
            input_message_content=InputTextMessageContent(
                message_text=message_text,
                disable_web_page_preview=True
            ),
            thumbnail_url=settings.INLINE_REFERRAL_THUMBNAIL_URL
        )
        
    except Exception as e:
        logging.error(f"Error creating referral result: {e}")
        return None


async def create_admin_stats_results(session: AsyncSession, i18n_instance, lang: str, settings: Settings) -> List[InlineQueryResultArticle]:
    """Create admin statistics results for inline query"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    results = []
    
    try:
        # Quick user stats
        user_stats_result = await create_user_stats_result(session, i18n_instance, lang, settings)
        if user_stats_result:
            results.append(user_stats_result)
        
        # Quick financial stats
        financial_stats_result = await create_financial_stats_result(session, i18n_instance, lang, settings)
        if financial_stats_result:
            results.append(financial_stats_result)
        
        # Quick system stats
        system_stats_result = await create_system_stats_result(session, i18n_instance, lang, settings)
        if system_stats_result:
            results.append(system_stats_result)
            
    except Exception as e:
        logging.error(f"Error creating admin stats results: {e}")
    
    return results


async def create_user_stats_result(session: AsyncSession, i18n_instance, lang: str, settings: Settings) -> Optional[InlineQueryResultArticle]:
    """Create user statistics result"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    
    try:
        from db.dal.user_dal import get_enhanced_user_statistics
        user_stats = await get_enhanced_user_statistics(session)
        
        stats_text = _(
            "inline_user_stats_message",
            total=user_stats['total_users'],
            active_today=user_stats['active_today'],
            paid=user_stats['paid_subscriptions'],
            trial=user_stats['trial_users'],
            inactive=user_stats['inactive_users'],
            banned=user_stats['banned_users'],
            referral=user_stats['referral_users']
        )
        
        return InlineQueryResultArticle(
            id="admin_user_stats",
            title=_(
                "inline_admin_user_stats_title"
            ),
            description=_(
                "inline_user_stats_description",
                total=user_stats['total_users'],
                active=user_stats['paid_subscriptions']
            ),
            input_message_content=InputTextMessageContent(
                message_text=stats_text,
                parse_mode="HTML"
            ),
            thumbnail_url=settings.INLINE_USER_STATS_THUMBNAIL_URL
        )
        
    except Exception as e:
        logging.error(f"Error creating user stats result: {e}")
        return None


async def create_financial_stats_result(session: AsyncSession, i18n_instance, lang: str, settings: Settings) -> Optional[InlineQueryResultArticle]:
    """Create financial statistics result"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    
    try:
        from db.dal.payment_dal import get_financial_statistics
        financial_stats = await get_financial_statistics(session)
        
        stats_text = _(
            "inline_financial_stats_message",
            today=financial_stats['today_revenue'],
            today_count=financial_stats['today_payments_count'],
            week=financial_stats['week_revenue'],
            month=financial_stats['month_revenue'],
            all_time=financial_stats['all_time_revenue']
        )
        
        return InlineQueryResultArticle(
            id="admin_financial_stats",
            title=_(
                "inline_admin_financial_stats_title"
            ),
            description=_(
                "inline_financial_description",
                today=f"{financial_stats['today_revenue']:.2f}"
            ),
            input_message_content=InputTextMessageContent(
                message_text=stats_text,
                parse_mode="HTML"
            ),
            thumbnail_url=settings.INLINE_FINANCIAL_STATS_THUMBNAIL_URL
        )
        
    except Exception as e:
        logging.error(f"Error creating financial stats result: {e}")
        return None


async def create_system_stats_result(session: AsyncSession, i18n_instance, lang: str, settings: Settings) -> Optional[InlineQueryResultArticle]:
    """Create panel statistics result with system/nodes/bandwidth info"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    
    try:
        from bot.services.panel_api_service import PanelApiService
        
        # Get panel stats similar to main statistics
        async with PanelApiService(settings) as panel_service:
            system_stats = await panel_service.get_system_stats()
            bandwidth_stats = await panel_service.get_bandwidth_stats()
            nodes_stats = await panel_service.get_nodes_statistics()
            
            if system_stats:
                users = system_stats.get('users', {})
                status_counts = users.get('statusCounts', {})
                online_stats = system_stats.get('onlineStats', {})
                
                active_users = status_counts.get('ACTIVE', 0)
                disabled_users = status_counts.get('DISABLED', 0) 
                expired_users = status_counts.get('EXPIRED', 0)
                limited_users = status_counts.get('LIMITED', 0)
                total_users = users.get('totalUsers', 0)
                online_now = online_stats.get('onlineNow', 0)
                
                # Memory usage
                memory = system_stats.get('memory', {})
                memory_usage = 0
                if memory:
                    memory_total = memory.get('total', 1)
                    memory_used = memory.get('used', 0)
                    memory_usage = (memory_used / memory_total) * 100 if memory_total > 0 else 0
                
                # Bandwidth
                week_traffic = "N/A"
                month_traffic = "N/A"
                if bandwidth_stats:
                    week_data = bandwidth_stats.get('bandwidthLastSevenDays', {})
                    month_data = bandwidth_stats.get('bandwidthLast30Days', {}) or bandwidth_stats.get('bandwidthLastThirtyDays', {})
                    
                    week_traffic = week_data.get('current', 'N/A') if week_data else 'N/A'
                    month_traffic = month_data.get('current', 'N/A') if month_data else 'N/A'
                
                # Nodes
                active_nodes = 0
                total_nodes = 0
                if nodes_stats and 'lastSevenDays' in nodes_stats:
                    unique_nodes = set()
                    for node_data in nodes_stats.get('lastSevenDays', []):
                        unique_nodes.add(node_data.get('nodeName', ''))
                    total_nodes = len(unique_nodes)
                    active_nodes = total_nodes  # Assume all are active
                elif system_stats and 'nodes' in system_stats:
                    active_nodes = system_stats.get('nodes', {}).get('totalOnline', 0)
                    total_nodes = active_nodes
                
                stats_text = _(
                    "inline_system_stats_message",
                    online=online_now,
                    active=active_users,
                    disabled=disabled_users,
                    expired=expired_users,
                    limited=limited_users,
                    total=total_users,
                    memory=memory_usage,
                    week_traffic=week_traffic,
                    month_traffic=month_traffic,
                    active_nodes=active_nodes,
                    total_nodes=total_nodes
                )
            else:
                stats_text = _("inline_panel_stats_error")
        
        return InlineQueryResultArticle(
            id="admin_system_stats",
            title=_(
                "inline_admin_system_stats_title"
            ),
            description=_(
                "inline_system_description",
                online=online_now,
                active=active_users
            ),
            input_message_content=InputTextMessageContent(
                message_text=stats_text,
                parse_mode="HTML"
            ),
            thumbnail_url=settings.INLINE_SYSTEM_STATS_THUMBNAIL_URL
        )
        
    except Exception as e:
        logging.error(f"Error creating system stats result: {e}")
        # Fallback error message
        error_text = _("inline_panel_stats_error")
        
        return InlineQueryResultArticle(
            id="admin_system_stats",
            title=_(
                "inline_admin_system_stats_title"
            ),
            description=_("inline_system_error"),
            input_message_content=InputTextMessageContent(
                message_text=error_text,
                parse_mode="HTML"
            ),
            thumbnail_url=settings.INLINE_SYSTEM_STATS_THUMBNAIL_URL
        )
        return None
