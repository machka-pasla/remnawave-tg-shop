import logging
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from aiohttp import web
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from yookassa.domain.notification import WebhookNotification
from yookassa.domain.models.amount import Amount as YooKassaAmount

from db.dal import payment_dal, user_dal

from bot.services.subscription_service import SubscriptionService
from bot.services.referral_service import ReferralService
from bot.services.panel_api_service import PanelApiService
from bot.services.payment_service import YooKassaService
from bot.middlewares.i18n import JsonI18n
from config.settings import Settings

payment_processing_lock = asyncio.Lock()

YOOKASSA_EVENT_PAYMENT_SUCCEEDED = 'payment.succeeded'
YOOKASSA_EVENT_PAYMENT_CANCELED = 'payment.canceled'


async def process_successful_payment(session: AsyncSession, bot: Bot,
                                     payment_info_from_webhook: dict,
                                     i18n: JsonI18n, settings: Settings,
                                     panel_service: PanelApiService,
                                     subscription_service: SubscriptionService,
                                     referral_service: ReferralService):
    metadata = payment_info_from_webhook.get("metadata", {})
    user_id_str = metadata.get("user_id")
    subscription_months_str = metadata.get("subscription_months")
    promo_code_id_str = metadata.get("promo_code_id")
    payment_db_id_str = metadata.get("payment_db_id")

    if not user_id_str or not subscription_months_str or not payment_db_id_str:
        logging.error(
            f"Missing crucial metadata for payment: {payment_info_from_webhook.get('id')}, metadata: {metadata}"
        )
        return

    db_user = None
    try:
        user_id = int(user_id_str)
        subscription_months = int(subscription_months_str)
        payment_db_id = int(payment_db_id_str)
        promo_code_id = int(
            promo_code_id_str
        ) if promo_code_id_str and promo_code_id_str.isdigit() else None

        amount_data = payment_info_from_webhook.get("amount", {})
        payment_value = float(amount_data.get("value", 0.0))

        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logging.error(
                f"User {user_id} not found in DB during successful payment processing for YK ID {payment_info_from_webhook.get('id')}. Payment record {payment_db_id}."
            )

            await payment_dal.update_payment_status_by_db_id(
                session, payment_db_id, "failed_user_not_found",
                payment_info_from_webhook.get("id"))

            return

    except (TypeError, ValueError) as e:
        logging.error(
            f"Invalid metadata format for payment processing: {metadata} - {e}"
        )

        if payment_db_id_str and payment_db_id_str.isdigit():
            try:
                await payment_dal.update_payment_status_by_db_id(
                    session, int(payment_db_id_str), "failed_metadata_error",
                    payment_info_from_webhook.get("id"))
            except Exception as e_upd:
                logging.error(
                    f"Failed to update payment status after metadata error: {e_upd}"
                )
        return

    try:
        yk_payment_id_from_hook = payment_info_from_webhook.get("id")
        updated_payment_record = await payment_dal.update_payment_status_by_db_id(
            session,
            payment_db_id=payment_db_id,
            new_status=payment_info_from_webhook.get("status", "succeeded"),
            yk_payment_id=yk_payment_id_from_hook)
        if not updated_payment_record:
            logging.error(
                f"Failed to update payment record {payment_db_id} for yk_id {yk_payment_id_from_hook}"
            )
            raise Exception(
                f"DB Error: Could not update payment record {payment_db_id}")

        activation_details = await subscription_service.activate_subscription(
            session,
            user_id,
            subscription_months,
            payment_value,
            payment_db_id,
            promo_code_id_from_payment=promo_code_id,
            provider="yookassa")

        if not activation_details or not activation_details.get('end_date'):
            logging.error(
                f"Failed to activate subscription for user {user_id} after payment {yk_payment_id_from_hook}"
            )
            raise Exception(
                f"Subscription Error: Failed to activate for user {user_id}")

        base_subscription_end_date = activation_details['end_date']
        final_end_date_for_user = base_subscription_end_date
        applied_promo_bonus_days = activation_details.get(
            "applied_promo_bonus_days", 0)

        referral_bonus_info = await referral_service.apply_referral_bonuses_for_payment(
            session, user_id, subscription_months)
        applied_referee_bonus_days_from_referral: Optional[int] = None
        if referral_bonus_info and referral_bonus_info.get(
                "referee_new_end_date"):
            final_end_date_for_user = referral_bonus_info[
                "referee_new_end_date"]
            applied_referee_bonus_days_from_referral = referral_bonus_info.get(
                "referee_bonus_applied_days")

        user_lang = db_user.language_code if db_user and db_user.language_code else settings.DEFAULT_LANGUAGE
        _ = lambda key, **kwargs: i18n.gettext(user_lang, key, **kwargs)

        success_message = ""
        if applied_referee_bonus_days_from_referral and final_end_date_for_user:
            inviter_name_display = _("friend_placeholder")
            if db_user and db_user.referred_by_id:
                inviter = await user_dal.get_user_by_id(
                    session, db_user.referred_by_id)
                if inviter and inviter.first_name:
                    inviter_name_display = inviter.first_name
                elif inviter and inviter.username:
                    inviter_name_display = f"@{inviter.username}"

            success_message = _(
                "payment_successful_with_referral_bonus",
                months=subscription_months,
                base_end_date=base_subscription_end_date.strftime('%Y-%m-%d'),
                bonus_days=applied_referee_bonus_days_from_referral,
                final_end_date=final_end_date_for_user.strftime('%Y-%m-%d'),
                inviter_name=inviter_name_display)
        elif applied_promo_bonus_days > 0 and final_end_date_for_user:
            success_message = _(
                "payment_successful_with_promo",
                months=subscription_months,
                bonus_days=applied_promo_bonus_days,
                end_date=final_end_date_for_user.strftime('%Y-%m-%d'))
        elif final_end_date_for_user:
            success_message = _(
                "payment_successful",
                months=subscription_months,
                end_date=final_end_date_for_user.strftime('%Y-%m-%d'))
        else:
            logging.error(
                f"Critical error: final_end_date_for_user is None for user {user_id} after successful payment logic."
            )
            success_message = _("payment_successful_error_details")

        try:
            await bot.send_message(user_id, success_message)
        except Exception as e_notify:
            logging.error(
                f"Failed to send final payment success message to user {user_id}: {e_notify}"
            )

    except Exception as e_process:
        logging.error(
            f"Error during process_successful_payment main try block for user {user_id}: {e_process}",
            exc_info=True)

        raise


async def process_cancelled_payment(session: AsyncSession, bot: Bot,
                                    payment_info_from_webhook: dict,
                                    i18n: JsonI18n, settings: Settings):

    metadata = payment_info_from_webhook.get("metadata", {})
    user_id_str = metadata.get("user_id")
    payment_db_id_str = metadata.get("payment_db_id")

    if not user_id_str or not payment_db_id_str:
        logging.warning(
            f"Missing metadata in cancelled payment webhook: {payment_info_from_webhook.get('id')}"
        )
        return
    try:
        user_id = int(user_id_str)
        payment_db_id = int(payment_db_id_str)
    except ValueError:
        logging.error(
            f"Invalid metadata in cancelled payment webhook: {metadata}")
        return

    try:
        updated_payment = await payment_dal.update_payment_status_by_db_id(
            session,
            payment_db_id=payment_db_id,
            new_status=payment_info_from_webhook.get("status", "canceled"),
            yk_payment_id=payment_info_from_webhook.get("id"))

        if updated_payment:
            logging.info(
                f"Payment {payment_db_id} (YK: {payment_info_from_webhook.get('id')}) status updated to cancelled for user {user_id}."
            )
        else:
            logging.warning(
                f"Could not find payment record {payment_db_id} to update status to cancelled for user {user_id}."
            )

        db_user = await user_dal.get_user_by_id(session, user_id)
        user_lang = settings.DEFAULT_LANGUAGE
        if db_user and db_user.language_code: user_lang = db_user.language_code

        _ = lambda key, **kwargs: i18n.gettext(user_lang, key, **kwargs)
        await bot.send_message(user_id, _("payment_failed"))

    except Exception as e_process_cancel:
        logging.error(
            f"Error processing cancelled payment for user {user_id}, payment_db_id {payment_db_id}: {e_process_cancel}",
            exc_info=True)
        raise


async def yookassa_webhook_route(request: web.Request):

    try:
        bot: Bot = request.app['bot']
        i18n_instance: JsonI18n = request.app['i18n']
        settings: Settings = request.app['settings']
        panel_service: PanelApiService = request.app['panel_service']
        subscription_service: SubscriptionService = request.app[
            'subscription_service']
        referral_service: ReferralService = request.app['referral_service']
        async_session_factory: sessionmaker = request.app[
            'async_session_factory']
    except KeyError as e_app_ctx:
        logging.error(
            f"KeyError accessing app context in yookassa_webhook_route: {e_app_ctx}.",
            exc_info=True)
        return web.Response(
            status=500,
            text="Internal Server Error: Missing app context component")

    try:
        event_json = await request.json()

        notification_object = WebhookNotification(event_json)
        payment_data_from_notification = notification_object.object

        logging.info(
            f"YooKassa Webhook Parsed: Event='{notification_object.event}', "
            f"PaymentId='{payment_data_from_notification.id}', Status='{payment_data_from_notification.status}'"
        )

        if not payment_data_from_notification or not hasattr(
                payment_data_from_notification,
                'metadata') or payment_data_from_notification.metadata is None:
            logging.error(
                f"YooKassa webhook payment {payment_data_from_notification.id} lacks metadata. Cannot process."
            )
            return web.Response(status=200, text="ok_error_no_metadata")

        payment_dict_for_processing = {
            "id":
            str(payment_data_from_notification.id),
            "status":
            str(payment_data_from_notification.status),
            "paid":
            bool(payment_data_from_notification.paid),
            "amount": {
                "value": str(payment_data_from_notification.amount.value),
                "currency": str(payment_data_from_notification.amount.currency)
            } if payment_data_from_notification.amount else {},
            "metadata":
            dict(payment_data_from_notification.metadata),
            "description":
            str(payment_data_from_notification.description)
            if payment_data_from_notification.description else None,
        }

        async with payment_processing_lock:
            async with async_session_factory() as session:
                try:
                    if notification_object.event == YOOKASSA_EVENT_PAYMENT_SUCCEEDED:
                        if payment_dict_for_processing.get(
                                "paid") and payment_dict_for_processing.get(
                                    "status") == "succeeded":
                            await process_successful_payment(
                                session, bot, payment_dict_for_processing,
                                i18n_instance, settings, panel_service,
                                subscription_service, referral_service)
                            await session.commit()
                        else:
                            logging.warning(
                                f"Payment Succeeded event for {payment_dict_for_processing.get('id')} "
                                f"but data not as expected: status='{payment_dict_for_processing.get('status')}', "
                                f"paid='{payment_dict_for_processing.get('paid')}'"
                            )
                    elif notification_object.event == YOOKASSA_EVENT_PAYMENT_CANCELED:
                        await process_cancelled_payment(
                            session, bot, payment_dict_for_processing,
                            i18n_instance, settings)
                        await session.commit()
                except Exception as e_webhook_db_processing:
                    await session.rollback()
                    logging.error(
                        f"Error processing YooKassa webhook event '{notification_object.event}' "
                        f"for YK Payment ID {payment_dict_for_processing.get('id')} in DB transaction: {e_webhook_db_processing}",
                        exc_info=True)
                    return web.Response(
                        status=200, text="ok_internal_processing_error_logged")

        return web.Response(status=200, text="ok")

    except json.JSONDecodeError:
        logging.error("YooKassa Webhook: Invalid JSON received.")
        return web.Response(status=400, text="bad_request_invalid_json")
    except Exception as e_general_webhook:
        logging.error(
            f"YooKassa Webhook general processing error: {e_general_webhook}",
            exc_info=True)
        return web.Response(status=200,
                            text="ok_general_internal_error_logged")
