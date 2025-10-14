#!/usr/bin/env python3
# Python 3.11.9 — CLI с поддержкой переменных окружения
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import sys
from typing import Literal

RADIX = 1_000_000
ROUNDS = 10

# Имена переменных окружения
ENV_SECRET = "ECDC_SECRET"
ENV_TWEAK = "ECDC_TWEAK"
ENV_KDF = "ECDC_KDF"
ENV_ITER = "ECDC_ITER"


def pbkdf2(password: bytes, salt: bytes, iter: int, dklen: int, kdf: Literal["sha256", "sha1"]) -> bytes:
    return hashlib.pbkdf2_hmac(kdf, password, salt, iter, dklen)


def derive_key(secret: str, tweak: str, kdf: str, iter: int) -> bytes:
    salt = ("fpe-uid-12|" + tweak).encode("utf-8")
    algo = "sha256" if (kdf or "sha256").lower() != "sha1" else "sha1"
    return pbkdf2(secret.encode("utf-8"), salt, iter, 32, algo)


def prf(key: bytes, tweak: bytes, round_byte: int, right: int) -> int:
    s = f"{right:06d}".encode("ascii")
    msg = tweak + bytes([round_byte]) + s
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    val = int.from_bytes(digest[:8], "little", signed=False)
    return int(val % RADIX)


def encrypt12(key: bytes, tweak: bytes, x: int) -> int:
    if not (0 <= x < 1_000_000_000_000):
        raise ValueError("tid must be < 10^12 and non-negative")
    L = x // RADIX
    R = x % RADIX
    for r in range(ROUNDS):
        F = prf(key, tweak, r, R)
        newR = L + F
        if newR >= RADIX:
            newR -= RADIX
        L, R = R, newR
    return L * RADIX + R


def decrypt12(key: bytes, tweak: bytes, y: int) -> int:
    if not (0 <= y < 1_000_000_000_000):
        raise ValueError("uid must be 12 digits (numeric < 10^12)")
    L = y // RADIX
    R = y % RADIX
    for r in range(ROUNDS - 1, -1, -1):
        F = prf(key, tweak, r, L)
        if R >= F:
            newL = R - F
        else:
            newL = R + RADIX - F
        R, L = L, newL
    return L * RADIX + R


def to_uid(n: int) -> str:
    s = f"{n:012d}"
    return f"{s[:4]}-{s[4:8]}-{s[8:]}"


def from_uid(s: str) -> int:
    digits = re.sub(r"\D", "", s)
    if len(digits) != 12:
        raise ValueError("UID must have exactly 12 digits")
    n = 0
    for ch in digits:
        n = n * 10 + (ord(ch) - 48)
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fpe12",
        add_help=True,
        description="Format-preserving encryption for 12-digit IDs (Feistel + HMAC-SHA256). "
                    f"Reads config from env: {ENV_SECRET}, {ENV_TWEAK}, {ENV_KDF}, {ENV_ITER}.",
    )
    sub = p.add_subparsers(dest="cmd")

    enc = sub.add_parser("enc", help="encrypt TID -> UID")
    enc.add_argument("--tid", type=int, required=True)
    # Конфиг-флаги стали необязательными → по умолчанию None, чтобы брать из env
    enc.add_argument("--secret", type=str, default=None, help=f"or set {ENV_SECRET}")
    enc.add_argument("--tweak", type=str, default=None, help=f"or set {ENV_TWEAK} (default 'default')")
    enc.add_argument("--kdf", type=str, default=None, choices=["sha256", "sha1"], help=f"or set {ENV_KDF} (default sha256)")
    enc.add_argument("--iter", type=int, default=None, help=f"or set {ENV_ITER} (default 200000)")
    enc.set_defaults(func=cmd_enc)

    dec = sub.add_parser("dec", help="decrypt UID -> TID")
    dec.add_argument("--uid", type=str, required=True)
    dec.add_argument("--secret", type=str, default=None, help=f"or set {ENV_SECRET}")
    dec.add_argument("--tweak", type=str, default=None, help=f"or set {ENV_TWEAK} (default 'default')")
    dec.add_argument("--kdf", type=str, default=None, choices=["sha256", "sha1"], help=f"or set {ENV_KDF} (default sha256)")
    dec.add_argument("--iter", type=int, default=None, help=f"or set {ENV_ITER} (default 200000)")
    dec.set_defaults(func=cmd_dec)

    st = sub.add_parser("selftest", help="run reference vectors and roundtrip check")
    st.set_defaults(func=cmd_selftest)

    return p


def _resolve_conf(args: argparse.Namespace):
    # Приоритет: флаг CLI → ENV → дефолт
    secret = args.secret if args.secret is not None else os.getenv(ENV_SECRET, None)
    tweak = args.tweak if args.tweak is not None else os.getenv(ENV_TWEAK, "default")
    kdf = args.kdf if args.kdf is not None else os.getenv(ENV_KDF, "sha256")
    iter_str = str(args.iter) if args.iter is not None else os.getenv(ENV_ITER, "200000")

    try:
        iterations = int(iter_str)
    except ValueError as e:
        raise ValueError(f"invalid {ENV_ITER} value: {iter_str!r}") from e

    if not secret:
        raise ValueError(f"--secret not provided and {ENV_SECRET} is not set")

    return secret, tweak.strip(), kdf.strip().lower(), iterations


def cmd_enc(args: argparse.Namespace) -> int:
    secret, tweak, kdf, iterations = _resolve_conf(args)
    key = derive_key(secret, tweak, kdf, iterations)
    y = encrypt12(key, tweak.encode("utf-8"), int(args.tid))
    sys.stdout.write(to_uid(y) + "\n")
    sys.stdout.flush()
    return 0


def cmd_dec(args: argparse.Namespace) -> int:
    secret, tweak, kdf, iterations = _resolve_conf(args)
    y = from_uid(args.uid)
    key = derive_key(secret, tweak, kdf, iterations)
    x = decrypt12(key, tweak.encode("utf-8"), y)
    sys.stdout.write(str(x) + "\n")
    sys.stdout.flush()
    return 0


def cmd_selftest(_: argparse.Namespace) -> int:
    cases = [
        ("qwerty123", "123", 12_345_678, "5377-6196-7198"),
        ("qwerty123", "123", 123_456_789, "8678-9607-3662"),
        ("correct horse battery staple", "prod", 42, "3467-7244-0811"),
    ]
    ok_all = True
    for secret, tweak, tid, want in cases:
        key = derive_key(secret, tweak, "sha256", 200_000)
        y = encrypt12(key, tweak.encode("utf-8"), tid)
        back = decrypt12(key, tweak.encode("utf-8"), y)
        got = to_uid(y)
        ok = got == want and back == tid
        ok_all &= ok
        sys.stdout.write(
            f'secret="{secret}" tweak="{tweak}" tid={tid} -> uid={got} -> back={back}  [{"OK" if ok else "FAIL"}]\n'
        )
    sys.stdout.flush()
    return 0 if ok_all else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help(sys.stdout)
        return 0
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help(sys.stdout)
        return 0
    try:
        return func(args)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())