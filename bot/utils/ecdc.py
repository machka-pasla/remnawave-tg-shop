#!/usr/bin/env python3
# fpe12.py  — Python 3.11.9 port of the Go CLI

from __future__ import annotations

import argparse
import hashlib
import hmac
import re
import sys
from typing import Literal

RADIX = 1_000_000  # 10^6 (6 digits)
ROUNDS = 10


def pbkdf2(password: bytes, salt: bytes, iter: int, dklen: int, kdf: Literal["sha256", "sha1"]) -> bytes:
    # stdlib fast C-implementation
    return hashlib.pbkdf2_hmac(kdf, password, salt, iter, dklen)


def derive_key(secret: str, tweak: str, kdf: str, iter: int) -> bytes:
    salt = ("fpe-uid-12|" + tweak).encode("utf-8")
    algo = "sha256" if kdf.lower() != "sha1" else "sha1"
    return pbkdf2(secret.encode("utf-8"), salt, iter, 32, algo)  # 32 bytes like Go code


def prf(key: bytes, tweak: bytes, round_byte: int, right: int) -> int:
    # msg = tweak || round(1b) || ascii(right_6d)
    s = f"{right:06d}".encode("ascii")
    msg = tweak + bytes([round_byte]) + s
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    # first 8 bytes as little-endian uint64 -> mod 10^6
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
    # avoid int(str) pitfalls with leading zeros? Go code reconstructs manually; emulate that:
    n = 0
    for ch in digits:
        n = n * 10 + (ord(ch) - 48)
    return n


def cmd_enc(args: argparse.Namespace) -> int:
    if args.secret is None or args.secret == "":
        print("Error: --secret is required", file=sys.stderr)
        return 1
    if args.tid is None:
        print("Error: --tid is required", file=sys.stderr)
        return 1
    key = derive_key(args.secret, args.tweak.strip(), args.kdf, args.iter)
    y = encrypt12(key, args.tweak.strip().encode("utf-8"), int(args.tid))
    print(to_uid(y))
    return 0


def cmd_dec(args: argparse.Namespace) -> int:
    if args.secret is None or args.secret == "":
        print("Error: --secret is required", file=sys.stderr)
        return 1
    if args.uid is None or args.uid == "":
        print("Error: --uid is required", file=sys.stderr)
        return 1
    y = from_uid(args.uid)
    key = derive_key(args.secret, args.tweak.strip(), args.kdf, args.iter)
    x = decrypt12(key, args.tweak.strip().encode("utf-8"), y)
    print(x)  # no leading zeros — TID as number
    return 0


def cmd_selftest(_: argparse.Namespace) -> int:
    # Reference cases (PBKDF2-SHA256, 200k iters) — copied from Go
    cases = [
        ("qwerty123", "123", 12_345_678, "5377-6196-7198"),
        ("qwerty123", "123", 123_456_789, "8678-9607-3662"),
        ("correct horse battery staple", "prod", 42, "3467-7244-0811"),
    ]
    for secret, tweak, tid, want in cases:
        key = derive_key(secret, tweak, "sha256", 200_000)
        y = encrypt12(key, tweak.encode("utf-8"), tid)
        back = decrypt12(key, tweak.encode("utf-8"), y)
        got = to_uid(y)
        ok = got == want and back == tid
        print(
            f'secret="{secret}" tweak="{tweak}" tid={tid} -> uid={got} -> back={back}  [{"OK" if ok else "FAIL"}]'
        )
        if not ok:
            print("self-test failed", file=sys.stderr)
            return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fpe12",
        description="Format-preserving encryption for 12-digit IDs (Feistel + HMAC-SHA256), Python port",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    enc = sub.add_parser("enc", help="encrypt TID -> UID")
    enc.add_argument("--tid", type=int, required=True, help="telegram id (digits, < 10^12)")
    enc.add_argument("--secret", type=str, required=True, help="secret passphrase (required)")
    enc.add_argument("--tweak", type=str, default="default", help="tweak/context label")
    enc.add_argument("--kdf", type=str, default="sha256", choices=["sha256", "sha1"], help="pbkdf2 hash")
    enc.add_argument("--iter", type=int, default=200_000, help="pbkdf2 iterations")
    enc.set_defaults(func=cmd_enc)

    dec = sub.add_parser("dec", help="decrypt UID -> TID")
    dec.add_argument("--uid", type=str, required=True, help="uid (0000-0000-0000 or 12 digits)")
    dec.add_argument("--secret", type=str, required=True, help="secret passphrase (required)")
    dec.add_argument("--tweak", type=str, default="default", help="tweak/context label")
    dec.add_argument("--kdf", type=str, default="sha256", choices=["sha256", "sha1"], help="pbkdf2 hash")
    dec.add_argument("--iter", type=int, default=200_000, help="pbkdf2 iterations")
    dec.set_defaults(func=cmd_dec)

    st = sub.add_parser("selftest", help="run reference vectors and roundtrip check")
    st.set_defaults(func=cmd_selftest)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
