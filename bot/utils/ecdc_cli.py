#!/usr/bin/env python3
# ecdc_cli.py
# Ручной CLI для проверки работы ecdc_api/ecdc_core:
# - читает конфиг из окружения (ECDC_*), флагами можно переопределить
# - использует ecdc_api (который опирается на ecdc_core)
# - режимы: enc / dec / selftest
from __future__ import annotations

import argparse
import os
import sys
from typing import Literal, Optional

# === ПУТЬ К API ===============================================================
# Если перенесёте файл в другую директорию — поправьте импорт:
from ecdc_api import EcdcService  # <- при переносе измените путь


ENV_SECRET = "ECDC_SECRET"
ENV_TWEAK = "ECDC_TWEAK"
ENV_KDF = "ECDC_KDF"
ENV_ITER = "ECDC_ITER"


def _resolve_conf(
    *,
    secret: Optional[str],
    tweak: Optional[str],
    kdf: Optional[str],
    iterations: Optional[int],
) -> tuple[str, str, Literal["sha256", "sha1"], int]:
    """
    Итоговая конфигурация с приоритетом: флаг CLI > ENV > дефолт.
    """
    # SECRET обязателен: из флага или из env
    sec = secret if secret is not None else os.getenv(ENV_SECRET)
    if not sec:
        raise ValueError(f"--secret not provided and {ENV_SECRET} is not set")

    # Остальные — с дефолтами
    tw = (tweak if tweak is not None else os.getenv(ENV_TWEAK, "default")).strip()
    k = (kdf if kdf is not None else os.getenv(ENV_KDF, "sha256")).strip().lower()
    if k not in ("sha256", "sha1"):
        raise ValueError(f"invalid KDF: {k!r} (allowed: sha256|sha1)")

    it_raw = str(iterations) if iterations is not None else os.getenv(ENV_ITER, "200000")
    try:
        it = int(it_raw)
    except ValueError as e:
        raise ValueError(f"invalid {ENV_ITER} value: {it_raw!r}") from e

    if it <= 0:
        raise ValueError("iterations must be positive")

    return sec, tw, k, it  # type: ignore[return-value]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ecdc",
        description=(
            "Encrypt/Decrypt CLI for 12-digit IDs via ecdc_api/ecdc_core.\n"
            f"Config via env: {ENV_SECRET} (required), {ENV_TWEAK}='default', {ENV_KDF}='sha256', {ENV_ITER}=200000.\n"
            "CLI flags override env."
        ),
        add_help=True,
    )
    sub = p.add_subparsers(dest="cmd")

    # Общие (опциональные) конфиги — добавим во все подкоманды
    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--secret", type=str, default=None, help=f"or set {ENV_SECRET}")
        sp.add_argument("--tweak", type=str, default=None, help=f"or set {ENV_TWEAK} (default 'default')")
        sp.add_argument("--kdf", type=str, choices=["sha256", "sha1"], default=None, help=f"or set {ENV_KDF} (default sha256)")
        sp.add_argument("--iter", dest="iterations", type=int, default=None, help=f"or set {ENV_ITER} (default 200000)")

    enc = sub.add_parser("enc", help="Encrypt TID -> UID")
    enc.add_argument("--tid", type=int, required=True, help="telegram id (digits, < 10^12)")
    add_common(enc)

    dec = sub.add_parser("dec", help="Decrypt UID -> TID")
    dec.add_argument("--uid", type=str, required=True, help="uid 'XXXX-XXXX-XXXX' or 12 digits")
    add_common(dec)

    st = sub.add_parser("selftest", help="Run reference vectors and a couple of roundtrips")
    add_common(st)

    return p


def cmd_enc(args: argparse.Namespace) -> int:
    secret, tweak, kdf, iterations = _resolve_conf(
        secret=args.secret, tweak=args.tweak, kdf=args.kdf, iterations=args.iterations
    )
    svc = EcdcService(secret=secret, tweak=tweak, kdf=kdf, iterations=iterations)
    try:
        uid = svc.enc_ttu(int(args.tid))
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1
    print(uid)
    return 0


def cmd_dec(args: argparse.Namespace) -> int:
    secret, tweak, kdf, iterations = _resolve_conf(
        secret=args.secret, tweak=args.tweak, kdf=args.kdf, iterations=args.iterations
    )
    svc = EcdcService(secret=secret, tweak=tweak, kdf=kdf, iterations=iterations)
    try:
        tid = svc.dec_utt(args.uid)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1
    print(tid)
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    """
    Самотест связывает ВСЕ слои:
    - собирает конфиг (env/flags) → создаёт EcdcService (ecdc_api) → вызывает методы,
      которые внутри используют ecdc_core.
    - Прогоняет эталонные кейсы и пару простых roundtrip'ов.
    """
    secret, tweak, kdf, iterations = _resolve_conf(
        secret=args.secret, tweak=args.tweak, kdf=args.kdf, iterations=args.iterations
    )
    svc = EcdcService(secret=secret, tweak=tweak, kdf=kdf, iterations=iterations)

    ok_all = True

    # Эталонные векторы — совпадают с портом из Go
    vectors = [
        ("qwerty123", "123", 12_345_678, "5377-6196-7198"),
        ("qwerty123", "123", 123_456_789, "8678-9607-3662"),
        ("correct horse battery staple", "prod", 42, "3467-7244-0811"),
    ]
    print("Reference vectors (use their own secrets/tweaks, independent from env):")
    for sec, tw, tid, want in vectors:
        svc_vec = EcdcService(secret=sec, tweak=tw, kdf="sha256", iterations=200_000)
        uid = svc_vec.enc_ttu(tid)
        back = svc_vec.dec_utt(uid)
        ok = (uid == want) and (back == tid)
        ok_all &= ok
        print(f'  secret="{sec}" tweak="{tw}" tid={tid} -> uid={uid} -> back={back}  [{"OK" if ok else "FAIL"}]')

    # Roundtrip на текущем конфиге
    print("\nRoundtrips with current config (from env/flags):")
    samples = [0, 42, 12345678, 999_999_999_999 % 1_000_000_000_000]
    for tid in samples:
        try:
            uid = svc.enc_ttu(tid)
            back = svc.dec_utt(uid)
            ok = (back == tid)
            ok_all &= ok
            print(f"  tid={tid} -> {uid} -> {back}  [{'OK' if ok else 'FAIL'}]")
        except Exception as e:
            ok_all = False
            print(f"  tid={tid} -> Error: {e}")

    return 0 if ok_all else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "cmd", None):
        parser.print_help(sys.stdout)
        return 0

    if args.cmd == "enc":
        return cmd_enc(args)
    elif args.cmd == "dec":
        return cmd_dec(args)
    elif args.cmd == "selftest":
        return cmd_selftest(args)

    parser.print_help(sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
