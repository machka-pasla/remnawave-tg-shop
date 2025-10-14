# ecdc_core.py
# Ядро формат-сохраняющего шифрования для 12-значных чисел (Feistel + HMAC-SHA256).
# Без CLI, без чтения env. Только чистые функции и тонкие утилиты.
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Literal

# Константы схемы
RADIX = 1_000_000  # 10^6 (6 цифр)
ROUNDS = 10        # число раундов Фейстеля


# ---- Низкоуровневые примитивы ------------------------------------------------

def pbkdf2(password: bytes, salt: bytes, iter: int, dklen: int,
           kdf: Literal["sha256", "sha1"]) -> bytes:
    """PBKDF2 (stdlib, C-реализация)."""
    return hashlib.pbkdf2_hmac(kdf, password, salt, iter, dklen)


def derive_key(secret: str, tweak: str, kdf: Literal["sha256", "sha1"] = "sha256",
               iterations: int = 200_000) -> bytes:
    """
    Производит 32-байтный ключ из секретной фразы и tweak.
    Важно: tweak участвует в соли для изоляции доменов.
    """
    salt = ("fpe-uid-12|" + tweak).encode("utf-8")  # строка домейна; можно зафиксировать версию здесь
    algo = "sha256" if kdf.lower() != "sha1" else "sha1"
    return pbkdf2(secret.encode("utf-8"), salt, iterations, 32, algo)


def _prf(key: bytes, tweak: bytes, round_byte: int, right: int) -> int:
    """
    Раундовая функция: HMAC-SHA256(key, tweak || round || ascii(right_6d)) mod 10^6.
    """
    s = f"{right:06d}".encode("ascii")
    msg = tweak + bytes([round_byte]) + s
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    val = int.from_bytes(digest[:8], "little", signed=False)
    return int(val % RADIX)


def encrypt12(key: bytes, tweak: bytes, x: int) -> int:
    """
    Шифрует 12-значное неотрицательное число x (TID) → 12-значное число (UID).
    Выбрасывает ValueError при выходе за домен.
    """
    if not (0 <= x < 1_000_000_000_000):
        raise ValueError("tid must be < 10^12 and non-negative")
    L = x // RADIX
    R = x % RADIX
    for r in range(ROUNDS):
        F = _prf(key, tweak, r, R)
        newR = L + F
        if newR >= RADIX:
            newR -= RADIX
        L, R = R, newR
    return L * RADIX + R


def decrypt12(key: bytes, tweak: bytes, y: int) -> int:
    """
    Дешифрует 12-значное число y (UID) → исходный TID.
    Выбрасывает ValueError при выходе за домен.
    """
    if not (0 <= y < 1_000_000_000_000):
        raise ValueError("uid must be 12 digits (numeric < 10^12)")
    L = y // RADIX
    R = y % RADIX
    for r in range(ROUNDS - 1, -1, -1):
        F = _prf(key, tweak, r, L)
        if R >= F:
            newL = R - F
        else:
            newL = R + RADIX - F
        R, L = L, newL
    return L * RADIX + R


# ---- Утилиты форматирования ---------------------------------------------------

def to_uid(n: int) -> str:
    """Печатает 12-значное число как XXXX-XXXX-XXXX."""
    s = f"{n:012d}"
    return f"{s[:4]}-{s[4:8]}-{s[8:]}"


def from_uid(s: str) -> int:
    """
    Парсит UID из строки с произвольными разделителями (берёт только цифры).
    Требует ровно 12 цифр.
    """
    digits = re.sub(r"\D", "", s)
    if len(digits) != 12:
        raise ValueError("UID must have exactly 12 digits")
    n = 0
    for ch in digits:
        n = n * 10 + (ord(ch) - 48)
    return n


# ---- Подготовка (кэширование ключа) ------------------------------------------

@dataclass(frozen=True)
class Config:
    """
    Конфиг для подготовки ключа. Хранит исходные параметры.
    """
    secret: str
    tweak: str = "default"
    kdf: Literal["sha256", "sha1"] = "sha256"
    iterations: int = 200_000


@dataclass(frozen=True)
class Prepared:
    """
    Подготовленный материал для быстрых вызовов: кэшированный ключ и tweak в байтах.
    """
    key: bytes
    tweak_bytes: bytes


def prepare(cfg: Config) -> Prepared:
    """
    Создаёт Prepared: делает PBKDF2 один раз и фиксирует tweak.
    Используйте это в вашем приложении/боте при старте процесса.
    """
    key = derive_key(cfg.secret, cfg.tweak, cfg.kdf, cfg.iterations)
    return Prepared(key=key, tweak_bytes=cfg.tweak.strip().encode("utf-8"))


# ---- Удобные обёртки над Prepared (без I/O) ----------------------------------

def encrypt_tid_to_uid(tid: int, prepared: Prepared) -> str:
    """
    Удобная обёртка: TID (int) → UID (форматированная строка XXXX-XXXX-XXXX).
    Исключения пробрасываются выше (ValueError при неверном вводе).
    """
    y = encrypt12(prepared.key, prepared.tweak_bytes, tid)
    return to_uid(y)


def decrypt_uid_to_tid(uid: str, prepared: Prepared) -> int:
    """
    Удобная обёртка: UID (строка) → исходный TID (int).
    Исключения пробрасываются выше (ValueError при неверном вводе).
    """
    y = from_uid(uid)
    return decrypt12(prepared.key, prepared.tweak_bytes, y)
