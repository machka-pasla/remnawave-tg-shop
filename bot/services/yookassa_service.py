import uuid
import logging
import asyncio
from typing import Optional, Dict, Any, List

from yookassa import Configuration, Payment as YooKassaPayment
from yookassa.domain.request.payment_request_builder import PaymentRequestBuilder
from yookassa.domain.common.confirmation_type import ConfirmationType

from config.settings import Settings


class YooKassaService:

    def __init__(self,
                 shop_id: Optional[str],
                 secret_key: Optional[str],
                 configured_return_url: Optional[str],
                 bot_username_for_default_return: Optional[str] = None,
                 settings_obj: Optional[Settings] = None):

        self.settings = settings_obj

        if not shop_id or not secret_key:
            logging.warning(
                "YooKassa SHOP_ID or SECRET_KEY not configured in settings. "
                "Payment functionality will be DISABLED.")
            self.configured = False
        else:
            try:
                Configuration.configure(shop_id, secret_key)
                self.configured = True
                logging.info(
                    f"YooKassa SDK configured for shop_id: {shop_id[:5]}...")
            except Exception as e:
                logging.error(f"Failed to configure YooKassa SDK: {e}",
                              exc_info=True)
                self.configured = False

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
                f"CRITICAL: YOOKASSA_RETURN_URL not set AND bot username not provided. "
                f"Using placeholder: {self.return_url}. Payments may not complete correctly."
            )
        logging.info(
            f"YooKassa Service effective return_url for payments: {self.return_url}"
        )

    async def create_payment(
            self,
            amount: float,
            currency: str,
            description: str,
            metadata: Dict[str, Any],
            receipt_email: Optional[str] = None,
            receipt_phone: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.configured:
            logging.error("YooKassa is not configured. Cannot create payment.")
            return None

        if not self.settings:
            logging.error(
                "YooKassaService: Settings object not available. Cannot create payment with receipt details."
            )
            return {
                "error":
                True,
                "internal_message":
                "Service settings (Settings object) not initialized."
            }

        customer_contact_for_receipt = {}
        if receipt_email:
            customer_contact_for_receipt["email"] = receipt_email
        elif receipt_phone:
            customer_contact_for_receipt["phone"] = receipt_phone
        elif self.settings.YOOKASSA_DEFAULT_RECEIPT_EMAIL:
            customer_contact_for_receipt[
                "email"] = self.settings.YOOKASSA_DEFAULT_RECEIPT_EMAIL
        else:
            logging.error(
                "CRITICAL: No email/phone for YooKassa receipt provided and YOOKASSA_DEFAULT_RECEIPT_EMAIL is not set."
            )
            return {
                "error":
                True,
                "internal_message":
                "YooKassa receipt customer contact (email/phone) missing and no default email configured."
            }

        try:
            builder = PaymentRequestBuilder()
            builder.set_amount({
                "value": str(round(amount, 2)),
                "currency": currency.upper()
            })
            builder.set_capture(True)
            builder.set_confirmation({
                "type": ConfirmationType.REDIRECT,
                "return_url": self.return_url
            })
            builder.set_description(description)
            builder.set_metadata(metadata)

            receipt_items_list: List[Dict[str, Any]] = [{
                "description":
                description[:128],
                "quantity":
                "1.00",
                "amount": {
                    "value": str(round(amount, 2)),
                    "currency": currency.upper()
                },
                "vat_code":
                str(self.settings.YOOKASSA_VAT_CODE),
                "payment_mode":
                self.settings.YOOKASSA_PAYMENT_MODE,
                "payment_subject":
                self.settings.YOOKASSA_PAYMENT_SUBJECT
            }]

            receipt_data_dict: Dict[str, Any] = {
                "customer": customer_contact_for_receipt,
                "items": receipt_items_list
            }

            builder.set_receipt(receipt_data_dict)

            idempotence_key = str(uuid.uuid4())
            payment_request = builder.build()

            logging.info(
                f"Creating YooKassa payment (Idempotence-Key: {idempotence_key}). "
                f"Amount: {amount} {currency}. Metadata: {metadata}. Receipt: {receipt_data_dict}"
            )

            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, lambda: YooKassaPayment.create(payment_request,
                                                     idempotence_key))

            logging.info(
                f"YooKassa Payment.create response: ID={response.id}, Status={response.status}, Paid={response.paid}"
            )

            return {
                "id":
                response.id,
                "confirmation_url":
                response.confirmation.confirmation_url
                if response.confirmation else None,
                "status":
                response.status,
                "metadata":
                response.metadata,
                "amount_value":
                float(response.amount.value),
                "amount_currency":
                response.amount.currency,
                "idempotence_key_used":
                idempotence_key,
                "paid":
                response.paid,
                "refundable":
                response.refundable,
                "created_at":
                response.created_at.isoformat() if hasattr(
                    response.created_at, 'isoformat') else str(
                        response.created_at),
                "description_from_yk":
                response.description,
                "test_mode":
                response.test if hasattr(response, 'test') else None
            }
        except Exception as e:
            logging.error(f"YooKassa payment creation failed: {e}",
                          exc_info=True)
            return None

    async def get_payment_info(
            self, payment_id_in_yookassa: str) -> Optional[Dict[str, Any]]:
        if not self.configured:
            logging.error(
                "YooKassa is not configured. Cannot get payment info.")
            return None
        try:
            logging.info(
                f"Fetching payment info from YooKassa for ID: {payment_id_in_yookassa}"
            )

            loop = asyncio.get_running_loop()
            payment_info_yk = await loop.run_in_executor(
                None, lambda: YooKassaPayment.find_one(payment_id_in_yookassa))

            if payment_info_yk:
                logging.info(
                    f"YooKassa payment info for {payment_id_in_yookassa}: Status={payment_info_yk.status}, Paid={payment_info_yk.paid}"
                )
                return {
                    "id":
                    payment_info_yk.id,
                    "status":
                    payment_info_yk.status,
                    "paid":
                    payment_info_yk.paid,
                    "amount_value":
                    float(payment_info_yk.amount.value),
                    "amount_currency":
                    payment_info_yk.amount.currency,
                    "metadata":
                    payment_info_yk.metadata,
                    "description":
                    payment_info_yk.description,
                    "refundable":
                    payment_info_yk.refundable,
                    "created_at":
                    payment_info_yk.created_at.isoformat() if hasattr(
                        payment_info_yk.created_at, 'isoformat') else str(
                            payment_info_yk.created_at),
                    "captured_at":
                    payment_info_yk.captured_at.isoformat()
                    if payment_info_yk.captured_at and hasattr(
                        payment_info_yk.captured_at, 'isoformat') else None,
                    "payment_method_type":
                    payment_info_yk.payment_method.type
                    if payment_info_yk.payment_method else None,
                    "test_mode":
                    payment_info_yk.test
                    if hasattr(payment_info_yk, 'test') else None
                }
            else:
                logging.warning(
                    f"No payment info found in YooKassa for ID: {payment_id_in_yookassa}"
                )
                return None
        except Exception as e:
            logging.error(
                f"YooKassa get payment info for {payment_id_in_yookassa} failed: {e}",
                exc_info=True)
            return None
