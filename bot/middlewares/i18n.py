import logging
import json
import os
import time
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import User, Update
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import user_dal
from config.settings import Settings


# ============================================================
#                    JSON-BASED I18N ENGINE
# ============================================================

class JsonI18n:
    """Fast, safe, cached JSON i18n loader with debounce hot-reload."""

    RELOAD_DEBOUNCE_SEC = 2  # how often to check .json files

    def __init__(self, path: str, default: str = "en", domain: str = "bot"):
        self.path = path
        self.default_lang = default
        self.domain = domain

        # loaded JSON locales
        self.locales_data: Dict[str, Dict[str, str]] = {}

        # file modified times
        self.file_mtimes: Dict[str, float] = {}

        # debounce timestamp
        self._last_reload_check = 0.0

        self._load_all_locales()
        logging.info(f"[i18n] Loaded languages: {list(self.locales_data.keys())}")

    # -------------------------------

    def _load_all_locales(self):
        """Load or reload all .json locale files."""
        if not os.path.isdir(self.path):
            logging.error(f"[i18n] Locales dir not found: {self.path}")
            return

        for file in os.listdir(self.path):
            if not file.endswith(".json"):
                continue

            lang = file.split(".")[0]
            full_path = os.path.join(self.path, file)

            # check file modification
            try:
                mtime = os.path.getmtime(full_path)
                if self.file_mtimes.get(full_path) == mtime:
                    continue  # no change

                self.file_mtimes[full_path] = mtime

                with open(full_path, "r", encoding="utf-8") as f:
                    self.locales_data[lang] = json.load(f)

                logging.info(f"[i18n] Reloaded: {lang}")

            except Exception as e:
                logging.error(f"[i18n] Failed to load locale {file}: {e}", exc_info=True)

    # -------------------------------

    def _check_and_reload_debounced(self):
        """Check .json changes not more often than RELOAD_DEBOUNCE_SEC."""
        now = time.time()
        if now - self._last_reload_check < self.RELOAD_DEBOUNCE_SEC:
            return  # do nothing

        self._last_reload_check = now
        self._load_all_locales()

    # -------------------------------

    def _safe_format(self, text: str, kwargs: Dict[str, Any]) -> str:
        """Safe text.format without exceptions."""
        try:
            return text.format(**kwargs)
        except KeyError as missing:
            logging.warning(f"[i18n] Missing placeholder '{missing}' in '{text}'")
            return text
        except Exception as e:
            logging.error(f"[i18n] Formatting error for '{text}': {e}", exc_info=True)
            return text

    # -------------------------------

    def gettext(self, lang_code: Optional[str], key: str, **kwargs) -> str:
        """Return translated text with fallback chain and safe formatting."""

        self._check_and_reload_debounced()

        # Choose effective language
        lang_code = (lang_code or "").lower()

        candidates = []

        # user lang
        if lang_code and lang_code in self.locales_data:
            candidates.append(lang_code)

        # try prefix (ru-RU → ru)
        if "-" in lang_code:
            prefix = lang_code.split("-")[0]
            if prefix in self.locales_data:
                candidates.append(prefix)

        # default lang
        if self.default_lang in self.locales_data:
            candidates.append(self.default_lang)

        # english fallback
        if "en" in self.locales_data:
            candidates.append("en")

        # flatten search
        for lang in candidates:
            text = self.locales_data.get(lang, {}).get(key)
            if text is not None:
                return self._safe_format(text, kwargs) if kwargs else text

        # fallback → key as text
        logging.warning(f"[i18n] Missing key='{key}' in languages {candidates}")
        return key

# ============================================================
#                      SINGLETON FACTORY
# ============================================================

_i18n_singleton: Optional[JsonI18n] = None

def get_i18n_instance(path="locales", default="en", domain="bot") -> JsonI18n:
    global _i18n_singleton

    if _i18n_singleton is None:
        _i18n_singleton = JsonI18n(path=path, default=default, domain=domain)

    return _i18n_singleton


# ============================================================
#                         MIDDLEWARE
# ============================================================

class I18nMiddleware(BaseMiddleware):
    """Aiogram middleware: injects i18n_instance + user language."""

    def __init__(self, i18n: JsonI18n, settings: Settings):
        super().__init__()
        self.i18n = i18n
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:

        session: AsyncSession = data["session"]
        tg_user: Optional[User] = data.get("event_from_user")

        lang = self.i18n.default_lang

        if tg_user:
            try:
                db_user = await user_dal.get_user_by_id(session, tg_user.id)

                if db_user and db_user.language_code in self.i18n.locales_data:
                    lang = db_user.language_code
                else:
                    # Detect via Telegram language
                    if tg_user.language_code:
                        raw = tg_user.language_code.lower()
                        prefix = raw.split("-")[0]

                        if raw in self.i18n.locales_data:
                            lang = raw
                        elif prefix in self.i18n.locales_data:
                            lang = prefix

            except Exception as e:
                logging.error(
                    f"[i18n] Error loading language for user {tg_user.id}: {e}",
                    exc_info=True
                )

        data["i18n_data"] = {
            "i18n_instance": self.i18n,
            "current_language": lang,
        }

        return await handler(event, data)