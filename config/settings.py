import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, ValidationError, computed_field
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
    YOOKASSA_WEBHOOK_BASE_URL: Optional[str] = None
    YOOKASSA_RETURN_URL: Optional[str] = None

    YOOKASSA_DEFAULT_RECEIPT_EMAIL: Optional[str] = Field(default=None)
    YOOKASSA_VAT_CODE: int = Field(default=1)
    YOOKASSA_PAYMENT_MODE: str = Field(default="full_prepayment")
    YOOKASSA_PAYMENT_SUBJECT: str = Field(default="service")

    TELEGRAM_WEBHOOK_BASE_URL: Optional[str] = None

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

    PANEL_API_URL: Optional[str] = None
    PANEL_API_KEY: Optional[str] = None
    USER_TRAFFIC_LIMIT_GB: Optional[float] = Field(default=0.0)
    USER_TRAFFIC_STRATEGY: str = Field(default="NO_RESET")
    USER_INBOUND_UUIDS: Optional[str] = Field(
        default=None,
        description=
        "Comma-separated UUIDs of inbounds to activate for new panel users")

    TRIAL_ENABLED: bool = Field(default=True)
    TRIAL_DURATION_DAYS: int = Field(default=3)
    TRIAL_TRAFFIC_LIMIT_GB: Optional[float] = Field(default=5.0)

    WEB_SERVER_HOST: str = Field(default="0.0.0.0")
    WEB_SERVER_PORT: int = Field(default=8080)
    LOGS_PAGE_SIZE: int = Field(default=10)

    SUBSCRIPTION_MINI_APP_URL: Optional[str] = Field(default=None)

    START_COMMAND_DESCRIPTION: Optional[str] = Field(default=None)

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
    def parsed_user_inbound_uuids(self) -> Optional[List[str]]:
        if self.USER_INBOUND_UUIDS:
            return [
                uuid.strip()
                for uuid in self.USER_INBOUND_UUIDS.split(',')
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
        if self.YOOKASSA_WEBHOOK_BASE_URL:

            return f"{self.YOOKASSA_WEBHOOK_BASE_URL.rstrip('/')}{self.yookassa_webhook_path}"
        return None

    @computed_field
    @property
    def tribute_webhook_path(self) -> str:
        return "/webhook/tribute"

    @computed_field
    @property
    def tribute_full_webhook_url(self) -> Optional[str]:
        if self.YOOKASSA_WEBHOOK_BASE_URL:
            return f"{self.YOOKASSA_WEBHOOK_BASE_URL.rstrip('/')}{self.tribute_webhook_path}"
        return None

    @computed_field
    @property
    def panel_webhook_path(self) -> str:
        return "/webhook/panel"

    @computed_field
    @property
    def panel_full_webhook_url(self) -> Optional[str]:
        if self.YOOKASSA_WEBHOOK_BASE_URL:
            return f"{self.YOOKASSA_WEBHOOK_BASE_URL.rstrip('/')}{self.panel_webhook_path}"
        return None

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
