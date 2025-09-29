import logging
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import update, delete, func, and_
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import User, Subscription


async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    stmt = select(User).where(User.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_username(session: AsyncSession, username: str) -> Optional[User]:
    clean_username = username.lstrip("@").lower()
    stmt = select(User).where(func.lower(User.username) == clean_username)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_panel_uuid(
    session: AsyncSession, panel_uuid: str
) -> Optional[User]:
    stmt = select(User).where(User.panel_user_uuid == panel_uuid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


## Removed unused generic get_user helper to keep DAL explicit and simple


async def create_user(session: AsyncSession, user_data: Dict[str, Any]) -> Tuple[User, bool]:
    """Create a user if not exists in a race-safe way.

    Returns a tuple of (user, created_flag).
    """

    if "registration_date" not in user_data:
        user_data["registration_date"] = datetime.now(timezone.utc)

    # Use PostgreSQL upsert to avoid IntegrityError on concurrent inserts
    stmt = (
        pg_insert(User)
        .values(**user_data)
        .on_conflict_do_nothing(index_elements=[User.user_id])
        .returning(User.user_id)
    )

    result = await session.execute(stmt)
    inserted_row = result.first()
    created = inserted_row is not None

    # Fetch the user (inserted just now or pre-existing)
    user_id: int = user_data["user_id"]
    user = await get_user_by_id(session, user_id)

    if created and user is not None:
        logging.info(
            f"New user {user.user_id} created in DAL. Referred by: {user.referred_by_id or 'N/A'}."
        )
    elif user is not None:
        logging.info(
            f"User {user.user_id} already exists in DAL. Proceeding without creation."
        )

    return user, created


async def update_user(
    session: AsyncSession, user_id: int, update_data: Dict[str, Any]
) -> Optional[User]:
    user = await get_user_by_id(session, user_id)
    if user:
        for key, value in update_data.items():
            setattr(user, key, value)
        await session.flush()
        await session.refresh(user)
    return user


async def update_user_language(
    session: AsyncSession, user_id: int, lang_code: str
) -> bool:
    stmt = update(User).where(User.user_id == user_id).values(language_code=lang_code)
    result = await session.execute(stmt)
    return result.rowcount > 0


async def get_banned_users(session: AsyncSession) -> List[User]:
    """Get all banned users"""
    stmt = (
        select(User)
        .where(User.is_banned == True)
        .order_by(User.registration_date.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_all_active_user_ids_for_broadcast(session: AsyncSession) -> List[int]:
    stmt = select(User.user_id).where(User.is_banned == False)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_all_users_with_panel_uuid(session: AsyncSession) -> List[User]:
    stmt = select(User).where(User.panel_user_uuid.is_not(None))
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_enhanced_user_statistics(session: AsyncSession) -> Dict[str, Any]:
    """Get comprehensive user statistics including active users, trial users, etc."""
    from datetime import datetime, timezone
    
    # Use timezone-aware UTC to avoid naive/aware comparison issues in SQL queries
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Total users
    total_users_stmt = select(func.count(User.user_id))
    total_users = (await session.execute(total_users_stmt)).scalar() or 0
    
    # Banned users
    banned_users_stmt = select(func.count(User.user_id)).where(User.is_banned == True)
    banned_users = (await session.execute(banned_users_stmt)).scalar() or 0
    
    # Active users today (proxy: registered today)
    active_today_stmt = select(func.count(User.user_id)).where(User.registration_date >= today_start)
    active_today = (await session.execute(active_today_stmt)).scalar() or 0
    
    # Users with active paid subscriptions (non-trial providers only)
    paid_subs_stmt = (
        select(func.count(func.distinct(Subscription.user_id)))
        .join(User, Subscription.user_id == User.user_id)
        .where(
            and_(
                Subscription.is_active == True,
                Subscription.end_date > now,
                Subscription.provider.is_not(None)  # Not trial
            )
        )
    )
    paid_subs_users = (await session.execute(paid_subs_stmt)).scalar() or 0
    
    # Users on trial period
    trial_subs_stmt = (
        select(func.count(func.distinct(Subscription.user_id)))
        .join(User, Subscription.user_id == User.user_id)
        .where(
            and_(
                Subscription.is_active == True,
                Subscription.end_date > now,
                Subscription.provider.is_(None)  # Trial subscriptions
            )
        )
    )
    trial_users = (await session.execute(trial_subs_stmt)).scalar() or 0
    
    # Inactive users (no active subscription)
    inactive_users = total_users - paid_subs_users - trial_users - banned_users
    
    # Users attracted via referral
    referral_users_stmt = select(func.count(User.user_id)).where(User.referred_by_id.is_not(None))
    referral_users = (await session.execute(referral_users_stmt)).scalar() or 0
    
    return {
        "total_users": total_users,
        "banned_users": banned_users,
        "active_today": active_today,
        "paid_subscriptions": paid_subs_users,
        "trial_users": trial_users,
        "inactive_users": max(0, inactive_users),
        "referral_users": referral_users
    }


async def get_user_ids_with_active_subscription(session: AsyncSession) -> List[int]:
    """Return non-banned user IDs who have an active subscription (paid or trial)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    stmt = (
        select(func.distinct(Subscription.user_id))
        .join(User, Subscription.user_id == User.user_id)
        .where(
            and_(
                User.is_banned == False,
                Subscription.is_active == True,
                Subscription.end_date > now,
            )
        )
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_user_ids_without_active_subscription(session: AsyncSession) -> List[int]:
    """Return non-banned user IDs who do NOT have any active subscription."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    # Subquery for users with active subscription
    active_subs_subq = (
        select(Subscription.user_id)
        .where(
            and_(
                Subscription.is_active == True,
                Subscription.end_date > now,
            )
        )
    ).scalar_subquery()

    stmt = (
        select(User.user_id)
        .where(
            and_(
                User.is_banned == False,
                ~User.user_id.in_(active_subs_subq),
            )
        )
    )
    result = await session.execute(stmt)
    return result.scalars().all()
