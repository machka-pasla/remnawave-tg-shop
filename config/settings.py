import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, ValidationError, computed_field, field_validator
from typing import Optional, List, Dict, Any


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS_STR: str = Field(
        default="",
        alias="ADMIN_IDS",
        description="Comma-separated list of admin Telegram User IDs")

    POSTGRES_USER: str = Field(default="user")
    POSTGRES_PASSWORD: str = Field(default="password")
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_DB: str = Field(default="vpn_shop_db")

    DEFAULT_LANGUAGE: str = Field(default="ru")
    DEFAULT_CURRENCY_SYMBOL: str = Field(default="RUB")

    SUPPORT_LINK: Optional[str] = Field(default=None)
    SERVER_STATUS_URL: Optional[str] = Field(default=None)
    TERMS_OF_SERVICE_URL: Optional[str] = Field(default=None)

    YOOKASSA_SHOP_ID: Optional[str] = None
    YOOKASSA_SECRET_KEY: Optional[str] = None
    YOOKASSA_RETURN_URL: Optional[str] = None

    YOOKASSA_DEFAULT_RECEIPT_EMAIL: Optional[str] = Field(default=None)
    YOOKASSA_VAT_CODE: int = Field(default=1)
    # Deprecated: explicit receipt fields are now derived from YOOKASSA_AUTOPAYMENTS_ENABLED
    YOOKASSA_PAYMENT_MODE: str = Field(default="full_prepayment")
    YOOKASSA_PAYMENT_SUBJECT: str = Field(default="service")
    # Single toggle to enable recurring payments (saving cards, managing payment methods, auto-renew)
    YOOKASSA_AUTOPAYMENTS_ENABLED: bool = Field(default=False)

    WEBHOOK_BASE_URL: Optional[str] = None

    CRYPTOPAY_TOKEN: Optional[str] = None
    CRYPTOPAY_NETWORK: str = Field(default="mainnet")
    CRYPTOPAY_CURRENCY_TYPE: str = Field(default="fiat")
    CRYPTOPAY_ASSET: str = Field(default="RUB")
    CRYPTOPAY_ENABLED: bool = Field(default=True)

    YOOKASSA_ENABLED: bool = Field(default=True)
    STARS_ENABLED: bool = Field(default=True)
    TRIBUTE_ENABLED: bool = Field(default=True)

    MONTH_1_ENABLED: bool = Field(default=True, alias="1_MONTH_ENABLED")
    MONTH_3_ENABLED: bool = Field(default=True, alias="3_MONTHS_ENABLED")
    MONTH_6_ENABLED: bool = Field(default=True, alias="6_MONTHS_ENABLED")
    MONTH_12_ENABLED: bool = Field(default=True, alias="12_MONTHS_ENABLED")

    RUB_PRICE_1_MONTH: Optional[int] = Field(default=None)
    RUB_PRICE_3_MONTHS: Optional[int] = Field(default=None)
    RUB_PRICE_6_MONTHS: Optional[int] = Field(default=None)
    RUB_PRICE_12_MONTHS: Optional[int] = Field(default=None)

    STARS_PRICE_1_MONTH: Optional[int] = Field(default=None)
    STARS_PRICE_3_MONTHS: Optional[int] = Field(default=None)
    STARS_PRICE_6_MONTHS: Optional[int] = Field(default=None)
    STARS_PRICE_12_MONTHS: Optional[int] = Field(default=None)


    TRIBUTE_LINK_1_MONTH: Optional[str] = Field(default=None)
    TRIBUTE_LINK_3_MONTHS: Optional[str] = Field(default=None)
    TRIBUTE_LINK_6_MONTHS: Optional[str] = Field(default=None)
    TRIBUTE_LINK_12_MONTHS: Optional[str] = Field(default=None)
    TRIBUTE_API_KEY: Optional[str] = Field(default=None)
    TRIBUTE_SKIP_NOTIFICATIONS: bool = Field(default=True, description="Skip renewal notifications for Tribute payments")
    TRIBUTE_SKIP_CANCELLATION_NOTIFICATIONS: bool = Field(default=False, description="Skip cancellation notifications for Tribute payments")
    PANEL_WEBHOOK_SECRET: Optional[str] = Field(default=None)

    SUBSCRIPTION_NOTIFICATIONS_ENABLED: bool = Field(default=True)
    SUBSCRIPTION_NOTIFY_ON_EXPIRE: bool = Field(default=True)
    SUBSCRIPTION_NOTIFY_AFTER_EXPIRE: bool = Field(default=True)
    SUBSCRIPTION_NOTIFY_DAYS_BEFORE: int = Field(default=3)

    REFERRAL_BONUS_DAYS_INVITER_1_MONTH: Optional[int] = Field(
        default=3, alias="REFERRAL_BONUS_DAYS_1_MONTH")
    REFERRAL_BONUS_DAYS_INVITER_3_MONTHS: Optional[int] = Field(
        default=7, alias="REFERRAL_BONUS_DAYS_3_MONTHS")
    REFERRAL_BONUS_DAYS_INVITER_6_MONTHS: Optional[int] = Field(
        default=15, alias="REFERRAL_BONUS_DAYS_6_MONTHS")
    REFERRAL_BONUS_DAYS_INVITER_12_MONTHS: Optional[int] = Field(
        default=30, alias="REFERRAL_BONUS_DAYS_12_MONTHS")

    REFERRAL_BONUS_DAYS_REFEREE_1_MONTH: Optional[int] = Field(
        default=1, alias="REFEREE_BONUS_DAYS_1_MONTH")
    REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS: Optional[int] = Field(
        default=3, alias="REFEREE_BONUS_DAYS_3_MONTHS")
    REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS: Optional[int] = Field(
        default=7, alias="REFEREE_BONUS_DAYS_6_MONTHS")
    REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS: Optional[int] = Field(
        default=15, alias="REFEREE_BONUS_DAYS_12_MONTHS")

    # Referral program configuration
    REFERRAL_ONE_BONUS_PER_REFEREE: bool = Field(
        default=True,
        description="When true, referral bonuses (for inviter and referee) are applied only once per invited user – on their first successful payment."
    )

    PANEL_API_URL: Optional[str] = None
    PANEL_API_KEY: Optional[str] = None
    USER_TRAFFIC_LIMIT_GB: Optional[float] = Field(default=0.0)
    USER_TRAFFIC_STRATEGY: str = Field(default="NO_RESET")
    USER_SQUAD_UUIDS: Optional[str] = Field(
        default=None,
        description=
        "Comma-separated UUIDs of internal squads to assign to new panel users")

    TRIAL_ENABLED: bool = Field(default=True)
    TRIAL_DURATION_DAYS: int = Field(default=3)
    TRIAL_TRAFFIC_LIMIT_GB: Optional[float] = Field(default=5.0)

    WEB_SERVER_HOST: str = Field(default="0.0.0.0")
    WEB_SERVER_PORT: int = Field(default=8080)
    LOGS_PAGE_SIZE: int = Field(default=10)

    SUBSCRIPTION_MINI_APP_URL: Optional[str] = Field(default=None)

    START_COMMAND_DESCRIPTION: Optional[str] = Field(default=None)
    DISABLE_WELCOME_MESSAGE: bool = Field(default=False, description="Disable welcome message on /start command")
    
    # Inline mode thumbnail URLs
    INLINE_REFERRAL_THUMBNAIL_URL: str = Field(default="https://cdn-icons-png.flaticon.com/512/1077/1077114.png")
    INLINE_USER_STATS_THUMBNAIL_URL: str = Field(default="https://cdn-icons-png.flaticon.com/512/681/681494.png")
    INLINE_FINANCIAL_STATS_THUMBNAIL_URL: str = Field(default="https://cdn-icons-png.flaticon.com/512/2769/2769339.png")
    INLINE_SYSTEM_STATS_THUMBNAIL_URL: str = Field(default="https://cdn-icons-png.flaticon.com/512/2920/2920277.png")

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @computed_field
    @property
    def ADMIN_IDS(self) -> List[int]:
        if self.ADMIN_IDS_STR:
            try:
                return [
                    int(admin_id.strip())
                    for admin_id in self.ADMIN_IDS_STR.split(',')
                    if admin_id.strip().isdigit()
                ]
            except ValueError:
                logging.error(
                    f"Invalid ADMIN_IDS_STR format: '{self.ADMIN_IDS_STR}'. Expected comma-separated integers."
                )
                return []
        return []

    @computed_field
    @property
    def PRIMARY_ADMIN_ID(self) -> Optional[int]:
        ids = self.ADMIN_IDS
        return ids[0] if ids else None

    @computed_field
    @property
    def trial_traffic_limit_bytes(self) -> int:
        if self.TRIAL_TRAFFIC_LIMIT_GB is None or self.TRIAL_TRAFFIC_LIMIT_GB <= 0:
            return 0
        return int(self.TRIAL_TRAFFIC_LIMIT_GB * (1024**3))

    @computed_field
    @property
    def user_traffic_limit_bytes(self) -> int:
        if self.USER_TRAFFIC_LIMIT_GB is None or self.USER_TRAFFIC_LIMIT_GB <= 0:
            return 0
        return int(self.USER_TRAFFIC_LIMIT_GB * (1024**3))

    @computed_field
    @property
    def parsed_user_squad_uuids(self) -> Optional[List[str]]:
        if self.USER_SQUAD_UUIDS:
            return [
                uuid.strip()
                for uuid in self.USER_SQUAD_UUIDS.split(',')
                if uuid.strip()
            ]
        return None

    @computed_field
    @property
    def yookassa_webhook_path(self) -> str:

        return "/webhook/yookassa"

    @computed_field
    @property
    def yookassa_full_webhook_url(self) -> Optional[str]:
        base = self.WEBHOOK_BASE_URL
        if base:
            return f"{base.rstrip('/')}{self.yookassa_webhook_path}"
        return None

    @computed_field
    @property
    def tribute_webhook_path(self) -> str:
        return "/webhook/tribute"

    @computed_field
    @property
    def tribute_full_webhook_url(self) -> Optional[str]:
        base = self.WEBHOOK_BASE_URL
        if base:
            return f"{base.rstrip('/')}{self.tribute_webhook_path}"
        return None

    @computed_field
    @property
    def panel_webhook_path(self) -> str:
        return "/webhook/panel"

    @computed_field
    @property
    def panel_full_webhook_url(self) -> Optional[str]:
        base = self.WEBHOOK_BASE_URL
        if base:
            return f"{base.rstrip('/')}{self.panel_webhook_path}"
        return None

    @computed_field
    @property
    def cryptopay_webhook_path(self) -> str:
        return "/webhook/cryptopay"

    @computed_field
    @property
    def cryptopay_full_webhook_url(self) -> Optional[str]:
        base = self.WEBHOOK_BASE_URL
        if base:
            return f"{base.rstrip('/')}{self.cryptopay_webhook_path}"
        return None

    # Computed YooKassa receipt fields based on recurring toggle
    @computed_field
    @property
    def yk_receipt_payment_mode(self) -> str:
        # If autopayments are enabled, use service; otherwise full prepayment
        return "service" if self.YOOKASSA_AUTOPAYMENTS_ENABLED else "full_prepayment"

    @computed_field
    @property
    def yk_receipt_payment_subject(self) -> str:
        # If autopayments are enabled, use full_payment; otherwise payment
        return "full_payment" if self.YOOKASSA_AUTOPAYMENTS_ENABLED else "payment"

    @computed_field
    @property
    def subscription_options(self) -> Dict[int, float]:
        options: Dict[int, float] = {}

        if self.MONTH_1_ENABLED and self.RUB_PRICE_1_MONTH is not None:
            options[1] = float(self.RUB_PRICE_1_MONTH)
        if self.MONTH_3_ENABLED and self.RUB_PRICE_3_MONTHS is not None:
            options[3] = float(self.RUB_PRICE_3_MONTHS)
        if self.MONTH_6_ENABLED and self.RUB_PRICE_6_MONTHS is not None:
            options[6] = float(self.RUB_PRICE_6_MONTHS)
        if self.MONTH_12_ENABLED and self.RUB_PRICE_12_MONTHS is not None:
            options[12] = float(self.RUB_PRICE_12_MONTHS)
        return options

    @computed_field
    @property
    def stars_subscription_options(self) -> Dict[int, int]:
        options: Dict[int, int] = {}
        if self.STARS_ENABLED and self.MONTH_1_ENABLED and self.STARS_PRICE_1_MONTH is not None:
            options[1] = self.STARS_PRICE_1_MONTH
        if self.STARS_ENABLED and self.MONTH_3_ENABLED and self.STARS_PRICE_3_MONTHS is not None:
            options[3] = self.STARS_PRICE_3_MONTHS
        if self.STARS_ENABLED and self.MONTH_6_ENABLED and self.STARS_PRICE_6_MONTHS is not None:
            options[6] = self.STARS_PRICE_6_MONTHS
        if self.STARS_ENABLED and self.MONTH_12_ENABLED and self.STARS_PRICE_12_MONTHS is not None:
            options[12] = self.STARS_PRICE_12_MONTHS
        return options

    @computed_field
    @property
    def tribute_payment_links(self) -> Dict[int, str]:
        links: Dict[int, str] = {}
        if self.TRIBUTE_ENABLED and self.MONTH_1_ENABLED and self.TRIBUTE_LINK_1_MONTH:
            links[1] = self.TRIBUTE_LINK_1_MONTH
        if self.TRIBUTE_ENABLED and self.MONTH_3_ENABLED and self.TRIBUTE_LINK_3_MONTHS:
            links[3] = self.TRIBUTE_LINK_3_MONTHS
        if self.TRIBUTE_ENABLED and self.MONTH_6_ENABLED and self.TRIBUTE_LINK_6_MONTHS:
            links[6] = self.TRIBUTE_LINK_6_MONTHS
        if self.TRIBUTE_ENABLED and self.MONTH_12_ENABLED and self.TRIBUTE_LINK_12_MONTHS:
            links[12] = self.TRIBUTE_LINK_12_MONTHS
        return links

    @computed_field
    @property
    def referral_bonus_inviter(self) -> Dict[int, int]:
        bonuses: Dict[int, int] = {}
        if self.REFERRAL_BONUS_DAYS_INVITER_1_MONTH is not None:
            bonuses[1] = self.REFERRAL_BONUS_DAYS_INVITER_1_MONTH
        if self.REFERRAL_BONUS_DAYS_INVITER_3_MONTHS is not None:
            bonuses[3] = self.REFERRAL_BONUS_DAYS_INVITER_3_MONTHS
        if self.REFERRAL_BONUS_DAYS_INVITER_6_MONTHS is not None:
            bonuses[6] = self.REFERRAL_BONUS_DAYS_INVITER_6_MONTHS
        if self.REFERRAL_BONUS_DAYS_INVITER_12_MONTHS is not None:
            bonuses[12] = self.REFERRAL_BONUS_DAYS_INVITER_12_MONTHS
        return bonuses

    @computed_field
    @property
    def referral_bonus_referee(self) -> Dict[int, int]:
        bonuses: Dict[int, int] = {}
        if self.REFERRAL_BONUS_DAYS_REFEREE_1_MONTH is not None:
            bonuses[1] = self.REFERRAL_BONUS_DAYS_REFEREE_1_MONTH
        if self.REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS is not None:
            bonuses[3] = self.REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS
        if self.REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS is not None:
            bonuses[6] = self.REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS
        if self.REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS is not None:
            bonuses[12] = self.REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS
        return bonuses
    
    # Logging Configuration
    LOG_CHAT_ID: Optional[int] = Field(default=None, description="Telegram chat/group ID for sending notifications")
    LOG_THREAD_ID: Optional[int] = Field(default=None, description="Thread ID for supergroup messages (optional)")
    
    @field_validator('LOG_CHAT_ID', 'LOG_THREAD_ID', mode='before')
    @classmethod
    def validate_optional_int_fields(cls, v):
        """Convert empty strings to None for optional integer fields"""
        if isinstance(v, str) and v.strip() == '':
            return None
        return v
    
    # Notification types
    LOG_NEW_USERS: bool = Field(default=True, description="Send notifications for new user registrations")
    LOG_PAYMENTS: bool = Field(default=True, description="Send notifications for successful payments")
    LOG_PROMO_ACTIVATIONS: bool = Field(default=True, description="Send notifications for promo code activations")
    LOG_TRIAL_ACTIVATIONS: bool = Field(default=True, description="Send notifications for trial activations")
    LOG_SUSPICIOUS_ACTIVITY: bool = Field(default=True, description="Send notifications for suspicious promo attempts")

    model_config = SettingsConfigDict(env_file='.env',
                                      env_file_encoding='utf-8',
                                      extra='ignore',
                                      populate_by_name=True)


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        try:
            _settings_instance = Settings()
            if not _settings_instance.ADMIN_IDS:
                logging.warning(
                    "CRITICAL: ADMIN_IDS not set or contains no valid integer IDs in .env. "
                    "Admin functionality will be restricted.")

            if not _settings_instance.PANEL_API_URL:
                logging.warning(
                    "CRITICAL: PANEL_API_URL is not set. Panel integration will not work."
                )
            if not _settings_instance.YOOKASSA_SHOP_ID or not _settings_instance.YOOKASSA_SECRET_KEY:
                logging.warning(
                    "CRITICAL: YooKassa credentials (SHOP_ID or SECRET_KEY) are not set. Payments will not work."
                )

        except ValidationError as e:
            logging.critical(
                f"Pydantic validation error while loading settings: {e}")

            raise SystemExit(
                f"CRITICAL SETTINGS ERROR: {e}. Please check your .env file and Settings model."
            )
    return _settings_instance
