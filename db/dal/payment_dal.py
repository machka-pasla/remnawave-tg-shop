import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, func
from sqlalchemy.orm import selectinload

from db.models import Payment, User


async def create_payment_record(session: AsyncSession,
                                payment_data: Dict[str, Any]) -> Payment:

    from .user_dal import get_user_by_id
    user = await get_user_by_id(session, payment_data["user_id"])
    if not user:

        raise ValueError(
            f"User with id {payment_data['user_id']} not found for creating payment."
        )

    if payment_data.get("promo_code_id"):
        from .promo_code_dal import get_promo_code_by_id
        promo = await get_promo_code_by_id(session,
                                           payment_data["promo_code_id"])
        if not promo:
            raise ValueError(
                f"Promo code with id {payment_data['promo_code_id']} not found."
            )

    new_payment = Payment(**payment_data)
    session.add(new_payment)
    await session.flush()
    await session.refresh(new_payment)
    logging.info(
        f"Payment record {new_payment.payment_id} created for user {new_payment.user_id}"
    )
    return new_payment


async def get_payment_by_yookassa_id(
        session: AsyncSession, yookassa_payment_id: str) -> Optional[Payment]:
    stmt = select(Payment).where(
        Payment.yookassa_payment_id == yookassa_payment_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_payment_by_provider_payment_id(
        session: AsyncSession, provider_payment_id: str) -> Optional[Payment]:
    """Fetch a payment by provider-specific identifier."""
    stmt = select(Payment).where(
        Payment.provider_payment_id == provider_payment_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_payment_by_db_id(session: AsyncSession,
                               payment_db_id: int) -> Optional[Payment]:

    stmt = select(Payment).where(Payment.payment_id == payment_db_id).options(
        selectinload(Payment.user), selectinload(Payment.promo_code_used))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_payment_by_db_id_with_promo(
        session: AsyncSession, payment_db_id: int) -> Optional[Payment]:

    stmt = select(Payment).where(Payment.payment_id == payment_db_id).options(
        selectinload(Payment.promo_code_used))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_payment_status_by_db_id(
        session: AsyncSession,
        payment_db_id: int,
        new_status: str,
        yk_payment_id: Optional[str] = None,
        payment_method_id: Optional[str] = None) -> Optional[Payment]:
    payment = await get_payment_by_db_id(session, payment_db_id)
    if payment:
        payment.status = new_status
        payment.updated_at = func.now()
        if yk_payment_id and payment.yookassa_payment_id is None:
            payment.yookassa_payment_id = yk_payment_id
        if payment_method_id:
            payment.payment_method_id = payment_method_id
        await session.flush()
        await session.refresh(payment)
        logging.info(
            f"Payment record {payment.payment_id} status updated to {new_status}."
        )
    else:
        logging.warning(
            f"Payment record with DB ID {payment_db_id} not found for status update."
        )
    return payment


async def user_has_successful_payment_for_provider(
        session: AsyncSession, user_id: int, provider: str) -> bool:
    """Check if a user has at least one successful payment for the provider."""

    stmt = (select(Payment.payment_id)
            .where(Payment.user_id == user_id,
                   Payment.provider == provider,
                   Payment.status == 'succeeded')
            .limit(1))
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def update_payment_status_by_yk_id(session: AsyncSession,
                                         yookassa_payment_id: str,
                                         new_status: str,
                                         payment_method_id: Optional[str] = None) -> Optional[Payment]:
    payment = await get_payment_by_yookassa_id(session, yookassa_payment_id)
    if payment:
        payment.status = new_status
        payment.updated_at = func.now()
        if payment_method_id:
            payment.payment_method_id = payment_method_id
        await session.flush()
        await session.refresh(payment)
        logging.info(
            f"Payment record with YK ID {yookassa_payment_id} status updated to {new_status}."
        )
    else:
        logging.warning(
            f"Payment record with YK ID {yookassa_payment_id} not found for status update."
        )
    return payment


async def get_recent_payment_logs_with_user(session: AsyncSession,
                                            limit: int = 20,
                                            offset: int = 0) -> List[Payment]:
    stmt = (select(Payment).options(selectinload(Payment.user)).order_by(
        Payment.created_at.desc()).limit(limit).offset(offset))
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_provider_payment_and_status(
        session: AsyncSession, payment_db_id: int,
        provider_payment_id: str, new_status: str) -> Optional[Payment]:
    payment = await get_payment_by_db_id(session, payment_db_id)
    if payment:
        payment.status = new_status
        payment.provider_payment_id = provider_payment_id
        payment.updated_at = func.now()
        await session.flush()
        await session.refresh(payment)
        logging.info(
            f"Payment record {payment.payment_id} updated with provider id {provider_payment_id} and status {new_status}."
        )
    else:
        logging.warning(
            f"Payment record with DB ID {payment_db_id} not found for provider update."
        )
    return payment
