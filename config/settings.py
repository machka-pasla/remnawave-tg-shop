import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, ValidationError
from typing import Optional, List, Dict, Any


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS_STR: str = Field(
        default="",
        alias="ADMIN_IDS",
        description="Comma-separated list of admin Telegram User IDs")

    DB_NAME: str = Field(default="bot_database.sqlite3")
    DEFAULT_LANGUAGE: str = Field(default="ru")
    DEFAULT_CURRENCY_SYMBOL: str = Field(default="RUB")

    SUPPORT_LINK: Optional[str] = Field(
        default=None,
        description="Link to support contact (e.g., t.me/your_support_contact)"
    )
    SERVER_STATUS_URL: Optional[str] = Field(
        default=None,
        description="Link to server status page (e.g., Uptime Kuma)")

    YOOKASSA_SHOP_ID: Optional[str] = None
    YOOKASSA_SECRET_KEY: Optional[str] = None
    YOOKASSA_WEBHOOK_BASE_URL: Optional[str] = None
    YOOKASSA_RETURN_URL: Optional[str] = None

    YOOKASSA_DEFAULT_RECEIPT_EMAIL: Optional[str] = Field(
        default=None,
        description="Default email for YooKassa receipts (REQUIRED for 54-FZ)")
    YOOKASSA_VAT_CODE: int = Field(
        default=1,
        description=
        "YooKassa VAT code (e.g., 1=No VAT - check YooKassa docs!)"
    )
    YOOKASSA_PAYMENT_MODE: str = Field(
        default="full_prepayment",
        description=
        "YooKassa payment mode (e.g., full_prepayment, full_payment)")
    YOOKASSA_PAYMENT_SUBJECT: str = Field(
        default="service",
        description="YooKassa payment subject (e.g., service, commodity)")

    TELEGRAM_WEBHOOK_BASE_URL: Optional[str] = None

    PRICE_1_MONTH: Optional[int] = None
    PRICE_3_MONTHS: Optional[int] = None
    PRICE_6_MONTHS: Optional[int] = None
    PRICE_12_MONTHS: Optional[int] = None

    SUBSCRIPTION_EXPIRATION_NOTIFICATION_DAYS: int = Field(default=7)
    SUBSCRIPTION_NOTIFICATION_HOUR_UTC: int = Field(default=9)
    SUBSCRIPTION_NOTIFICATION_MINUTE_UTC: int = Field(default=0)

    REFERRAL_BONUS_DAYS_1_MONTH: Optional[int] = 3
    REFERRAL_BONUS_DAYS_3_MONTHS: Optional[int] = 7
    REFERRAL_BONUS_DAYS_6_MONTHS: Optional[int] = 15
    REFERRAL_BONUS_DAYS_12_MONTHS: Optional[int] = 30
    REFEREE_BONUS_DAYS_1_MONTH: Optional[int] = 1
    REFEREE_BONUS_DAYS_3_MONTHS: Optional[int] = 3
    REFEREE_BONUS_DAYS_6_MONTHS: Optional[int] = 7
    REFEREE_BONUS_DAYS_12_MONTHS: Optional[int] = 15

    PANEL_API_URL: Optional[str] = None
    PANEL_API_KEY: Optional[str] = None
    PANEL_USER_DEFAULT_EXPIRE_DAYS: int = Field(default=1)
    PANEL_USER_DEFAULT_TRAFFIC_BYTES: int = Field(default=0)
    PANEL_USER_DEFAULT_TRAFFIC_STRATEGY: str = Field(default="NO_RESET")
    PANEL_USER_DEFAULT_INBOUND_UUIDS: Optional[str] = Field(default=None)

    TRIAL_ENABLED: bool = Field(default=True)
    TRIAL_DURATION_DAYS: int = Field(default=3)
    TRIAL_TRAFFIC_LIMIT_GB: Optional[float] = Field(default=5.0)

    WEB_SERVER_HOST: str = Field(default="0.0.0.0")
    WEB_SERVER_PORT: int = Field(default=8080)
    LOGS_PAGE_SIZE: int = Field(default=10)

    _admin_ids_list: Optional[List[int]] = None

    @property
    def ADMIN_IDS(self) -> List[int]:
        if self._admin_ids_list is None:
            if self.ADMIN_IDS_STR:
                try:
                    self._admin_ids_list = [
                        int(admin_id.strip())
                        for admin_id in self.ADMIN_IDS_STR.split(',')
                        if admin_id.strip().isdigit()
                    ]
                    if not self._admin_ids_list and self.ADMIN_IDS_STR:
                        logging.error(
                            f"ADMIN_IDS_STR ('{self.ADMIN_IDS_STR}') contains non-integer values or is malformed. No admin IDs loaded from string."
                        )
                        self._admin_ids_list = []
                except ValueError:
                    logging.error(
                        f"Invalid ADMIN_IDS_STR format: '{self.ADMIN_IDS_STR}'. Expected comma-separated integers."
                    )
                    self._admin_ids_list = []
            else:
                self._admin_ids_list = []
        return self._admin_ids_list

    @property
    def PRIMARY_ADMIN_ID(self) -> Optional[int]:
        admin_ids_list = self.ADMIN_IDS
        if admin_ids_list:
            return admin_ids_list[0]
        return None

    @property
    def trial_traffic_limit_bytes(self) -> int:
        if self.TRIAL_TRAFFIC_LIMIT_GB is None or self.TRIAL_TRAFFIC_LIMIT_GB <= 0:
            return 0
        return int(self.TRIAL_TRAFFIC_LIMIT_GB * (1024**3))

    @property
    def parsed_default_panel_user_inbound_uuids(self) -> Optional[List[str]]:
        if self.PANEL_USER_DEFAULT_INBOUND_UUIDS:
            return [
                uuid.strip()
                for uuid in self.PANEL_USER_DEFAULT_INBOUND_UUIDS.split(',')
                if uuid.strip()
            ]
        return None

    @property
    def yookassa_webhook_path(self) -> str:
        return "/webhook/yookassa"

    @property
    def yookassa_full_webhook_url(self) -> Optional[str]:
        if self.YOOKASSA_WEBHOOK_BASE_URL:
            return f"{self.YOOKASSA_WEBHOOK_BASE_URL.rstrip('/')}{self.yookassa_webhook_path}"
        return None

    @property
    def subscription_options(self) -> Dict[int, int]:
        options: Dict[int, int] = {}
        if self.PRICE_1_MONTH is not None: options[1] = self.PRICE_1_MONTH
        if self.PRICE_3_MONTHS is not None: options[3] = self.PRICE_3_MONTHS
        if self.PRICE_6_MONTHS is not None: options[6] = self.PRICE_6_MONTHS
        if self.PRICE_12_MONTHS is not None: options[12] = self.PRICE_12_MONTHS
        return options

    @property
    def referral_bonus_inviter(self) -> Dict[int, int]:
        bonuses: Dict[int, int] = {}
        if self.REFERRAL_BONUS_DAYS_1_MONTH is not None:
            bonuses[1] = self.REFERRAL_BONUS_DAYS_1_MONTH
        if self.REFERRAL_BONUS_DAYS_3_MONTHS is not None:
            bonuses[3] = self.REFERRAL_BONUS_DAYS_3_MONTHS
        if self.REFERRAL_BONUS_DAYS_6_MONTHS is not None:
            bonuses[6] = self.REFERRAL_BONUS_DAYS_6_MONTHS
        if self.REFERRAL_BONUS_DAYS_12_MONTHS is not None:
            bonuses[12] = self.REFERRAL_BONUS_DAYS_12_MONTHS
        return bonuses

    @property
    def referral_bonus_referee(self) -> Dict[int, int]:
        bonuses: Dict[int, int] = {}
        if self.REFEREE_BONUS_DAYS_1_MONTH is not None:
            bonuses[1] = self.REFEREE_BONUS_DAYS_1_MONTH
        if self.REFEREE_BONUS_DAYS_3_MONTHS is not None:
            bonuses[3] = self.REFEREE_BONUS_DAYS_3_MONTHS
        if self.REFEREE_BONUS_DAYS_6_MONTHS is not None:
            bonuses[6] = self.REFEREE_BONUS_DAYS_6_MONTHS
        if self.REFEREE_BONUS_DAYS_12_MONTHS is not None:
            bonuses[12] = self.REFEREE_BONUS_DAYS_12_MONTHS
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
                    "CRITICAL: ADMIN_IDS not set or contains no valid integer IDs in .env. Admin functionality will be restricted."
                )
        except ValidationError as e:
            logging.critical(
                f"Pydantic validation error while loading settings: {e}")
            raise SystemExit(f"CRITICAL SETTINGS ERROR: {e}")
    return _settings_instance
