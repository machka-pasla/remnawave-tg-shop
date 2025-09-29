import logging
import json
import os
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import User, Update
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import user_dal
from config.settings import Settings


class JsonI18n:

    def __init__(self, path: str, default: str = "en", domain: str = "bot"):
        self.domain = domain
        self.path = path
        self.default_lang = default
        self.locales_data: Dict[str, Dict[str, str]] = {}
        self._load_locales()
        logging.info(
            f"JsonI18n initialized. Loaded languages: {list(self.locales_data.keys())}. Default: {self.default_lang}"
        )

    def _load_locales(self):
        if not os.path.isdir(self.path):
            logging.error(
                f"Locales path not found or not a directory: {self.path}")
            return
        for item in os.listdir(self.path):
            if item.endswith(".json"):
                lang_code = item.split(".")[0]
                file_path = os.path.join(self.path, item)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        self.locales_data[lang_code] = json.load(f)
                except json.JSONDecodeError as e_json_load:
                    logging.error(
                        f"Error loading locale {lang_code} from {file_path} (JSON Decode Error): {e_json_load}"
                    )
                except Exception as e_load:
                    logging.error(
                        f"Error loading locale {lang_code} from {file_path}: {e_load}",
                        exc_info=True)

    def gettext(self, lang_code: Optional[str], key: str, **kwargs) -> str:
        # Determine effective language with robust fallback
        if lang_code and lang_code in self.locales_data:
            effective_lang_code = lang_code
        elif self.default_lang in self.locales_data:
            effective_lang_code = self.default_lang
        elif 'en' in self.locales_data:
            effective_lang_code = 'en'
        else:
            effective_lang_code = lang_code or self.default_lang

        lang_data = self.locales_data.get(effective_lang_code)
        if lang_data is None:
            # Try explicit fallback to English if available
            fallback_data = self.locales_data.get('en')
            if fallback_data is not None:
                text = fallback_data.get(key)
                if text is not None:
                    try:
                        return text.format(**kwargs) if kwargs else text
                    except Exception:
                        return text
            logging.warning(
                f"No language data for '{effective_lang_code}' (default '{self.default_lang}' also missing). Key '{key}' will be returned as is."
            )
            return key.format(**kwargs) if kwargs else key

        text = lang_data.get(key)
        if text is None:
            if effective_lang_code != self.default_lang:
                default_lang_data = self.locales_data.get(
                    self.default_lang, {})
                text = default_lang_data.get(key)

            if text is None:
                logging.warning(
                    f"Translation key '{key}' not found for lang '{effective_lang_code}' or default '{self.default_lang}'. Returning key."
                )
                return key.format(**kwargs) if kwargs else key
        try:
            return text.format(**kwargs) if kwargs else text
        except KeyError as e_format:
            logging.warning(
                f"Missing format key '{e_format}' for i18n key '{key}' (lang: {effective_lang_code}). Original text: '{text}'"
            )
            return text
        except Exception as e_general_format:
            logging.error(
                f"General error formatting i18n key '{key}' (lang: {effective_lang_code}): {e_general_format}. Original text: '{text}'",
                exc_info=True)
            return text


_i18n_instance_singleton: Optional[JsonI18n] = None


def get_i18n_instance(path: str = "locales",
                      default: str = "en",
                      domain: str = "bot") -> JsonI18n:
    global _i18n_instance_singleton
    if _i18n_instance_singleton is None:

        if not os.path.exists(path) or not os.path.isdir(path):
            logging.error(
                f"CRITICAL: Locales directory '{path}' not found. i18n will not work correctly."
            )

            _i18n_instance_singleton = JsonI18n(path=path,
                                                default=default,
                                                domain=domain)
        else:
            _i18n_instance_singleton = JsonI18n(path=path,
                                                default=default,
                                                domain=domain)
    return _i18n_instance_singleton


class I18nMiddleware(BaseMiddleware):

    def __init__(self, i18n: JsonI18n, settings: Settings):
        super().__init__()
        self.i18n = i18n
        self.settings = settings

    async def __call__(self, handler: Callable[[Update, Dict[str, Any]],
                                               Awaitable[Any]], event: Update,
                       data: Dict[str, Any]) -> Any:
        session: AsyncSession = data["session"]
        event_user: Optional[User] = data.get("event_from_user")

        current_language = self.i18n.default_lang

        if event_user:
            try:
                user_db_model = await user_dal.get_user_by_id(
                    session, event_user.id)
                if user_db_model and user_db_model.language_code and user_db_model.language_code in self.i18n.locales_data:
                    current_language = user_db_model.language_code
                elif event_user.language_code:
                    lang_prefix = event_user.language_code.split(
                        '-')[0].lower()
                    if lang_prefix in self.i18n.locales_data:
                        current_language = lang_prefix
                    elif event_user.language_code.lower(
                    ) in self.i18n.locales_data:
                        current_language = event_user.language_code.lower()
            except Exception as e_db_lang:
                logging.error(
                    f"I18nMiddleware: Error fetching user lang from DB for {event_user.id}: {e_db_lang}. Falling back.",
                    exc_info=True)
                if event_user.language_code:
                    lang_prefix = event_user.language_code.split(
                        '-')[0].lower()
                    if lang_prefix in self.i18n.locales_data:
                        current_language = lang_prefix
                    elif event_user.language_code.lower(
                    ) in self.i18n.locales_data:
                        current_language = event_user.language_code.lower()

        data["i18n_data"] = {
            "i18n_instance": self.i18n,
            "current_language": current_language
        }
        return await handler(event, data)
