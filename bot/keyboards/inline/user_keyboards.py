from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from typing import Dict, Optional, List
import logging

from config.settings import Settings


def get_main_menu_inline_keyboard(
        lang: str,
        i18n_instance,
        settings: Settings,
        show_trial_button: bool = False) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()

    if show_trial_button and settings.TRIAL_ENABLED:
        builder.row(
            InlineKeyboardButton(text=_(key="menu_activate_trial_button"),
                                 callback_data="main_action:request_trial"))

    builder.row(
        InlineKeyboardButton(text=_(key="menu_subscribe_inline"),
                             callback_data="main_action:subscribe"))
    if settings.SUBSCRIPTION_MINI_APP_URL:
        builder.row(
            InlineKeyboardButton(
                text=_(key="menu_my_subscription_inline"),
                web_app=WebAppInfo(url=settings.SUBSCRIPTION_MINI_APP_URL),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=_(key="menu_my_subscription_inline"),
                callback_data="main_action:my_subscription",
            )
        )

    referral_button = InlineKeyboardButton(
        text=_(key="menu_referral_inline"),
        callback_data="main_action:referral")
    promo_button = InlineKeyboardButton(
        text=_(key="menu_apply_promo_button"),
        callback_data="main_action:apply_promo")
    builder.row(referral_button, promo_button)

    language_button = InlineKeyboardButton(
        text=_(key="menu_language_settings_inline"),
        callback_data="main_action:language")
    status_button_list = []
    if settings.SERVER_STATUS_URL:
        status_button_list.append(
            InlineKeyboardButton(text=_(key="menu_server_status_button"),
                                 url=settings.SERVER_STATUS_URL))

    if status_button_list:
        builder.row(language_button, *status_button_list)
    else:
        builder.row(language_button)

    if settings.SUPPORT_LINK:
        builder.row(
            InlineKeyboardButton(text=_(key="menu_support_button"),
                                 url=settings.SUPPORT_LINK))

    if settings.TERMS_OF_SERVICE_URL:
        builder.row(
            InlineKeyboardButton(text=_(key="menu_terms_button"),
                                 url=settings.TERMS_OF_SERVICE_URL))

    return builder.as_markup()


def get_language_selection_keyboard(i18n_instance,
                                    current_lang: str) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(current_lang, key, **kwargs
                                                    )
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🇬🇧 English {'✅' if current_lang == 'en' else ''}",
                   callback_data="set_lang_en")
    builder.button(text=f"🇷🇺 Русский {'✅' if current_lang == 'ru' else ''}",
                   callback_data="set_lang_ru")
    builder.button(text=_(key="back_to_main_menu_button"),
                   callback_data="main_action:back_to_main")
    builder.adjust(1)
    return builder.as_markup()


def get_trial_confirmation_keyboard(lang: str,
                                    i18n_instance) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(text=_(key="trial_confirm_activate_button"),
                   callback_data="trial_action:confirm_activate")
    builder.button(text=_(key="cancel_button"),
                   callback_data="main_action:back_to_main")
    builder.adjust(1)
    return builder.as_markup()


def get_subscription_options_keyboard(subscription_options: Dict[
    int, Optional[int]], currency_symbol_val: str, lang: str,
                                      i18n_instance) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    if subscription_options:
        for months, price in subscription_options.items():
            if price is not None:
                button_text = _("subscribe_for_months_button",
                                months=months,
                                price=price,
                                currency_symbol=currency_symbol_val)
                builder.button(text=button_text,
                               callback_data=f"subscribe_period:{months}")
        builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text=_(key="back_to_main_menu_button"),
                             callback_data="main_action:back_to_main"))
    return builder.as_markup()


def get_payment_method_keyboard(months: int, price: float,
                                tribute_url: Optional[str],
                                stars_price: Optional[int],
                                currency_symbol_val: str, lang: str,
                                i18n_instance, settings: Settings) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    
    logging.info(f"Building payment method keyboard: PHONE_TRANSFER_ENABLED={settings.PHONE_TRANSFER_ENABLED}")
    
    if settings.STARS_ENABLED and stars_price is not None:
        builder.button(text=_("pay_with_stars_button"),
                       callback_data=f"pay_stars:{months}:{stars_price}")
    if settings.TRIBUTE_ENABLED and tribute_url:
        builder.button(text=_("pay_with_tribute_button"), url=tribute_url)
    if settings.YOOKASSA_ENABLED:
        builder.button(text=_("pay_with_yookassa_button"),
                       callback_data=f"pay_yk:{months}:{price}")
    if settings.CRYPTOPAY_ENABLED:
        builder.button(text=_("pay_with_cryptopay_button"),
                       callback_data=f"pay_crypto:{months}:{price}")
    if settings.PHONE_TRANSFER_ENABLED:
        logging.info("Adding phone transfer button to keyboard")
        builder.button(text=_("pay_with_phone_transfer_button"),
                       callback_data=f"pay_phone_transfer:{months}:{price}")
    else:
        logging.warning("Phone transfer is disabled in settings")
    
    builder.button(text=_(key="cancel_button"),
                   callback_data="main_action:subscribe")
    builder.adjust(1)
    return builder.as_markup()


def get_payment_url_keyboard(payment_url: str, lang: str,
                             i18n_instance) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(text=_(key="pay_button"), url=payment_url)
    builder.button(text=_(key="back_to_main_menu_button"),
                   callback_data="main_action:back_to_main")
    builder.adjust(1)
    return builder.as_markup()


def get_referral_link_keyboard(lang: str,
                               i18n_instance) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(text=_(key="referral_share_message_button"),
                   callback_data="referral_action:share_message")
    builder.button(text=_(key="back_to_main_menu_button"),
                   callback_data="main_action:back_to_main")
    builder.adjust(1)
    return builder.as_markup()


def get_back_to_main_menu_markup(lang: str,
                                 i18n_instance) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(text=_(key="back_to_main_menu_button"),
                   callback_data="main_action:back_to_main")
    return builder.as_markup()


def get_subscribe_only_markup(lang: str, i18n_instance) -> InlineKeyboardMarkup:
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(text=_(key="menu_subscribe_inline"),
                   callback_data="main_action:subscribe")
    return builder.as_markup()


def get_user_banned_keyboard(support_link: Optional[str], lang: str,
                             i18n_instance) -> Optional[InlineKeyboardMarkup]:
    if not support_link:
        return None
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    builder.button(text=_(key="menu_support_button"), url=support_link)
    return builder.as_markup()


def get_connect_and_main_keyboard(
        lang: str,
        i18n_instance,
        settings: Settings,
        config_link: Optional[str]) -> InlineKeyboardMarkup:
    """Keyboard with a connect button and a back to main menu button."""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()

    if settings.SUBSCRIPTION_MINI_APP_URL:
        builder.row(
            InlineKeyboardButton(
                text=_("connect_button"),
                web_app=WebAppInfo(url=settings.SUBSCRIPTION_MINI_APP_URL),
            )
        )
    elif config_link:
        builder.row(
            InlineKeyboardButton(text=_("connect_button"), url=config_link)
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=_("connect_button"),
                callback_data="main_action:my_subscription",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text=_("back_to_main_menu_button"),
            callback_data="main_action:back_to_main",
        )
    )

    return builder.as_markup()


def get_phone_transfer_receipt_keyboard(payment_id: int, lang: str, i18n_instance) -> InlineKeyboardMarkup:
    """Keyboard for phone transfer payment receipt upload"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text=_("upload_receipt_button", default="📸 Загрузить чек"),
        callback_data=f"upload_receipt:{payment_id}"
    )
    builder.button(
        text=_("cancel_button"),
        callback_data="main_action:subscribe"
    )
    builder.adjust(1)
    return builder.as_markup()


def get_phone_transfer_pending_keyboard(lang: str, i18n_instance) -> InlineKeyboardMarkup:
    """Keyboard for pending phone transfer payment"""
    _ = lambda key, **kwargs: i18n_instance.gettext(lang, key, **kwargs)
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text=_("payment_pending_button", default="⏳ Ожидает подтверждения"),
        callback_data="phone_transfer_pending"
    )
    builder.button(
        text=_("back_to_main_menu_button"),
        callback_data="main_action:back_to_main"
    )
    builder.adjust(1)
    return builder.as_markup()
