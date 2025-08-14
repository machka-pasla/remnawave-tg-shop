import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from db.dal import user_dal
from db.models import PhoneTransferPayment
from config.settings import Settings


class PhoneTransferService:
    """Service for handling phone transfer payments (manual offline payments)"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.enabled = settings.PHONE_TRANSFER_ENABLED
        self.phone_number = settings.PHONE_TRANSFER_NUMBER
        self.bank_name = settings.PHONE_TRANSFER_BANK_NAME
        self.instructions = settings.PHONE_TRANSFER_INSTRUCTIONS
        
        logging.info(f"PhoneTransferService initialized: enabled={self.enabled}, phone_number={self.phone_number}, bank_name={self.bank_name}")
        
        if not self.enabled:
            logging.warning("PhoneTransferService is DISABLED in settings")
        elif not self.phone_number:
            logging.error("PhoneTransferService: PHONE_TRANSFER_NUMBER not configured")
        else:
            logging.info(f"PhoneTransferService: Ready with phone {self.phone_number}")

    async def create_payment_request(
        self,
        session: AsyncSession,
        user_id: int,
        months: int,
        amount: float,
        currency: str = "RUB",
        description: Optional[str] = None,
        promo_code_id: Optional[int] = None
    ) -> Optional[PhoneTransferPayment]:
        """Create a new phone transfer payment request"""
        if not self.enabled:
            logging.warning("Phone transfer payments are disabled")
            return None

        if not self.phone_number:
            logging.error("Phone transfer number not configured")
            return None

        try:
            # Verify user exists
            user = await user_dal.get_user_by_id(session, user_id)
            if not user:
                logging.error(f"User {user_id} not found when creating phone transfer payment")
                return None

            # Create payment record
            payment = PhoneTransferPayment(
                user_id=user_id,
                amount=amount,
                currency=currency,
                subscription_duration_months=months,
                status="pending",
                description=description or f"Подписка на {months} мес.",
                promo_code_id=promo_code_id
            )

            session.add(payment)
            await session.flush()  # Get the ID without committing
            await session.refresh(payment)

            logging.info(f"Created phone transfer payment {payment.payment_id} for user {user_id}")
            return payment

        except Exception as e:
            logging.error(f"Error creating phone transfer payment: {e}")
            await session.rollback()
            return None

    async def upload_receipt(
        self,
        session: AsyncSession,
        payment_id: int,
        receipt_photo_id: str,
        receipt_file_id: str
    ) -> bool:
        """Upload receipt photo for a phone transfer payment"""
        try:
            payment = await session.get(PhoneTransferPayment, payment_id)
            if not payment:
                logging.error(f"Phone transfer payment {payment_id} not found")
                return False

            if payment.status != "pending":
                logging.warning(f"Payment {payment_id} is not in pending status: {payment.status}")
                return False

            payment.receipt_photo_id = receipt_photo_id
            payment.receipt_file_id = receipt_file_id
            payment.updated_at = datetime.now(timezone.utc)

            await session.commit()
            logging.info(f"Receipt uploaded for phone transfer payment {payment_id}")
            return True

        except Exception as e:
            logging.error(f"Error uploading receipt for payment {payment_id}: {e}")
            await session.rollback()
            return False

    async def approve_payment(
        self,
        session: AsyncSession,
        payment_id: int,
        admin_id: int,
        notes: Optional[str] = None
    ) -> bool:
        """Approve a phone transfer payment"""
        try:
            payment = await session.get(PhoneTransferPayment, payment_id)
            if not payment:
                logging.error(f"Phone transfer payment {payment_id} not found")
                return False

            if payment.status != "pending":
                logging.warning(f"Payment {payment_id} is not in pending status: {payment.status}")
                return False

            payment.status = "approved"
            payment.approved_at = datetime.now(timezone.utc)
            payment.approved_by_admin_id = admin_id
            payment.admin_notes = notes
            payment.updated_at = datetime.now(timezone.utc)

            await session.commit()
            logging.info(f"Phone transfer payment {payment_id} approved by admin {admin_id}")
            return True

        except Exception as e:
            logging.error(f"Error approving payment {payment_id}: {e}")
            await session.rollback()
            return False

    async def reject_payment(
        self,
        session: AsyncSession,
        payment_id: int,
        admin_id: int,
        reason: str,
        notes: Optional[str] = None
    ) -> bool:
        """Reject a phone transfer payment"""
        try:
            payment = await session.get(PhoneTransferPayment, payment_id)
            if not payment:
                logging.error(f"Phone transfer payment {payment_id} not found")
                return False

            if payment.status != "pending":
                logging.warning(f"Payment {payment_id} is not in pending status: {payment.status}")
                return False

            payment.status = "rejected"
            payment.rejected_at = datetime.now(timezone.utc)
            payment.rejected_by_admin_id = admin_id
            payment.rejection_reason = reason
            payment.admin_notes = notes
            payment.updated_at = datetime.now(timezone.utc)

            await session.commit()
            logging.info(f"Phone transfer payment {payment_id} rejected by admin {admin_id}: {reason}")
            return True

        except Exception as e:
            logging.error(f"Error rejecting payment {payment_id}: {e}")
            await session.rollback()
            return False

    def get_transfer_instructions(self, amount: float, currency: str, months: int) -> str:
        """Get formatted transfer instructions for the user"""
        instructions = f"💳 <b>Перевод на номер телефона</b>\n\n"
        
        if self.bank_name:
            instructions += f"🏦 Банк: <b>{self.bank_name}</b>\n"
        
        instructions += f"📱 Номер: <b>{self.phone_number}</b>\n"
        instructions += f"💰 Сумма: <b>{amount} {currency}</b>\n"
        instructions += f"📅 Срок подписки: <b>{months} мес.</b>\n\n"
        
        if self.instructions:
            instructions += f"📋 <b>Дополнительные инструкции:</b>\n{self.instructions}\n\n"
        
        instructions += "📸 После перевода загрузите скриншот или фото чека для подтверждения."
        
        return instructions

    def is_configured(self) -> bool:
        """Check if phone transfer service is properly configured"""
        return self.enabled and self.phone_number is not None
