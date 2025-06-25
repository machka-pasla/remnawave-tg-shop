import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete, func, and_, or_
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone, timedelta

from db.models import Subscription, User


async def get_active_subscription_by_user_id(
        session: AsyncSession,
        user_id: int,
        panel_user_uuid: Optional[str] = None) -> Optional[Subscription]:
    stmt = select(Subscription).where(
        Subscription.user_id == user_id, Subscription.is_active == True,
        Subscription.end_date > datetime.now(timezone.utc))
    if panel_user_uuid:
        stmt = stmt.where(Subscription.panel_user_uuid == panel_user_uuid)
    stmt = stmt.order_by(Subscription.end_date.desc())
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_subscription_by_panel_subscription_uuid(
        session: AsyncSession, panel_sub_uuid: str) -> Optional[Subscription]:
    stmt = select(Subscription).where(
        Subscription.panel_subscription_uuid == panel_sub_uuid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_subscription(session: AsyncSession,
                              sub_data: Dict[str, Any]) -> Subscription:
    from .user_dal import get_user_by_id

    if "user_id" not in sub_data or sub_data["user_id"] is None:
        raise ValueError(
            "user_id is required to create a subscription directly.")
    user = await get_user_by_id(session, sub_data["user_id"])
    if not user:
        raise ValueError(
            f"User with id {sub_data['user_id']} not found for creating subscription."
        )

    new_sub = Subscription(**sub_data)
    session.add(new_sub)
    await session.flush()
    await session.refresh(new_sub)
    logging.info(
        f"Subscription {new_sub.subscription_id} created for user {new_sub.user_id}"
    )
    return new_sub


async def update_subscription(
        session: AsyncSession, subscription_id: int,
        update_data: Dict[str, Any]) -> Optional[Subscription]:
    sub = await session.get(Subscription, subscription_id)
    if sub:
        for key, value in update_data.items():
            setattr(sub, key, value)
        await session.flush()
        await session.refresh(sub)
    return sub


async def upsert_subscription(session: AsyncSession,
                              sub_payload: Dict[str, Any]) -> Subscription:
    panel_sub_uuid = sub_payload.get("panel_subscription_uuid")
    if not panel_sub_uuid:
        raise ValueError("panel_subscription_uuid is required for upsert.")

    existing_sub = await get_subscription_by_panel_subscription_uuid(
        session, panel_sub_uuid)

    if existing_sub:
        logging.info(
            f"Updating existing subscription {existing_sub.subscription_id} by panel_sub_uuid {panel_sub_uuid}"
        )
        for key, value in sub_payload.items():
            if hasattr(existing_sub, key):
                setattr(existing_sub, key, value)
        await session.flush()
        await session.refresh(existing_sub)
        return existing_sub
    else:
        logging.info(
            f"Creating new subscription with panel_sub_uuid {panel_sub_uuid}")

        if sub_payload.get(
                "user_id") is None and "panel_user_uuid" not in sub_payload:
            raise ValueError(
                "For a new subscription without user_id, panel_user_uuid is required."
            )
        if "end_date" not in sub_payload:
            raise ValueError("Missing 'end_date' for new subscription.")
        if sub_payload.get("user_id") is not None:
            from .user_dal import get_user_by_id
            user = await get_user_by_id(session, sub_payload["user_id"])
            if not user:
                raise ValueError(
                    f"User {sub_payload['user_id']} not found for new subscription with panel_uuid {panel_sub_uuid}."
                )

        new_sub = Subscription(**sub_payload)
        session.add(new_sub)
        await session.flush()
        await session.refresh(new_sub)
        return new_sub


async def deactivate_other_active_subscriptions(
        session: AsyncSession, panel_user_uuid: str,
        current_panel_subscription_uuid: Optional[str]):
    stmt = (update(Subscription).where(
        Subscription.panel_user_uuid == panel_user_uuid,
        Subscription.is_active == True,
    ).values(is_active=False, status_from_panel="INACTIVE_BY_BOT_SYNC"))
    if current_panel_subscription_uuid:
        stmt = stmt.where(Subscription.panel_subscription_uuid !=
                          current_panel_subscription_uuid)

    result = await session.execute(stmt)
    if result.rowcount > 0:
        logging.info(
            f"Deactivated {result.rowcount} other active subscriptions for panel_user_uuid {panel_user_uuid}."
        )


async def deactivate_all_user_subscriptions(
        session: AsyncSession, user_id: int) -> int:
    stmt = (
        update(Subscription)
        .where(Subscription.user_id == user_id, Subscription.is_active == True)
        .values(is_active=False, status_from_panel="INACTIVE_USER_NOT_FOUND")
    )
    result = await session.execute(stmt)
    if result.rowcount > 0:
        logging.info(
            f"Deactivated {result.rowcount} subscriptions for user {user_id} due to missing panel user."
        )
    return result.rowcount


async def update_subscription_end_date(
        session: AsyncSession, subscription_id: int,
        new_end_date: datetime) -> Optional[Subscription]:

    return await update_subscription(
        session, subscription_id, {
            "end_date": new_end_date,
            "last_notification_sent": None,
            "is_active": True,
            "status_from_panel": "ACTIVE_EXTENDED_BY_BOT"
        })


async def has_any_subscription_for_user(session: AsyncSession,
                                        user_id: int) -> bool:
    stmt = select(Subscription.subscription_id).where(
        Subscription.user_id == user_id).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def get_subscriptions_near_expiration(
        session: AsyncSession, days_threshold: int) -> List[Subscription]:
    now_utc = datetime.now(timezone.utc)
    threshold_date = now_utc + timedelta(days=days_threshold)

    stmt = (select(Subscription).join(Subscription.user).where(
        Subscription.is_active == True,
        Subscription.skip_notifications == False,
        Subscription.end_date > now_utc,
        Subscription.end_date <= threshold_date,
        or_(
            Subscription.last_notification_sent == None,
            func.date(Subscription.last_notification_sent)
            < func.date(now_utc))).order_by(
                Subscription.end_date.asc()).options(
                    selectinload(Subscription.user)))
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_subscription_notification_time(
        session: AsyncSession, subscription_id: int,
        notification_time: datetime) -> Optional[Subscription]:
    return await update_subscription(
        session, subscription_id,
        {"last_notification_sent": notification_time})


async def get_user_active_subscription_end_date_str(
        session: AsyncSession, user_id: int) -> Optional[str]:
    stmt = (select(Subscription.end_date).where(
        Subscription.user_id == user_id, Subscription.is_active == True,
        Subscription.end_date > datetime.now(timezone.utc)).order_by(
            Subscription.end_date.desc()).limit(1))
    result = await session.execute(stmt)
    end_date_obj = result.scalar_one_or_none()
    return end_date_obj.strftime('%Y-%m-%d') if end_date_obj else None


async def find_subscription_for_notification_update(
        session: AsyncSession, user_id: int,
        subscription_end_date_to_match: datetime) -> Optional[Subscription]:

    if subscription_end_date_to_match.tzinfo is None:
        subscription_end_date_to_match = subscription_end_date_to_match.replace(
            tzinfo=timezone.utc)

    stmt = select(Subscription).where(
        Subscription.user_id == user_id, Subscription.is_active == True,
        Subscription.end_date
        >= subscription_end_date_to_match - timedelta(seconds=1),
        Subscription.end_date
        <= subscription_end_date_to_match + timedelta(seconds=1)).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def set_skip_notifications_for_provider(
        session: AsyncSession, user_id: int, provider: str,
        skip: bool) -> int:
    stmt = (update(Subscription).where(
        Subscription.user_id == user_id,
        Subscription.is_active == True,
        Subscription.provider == provider).values(skip_notifications=skip))
    result = await session.execute(stmt)
    return result.rowcount
