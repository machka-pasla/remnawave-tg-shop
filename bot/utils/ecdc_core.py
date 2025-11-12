# ecdc_core.py
# Ядро формат-сохраняющего шифрования для 12- и 16-значных чисел (Feistel + HMAC-SHA256).
# Без CLI, без чтения env. Только чистые функции и тонкие утилиты.
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Literal

# Константы схемы
RADIX6 = 1_000_000      # 10^6  (6 цифр, половина от 12)
RADIX8 = 100_000_000    # 10^8  (8 цифр, половина от 16)
ROUNDS = 10             # число раундов Фейстеля


# ---- Низкоуровневые примитивы ------------------------------------------------

def pbkdf2(password: bytes, salt: bytes, iter: int, dklen: int,
           kdf: Literal["sha256", "sha1"]) -> bytes:
    """PBKDF2 (stdlib, C-реализация)."""
    return hashlib.pbkdf2_hmac(kdf, password, salt, iter, dklen)


def derive_key(secret: str, tweak: str, kdf: Literal["sha256", "sha1"] = "sha256",
               iterations: int = 200_000) -> bytes:
    """
    Производит 32-байтный ключ из секретной фразы и tweak.
    Важно: tweak участвует в соли. Совместимо с исходной реализацией (Go/Python-CLI).
    """
    # ВАЖНО: не менять префикс соли, иначе UID перестанут совпадать со старыми:
    salt = ("fpe-uid-12|" + tweak).encode("utf-8")
    algo = "sha256" if kdf.lower() != "sha1" else "sha1"
    return pbkdf2(secret.encode("utf-8"), salt, iterations, 32, algo)


def _prf_generic(key: bytes, tweak: bytes, round_byte: int, right: int, width: int, modulus: int) -> int:
    """
    Общая раундовая функция: HMAC-SHA256(key, tweak || round || ascii(right_widthd)) mod 10^width.
    width = 6 для 12-значного домена (6+6), width = 8 для 16-значного домена (8+8).
    """
    s = f"{right:0{width}d}".encode("ascii")
    msg = tweak + bytes([round_byte]) + s
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    val = int.from_bytes(digest[:8], "little", signed=False)
    return int(val % modulus)


# ---- 12-значный домен (пользователи) -----------------------------------------

def encrypt12(key: bytes, tweak: bytes, x: int) -> int:
    """
    Шифрует 12-значное неотрицательное число x (TID) → 12-значное число (UID).
    Выбрасывает ValueError при выходе за домен.
    """
    if not (0 <= x < 1_000_000_000_000):
        raise ValueError("tid must be < 10^12 and non-negative")
    L = x // RADIX6
    R = x % RADIX6
    for r in range(ROUNDS):
        F = _prf_generic(key, tweak, r, R, width=6, modulus=RADIX6)
        newR = L + F
        if newR >= RADIX6:
            newR -= RADIX6
        L, R = R, newR
    return L * RADIX6 + R


def decrypt12(key: bytes, tweak: bytes, y: int) -> int:
    """
    Дешифрует 12-значное число y (UID) → исходный TID.
    Выбрасывает ValueError при выходе за домен.
    """
    if not (0 <= y < 1_000_000_000_000):
        raise ValueError("uid must be 12 digits (numeric < 10^12)")
    L = y // RADIX6
    R = y % RADIX6
    for r in range(ROUNDS - 1, -1, -1):
        F = _prf_generic(key, tweak, r, L, width=6, modulus=RADIX6)
        if R >= F:
            newL = R - F
        else:
            newL = R + RADIX6 - F
        R, L = L, newL
    return L * RADIX6 + R


# ---- 16-значный домен (группы/чаты) ------------------------------------------

def encrypt16(key: bytes, tweak: bytes, x: int) -> int:
    """
    Шифрует 16-значное неотрицательное число x → 16-значное число.
    Ожидается 0 <= x < 10^16 (в т.ч. abs(gid) после нормализации).
    """
    if not (0 <= x < 10_000_000_000_000_000):
        raise ValueError("value must be < 10^16 and non-negative")
    L = x // RADIX8
    R = x % RADIX8
    for r in range(ROUNDS):
        F = _prf_generic(key, tweak, r, R, width=8, modulus=RADIX8)
        newR = L + F
        if newR >= RADIX8:
            newR -= RADIX8
        L, R = R, newR
    return L * RADIX8 + R


def decrypt16(key: bytes, tweak: bytes, y: int) -> int:
    """
    Дешифрует 16-значное число y → исходное 16-значное число (без знака).
    """
    if not (0 <= y < 10_000_000_000_000_000):
        raise ValueError("value must be 16 digits (numeric < 10^16)")
    L = y // RADIX8
    R = y % RADIX8
    for r in range(ROUNDS - 1, -1, -1):
        F = _prf_generic(key, tweak, r, L, width=8, modulus=RADIX8)
        if R >= F:
            newL = R - F
        else:
            newL = R + RADIX8 - F
        R, L = L, newL
    return L * RADIX8 + R


# ---- Утилиты форматирования (12) ---------------------------------------------

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


# ---- Утилиты форматирования (16 с минусом для групп) -------------------------

def to_ugid(n16: int) -> str:
    """
    Печатает 16-значное число как строку формата '-XXXX-XXXX-XXXX-XXXX'.
    Минус — часть формата для групп/чатов.
    """
    s = f"{n16:016d}"
    return f"-{s[:4]}-{s[4:8]}-{s[8:12]}-{s[12:]}"


def from_ugid(s: str) -> int:
    """
    Парсит групповой UID (UGID) вида '-XXXX-XXXX-XXXX-XXXX' или любую строку,
    где содержатся ровно 16 цифр. Знак игнорируется на парсинге (мы ожидаем минус на выводе).
    """
    digits = re.sub(r"\D", "", s)
    if len(digits) != 16:
        raise ValueError("UGID must have exactly 16 digits")
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


# ---- Группы: удобные обёртки (tgid ↔ ugid) -----------------------------------

def encg(tgid: int, prepared: Prepared) -> str:
    """
    Encrypt GroupID to UGID: принимает отрицательный Telegram group/chat ID (например, -1001234567890),
    шифрует abs(tgid) как 16-значное число и возвращает строку формата '-XXXX-XXXX-XXXX-XXXX'.
    """
    if tgid >= 0:
        raise ValueError("tgid must be negative (Telegram group/chat IDs are negative)")
    n = -tgid  # abs
    if not (0 <= n < 10_000_000_000_000_000):
        raise ValueError("abs(tgid) must be < 10^16")
    # паддинг до 16 цифр обеспечивается форматтером внутри to_ugid (encrypt16 работает на int-домене)
    y16 = encrypt16(prepared.key, prepared.tweak_bytes, n)
    return to_ugid(y16)


def decg(ugid: str, prepared: Prepared) -> int:
    """
    Decrypt UGID to GroupID: принимает строку '-XXXX-XXXX-XXXX-XXXX' (или любую с 16 цифрами),
    дешифрует её и возвращает отрицательный Telegram group/chat ID.
    """
    y16 = from_ugid(ugid)
    n = decrypt16(prepared.key, prepared.tweak_bytes, y16)
    # исходный group/chat ID — отрицательный
    return -n
