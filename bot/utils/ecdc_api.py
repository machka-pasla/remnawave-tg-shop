# ecdc_api.py
# Сервисный слой для бота (aiogram/aiohttp): короткие функции enc_ttu / dec_utt.
# Не тянет ввод из CLI; конфиг задаётся один раз при старте.
# ──────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from typing import Any, Literal, Optional

# === ПУТЬ К ЯДРУ ==============================================================
# Если перенесёте этот файл в другую директорию — поправьте импорт ниже:
from ecdc_core import (  # <- при переносе измените путь на корректный
    Config,
    Prepared,
    prepare,
    encrypt_tid_to_uid,
    decrypt_uid_to_tid,
)

import os


__all__ = [
    "EcdcService",
    "init_from_settings",
    "init_from_env",
    "get_service",
    "enc_ttu",
    "dec_utt",
]


class EcdcService:
    """
    Сервис шифрования/дешифрования Telegram ID ⟷ UID для использования в хендлерах бота.

    Особенности:
      - Делает PBKDF2 ОДИН РАЗ при инициализации (кэширует ключ) → быстрые вызовы.
      - Не делает I/O и не читает переменные окружения сам по себе.
      - Методы синхронные и очень быстрые (HMAC + немного арифметики).

    Пример:
        svc = EcdcService(secret=..., tweak=..., kdf="sha256", iterations=200_000)
        uid = svc.enc_ttu(12345678)       # -> '5377-6196-7198'
        tid = svc.dec_utt('5377-6196-7198')  # -> 12345678
    """

    def __init__(
        self,
        *,
        secret: str,
        tweak: str = "default",
        kdf: Literal["sha256", "sha1"] = "sha256",
        iterations: int = 200_000,
    ) -> None:
        if not secret:
            raise ValueError("ECDC: 'secret' must be non-empty")
        if iterations <= 0:
            raise ValueError("ECDC: 'iterations' must be positive")

        cfg = Config(secret=secret.strip(), tweak=tweak.strip(), kdf=kdf, iterations=iterations)
        self._cfg: Config = cfg
        self._prepared: Prepared = prepare(cfg)

    # --- публичные методы, короткие имена как просили ---

    def enc_ttu(self, tid: int) -> str:
        """
        Encrypt TID To UID: принимает Telegram ID (целое < 10^12), возвращает UID 'XXXX-XXXX-XXXX'.
        Поднимает ValueError при неверном вводе.
        """
        return encrypt_tid_to_uid(tid, self._prepared)

    def dec_utt(self, uid: str) -> int:
        """
        Decrypt UID To TID: принимает строку UID (с дефисами/без), возвращает исходный Telegram ID.
        Поднимает ValueError при неверном вводе.
        """
        return decrypt_uid_to_tid(uid, self._prepared)

    # --- вспомогательные свойства (если нужно логировать/диагностировать) ---

    @property
    def tweak(self) -> str:
        return self._cfg.tweak

    @property
    def kdf(self) -> Literal["sha256", "sha1"]:
        return self._cfg.kdf

    @property
    def iterations(self) -> int:
        return self._cfg.iterations


# ========== ГЛОБАЛЬНЫЙ СЕРВИС (ОПЦИОНАЛЬНО) ==================================
# Удобно, если хотите инициализировать один раз при старте и пользоваться далее
# короткими функциями enc_ttu/dec_utt без прокидывания объекта.

_SERVICE: Optional[EcdcService] = None


def init_from_settings(settings: Any) -> EcdcService:
    """
    Инициализировать глобальный сервис из объекта настроек (pydantic/любой класс),
    ожидаются поля:
        - ECDC_SECRET: str
        - ECDC_TWEAK: str = "default"
        - ECDC_KDF: Literal["sha256","sha1"] = "sha256"
        - ECDC_ITER: int = 200000

    Возвращает созданный EcdcService и сохраняет его как глобальный.
    """
    secret = getattr(settings, "ECDC_SECRET", None)
    if not secret:
        raise ValueError("ECDC: settings.ECDC_SECRET is required")

    tweak = getattr(settings, "ECDC_TWEAK", "default") or "default"
    kdf = getattr(settings, "ECDC_KDF", "sha256") or "sha256"
    iterations = int(getattr(settings, "ECDC_ITER", 200_000) or 200_000)

    global _SERVICE
    _SERVICE = EcdcService(secret=secret, tweak=tweak, kdf=kdf, iterations=iterations)
    return _SERVICE


def init_from_env() -> EcdcService:
    """
    Инициализировать глобальный сервис напрямую из переменных окружения:
        ECDC_SECRET (обязателен)
        ECDC_TWEAK  (по умолчанию 'default')
        ECDC_KDF    (по умолчанию 'sha256')
        ECDC_ITER   (по умолчанию 200000)
    """
    secret = os.getenv("ECDC_SECRET")
    if not secret:
        raise ValueError("ECDC: env ECDC_SECRET is required")

    tweak = os.getenv("ECDC_TWEAK", "default")
    kdf = os.getenv("ECDC_KDF", "sha256")
    iter_str = os.getenv("ECDC_ITER", "200000")

    try:
        iterations = int(iter_str)
    except ValueError as e:
        raise ValueError(f"ECDC: invalid ECDC_ITER value: {iter_str!r}") from e

    global _SERVICE
    _SERVICE = EcdcService(secret=secret, tweak=tweak, kdf=kdf, iterations=iterations)
    return _SERVICE


def get_service() -> EcdcService:
    """
    Получить глобальный сервис. Поднимет RuntimeError, если он не инициализирован.
    """
    if _SERVICE is None:
        raise RuntimeError("ECDC: service is not initialized. Call init_from_settings() or init_from_env() first.")
    return _SERVICE


# ========== КОРОТКИЕ ФУНКЦИИ ДЛЯ ХЕНДЛЕРОВ ===================================

def enc_ttu(tid: int) -> str:
    """
    Удобная функция верхнего уровня: шифрует TID -> UID на основе глобального сервиса.
    Внутри использует кэшированный ключ, поэтому вызов быстрый.
    """
    return get_service().enc_ttu(tid)


def dec_utt(uid: str) -> int:
    """
    Удобная функция верхнего уровня: дешифрует UID -> TID на основе глобального сервиса.
    """
    return get_service().dec_utt(uid)
