import logging
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import update, delete, func, and_
from datetime import datetime

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


async def create_user(session: AsyncSession, user_data: Dict[str, Any]) -> User:

    if "registration_date" not in user_data:
        user_data["registration_date"] = datetime.now()

    new_user = User(**user_data)
    session.add(new_user)
    await session.flush()
    await session.refresh(new_user)
    logging.info(
        f"New user {new_user.user_id} created in DAL. Referred by: {new_user.referred_by_id or 'N/A'}."
    )
    return new_user


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


async def set_user_ban_status(
    session: AsyncSession, user_id: int, is_banned: bool
) -> bool:
    user = await get_user_by_id(session, user_id)
    if user:
        user.is_banned = is_banned
        await session.flush()
        await session.refresh(user)
        return True
    return False


async def get_banned_users_paginated(
    session: AsyncSession, limit: int, offset: int
) -> Tuple[List[User], int]:
    stmt_users = (
        select(User)
        .where(User.is_banned == True)
        .order_by(User.registration_date.desc())
        .limit(limit)
        .offset(offset)
    )
    result_users = await session.execute(stmt_users)
    users_list = result_users.scalars().all()

    stmt_count = select(func.count()).select_from(User).where(User.is_banned == True)
    result_count = await session.execute(stmt_count)
    total_banned = result_count.scalar_one()

    return users_list, total_banned


async def get_all_active_user_ids_for_broadcast(session: AsyncSession) -> List[int]:
    stmt = select(User.user_id).where(User.is_banned == False)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_user_count_stats_dal(session: AsyncSession) -> Dict[str, int]:
    total_users_stmt = select(func.count(User.user_id)).select_from(User)
    banned_users_stmt = (
        select(func.count(User.user_id)).select_from(User).where(User.is_banned == True)
    )

    active_subs_stmt = (
        select(func.count(func.distinct(Subscription.user_id)))
        .join(User, Subscription.user_id == User.user_id)
        .where(Subscription.is_active == True)
        .where(Subscription.end_date > datetime.now())
    )

    total_users = (await session.execute(total_users_stmt)).scalar_one_or_none() or 0
    banned_users = (await session.execute(banned_users_stmt)).scalar_one_or_none() or 0
    active_subs_users = (
        await session.execute(active_subs_stmt)
    ).scalar_one_or_none() or 0

    return {
        "total_users": total_users,
        "banned_users": banned_users,
        "users_with_active_subscriptions": active_subs_users,
    }


async def get_all_users_with_panel_uuid(session: AsyncSession) -> List[User]:
    stmt = select(User).where(User.panel_user_uuid.is_not(None))
    result = await session.execute(stmt)
    return result.scalars().all()
