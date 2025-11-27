import uuid
import logging
import asyncio
from typing import Optional, Dict, Any, List

from yookassa import Configuration, Payment as YooKassaPayment
from yookassa.domain.request.payment_request_builder import PaymentRequestBuilder
from yookassa.domain.common.confirmation_type import ConfirmationType

from config.settings import Settings


class YooKassaService:

    def __init__(
        self,
        shop_id: Optional[str],
        secret_key: Optional[str],
        configured_return_url: Optional[str],
        bot_username_for_default_return: Optional[str] = None,
        settings_obj: Optional[Settings] = None
    ):

        self.settings = settings_obj

        if not shop_id or not secret_key:
            logging.warning(
                "YooKassa SHOP_ID or SECRET_KEY not configured in settings. "
                "Payment functionality will be DISABLED."
            )
            self.configured = False
        else:
            try:
                Configuration.configure(shop_id, secret_key)
                self.configured = True
                logging.info(f"YooKassa SDK configured for shop_id: {shop_id[:5]}...")
            except Exception as e:
                logging.error(f"Failed to configure YooKassa SDK: {e}", exc_info=True)
                self.configured = False

        # Return URL
        if configured_return_url:
            self.return_url = configured_return_url
        elif bot_username_for_default_return:
            self.return_url = f"https://t.me/{bot_username_for_default_return}"
            logging.info(
                f"YOOKASSA_RETURN_URL not set, using dynamic default based on bot username: {self.return_url}"
            )
        else:
            self.return_url = "https://example.com/payment_error_no_return_url_configured"
            logging.warning(
                "CRITICAL: YOOKASSA_RETURN_URL not set AND bot username not provided."
            )

        logging.info(f"YooKassa Service effective return_url: {self.return_url}")

    # -------------------------------------------------------------------------
    #   BASE PAYMENT CREATOR (full receipt, metadata, bind, etc)
    # -------------------------------------------------------------------------
    async def create_payment(
        self,
        amount: float,
        currency: str,
        description: str,
        metadata: Dict[str, Any],
        receipt_email: Optional[str] = None,
        receipt_phone: Optional[str] = None,
        save_payment_method: bool = False,
        payment_method_id: Optional[str] = None,
        capture: bool = True,
        bind_only: bool = False
    ) -> Optional[Dict[str, Any]]:

        if not self.configured:
            logging.error("YooKassa is not configured.")
            return None

        if not self.settings:
            logging.error("Settings object is missing in YooKassaService")
            return {"error": True, "internal_message": "Settings missing"}

        # Receipt contact
        customer_contact_for_receipt = {}
        if receipt_email:
            customer_contact_for_receipt["email"] = receipt_email
        elif receipt_phone:
            customer_contact_for_receipt["phone"] = receipt_phone
        elif self.settings.YOOKASSA_DEFAULT_RECEIPT_EMAIL:
            customer_contact_for_receipt["email"] = self.settings.YOOKASSA_DEFAULT_RECEIPT_EMAIL
        else:
            logging.error("Missing receipt email/phone and no default email configured")
            return {"error": True, "internal_message": "No receipt contact"}

        try:
            builder = PaymentRequestBuilder()

            builder.set_amount({
                "value": str(round(amount, 2)),
                "currency": currency.upper()
            })

            # Bind-only minimal amount
            if bind_only:
                capture = False
                amount = max(amount, 1.00)

            builder.set_capture(capture)

            builder.set_confirmation({
                "type": ConfirmationType.REDIRECT,
                "return_url": self.return_url
            })

            builder.set_description(description)
            builder.set_metadata(metadata)

            if save_payment_method:
                builder.set_save_payment_method(True)
            if payment_method_id:
                builder.set_payment_method_id(payment_method_id)

            # Receipt
            receipt_items_list: List[Dict[str, Any]] = [{
                "description": description[:128],
                "quantity": "1.00",
                "amount": {
                    "value": str(round(amount, 2)),
                    "currency": currency.upper()
                },
                "vat_code": str(self.settings.YOOKASSA_VAT_CODE),
                "payment_mode": getattr(self.settings, 'yk_receipt_payment_mode', self.settings.YOOKASSA_PAYMENT_MODE),
                "payment_subject": getattr(self.settings, 'yk_receipt_payment_subject', self.settings.YOOKASSA_PAYMENT_SUBJECT),
            }]

            receipt_data_dict: Dict[str, Any] = {
                "customer": customer_contact_for_receipt,
                "items": receipt_items_list
            }

            builder.set_receipt(receipt_data_dict)

            idempotence_key = str(uuid.uuid4())
            payment_request = builder.build()

            logging.info(
                f"Creating YooKassa payment | Amount: {amount}, Metadata: {metadata}"
            )

            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: YooKassaPayment.create(payment_request, idempotence_key)
            )

            logging.info(
                f"YK Payment created: ID={response.id}, Status={response.status}, Paid={response.paid}"
            )

            return {
                "id": response.id,
                "confirmation_url": response.confirmation.confirmation_url
                    if response.confirmation else None,
                "status": response.status,
                "metadata": response.metadata,
                "amount_value": float(response.amount.value),
                "amount_currency": response.amount.currency,
                "paid": response.paid,
            }

        except Exception as e:
            logging.error(f"YooKassa payment creation failed: {e}", exc_info=True)
            return None

    # -------------------------------------------------------------------------
    #   GET PAYMENT INFO
    # -------------------------------------------------------------------------
    async def get_payment_info(self, payment_id_in_yookassa: str) -> Optional[Dict[str, Any]]:

        if not self.configured:
            logging.error("YooKassa is not configured.")
            return None

        try:
            loop = asyncio.get_running_loop()
            payment_info = await loop.run_in_executor(
                None,
                lambda: YooKassaPayment.find_one(payment_id_in_yookassa)
            )

            if not payment_info:
                logging.warning(f"No payment info found for {payment_id_in_yookassa}")
                return None

            pm = getattr(payment_info, "payment_method", None)
            pm_payload = {}
            if pm:
                pm_payload = {
                    "id": getattr(pm, "id", None),
                    "type": getattr(pm, "type", None),
                    "title": getattr(pm, "title", None),
                    "card_last4": getattr(getattr(pm, "card", None), "last4", None),
                }

            return {
                "id": payment_info.id,
                "status": payment_info.status,
                "paid": payment_info.paid,
                "amount_value": float(payment_info.amount.value),
                "amount_currency": payment_info.amount.currency,
                "metadata": payment_info.metadata,
                "description": payment_info.description,
                "payment_method": pm_payload,
            }

        except Exception as e:
            logging.error(f"Failed to fetch YK payment info {payment_id_in_yookassa}: {e}")
            return None

    # -------------------------------------------------------------------------
    #   CANCEL PAYMENT
    # -------------------------------------------------------------------------
    async def cancel_payment(self, payment_id_in_yookassa: str) -> bool:
        if not self.configured:
            return False
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: YooKassaPayment.cancel(payment_id_in_yookassa)
            )
            return True
        except Exception as e:
            logging.error(f"Failed to cancel YK payment: {e}")
            return False

    # -------------------------------------------------------------------------
    #   🔥 COMPATIBILITY WRAPPER: create_yk_payment()
    # -------------------------------------------------------------------------
    async def create_yk_payment(
        self,
        amount: float,
        description: str,
        user_id: int,
        months: int,
        promo_code_id: int | None = None,
    ):
        """
        Обёртка, чтобы старый код в handlers/payments.py продолжал работать.
        Возвращает (payment_url, payment_id).
        """

        metadata = {
            "user_id": user_id,
            "months": months,
            "promo_code_id": promo_code_id,
        }

        result = await self.create_payment(
            amount=amount,
            currency="RUB",
            description=description,
            metadata=metadata,
            receipt_email=None,
            receipt_phone=None,
            save_payment_method=False,
            payment_method_id=None,
            capture=True,
            bind_only=False,
        )

        if not result or result.get("error"):
            raise Exception("YooKassa payment creation failed")

        return result["confirmation_url"], result["id"]