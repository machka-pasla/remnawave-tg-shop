from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional, Union

from config.settings import Settings
from bot.utils.ecdc_api import EcdcService

UIDLike = Union[int, str]
UGIDLike = Union[int, str]
ChatIdLike = Union[int, str]


@dataclass(frozen=True)
class UserIdentity:
    tid: int
    uid: str


class IdBridge:
    """
    Central adapter that keeps UID/UGID inside the domain and converts them
    to TID/TGID only when talking to Telegram or third-party APIs.
    """

    def __init__(self, settings: Settings) -> None:
        self._enabled = settings.TELEGRAM_ID_ENCRYPTION
        self._settings = settings
        self._ecdc: Optional[EcdcService] = None

        if self._enabled:
            self._ecdc = EcdcService(
                secret=settings.ECDC_SECRET or "",
                tweak=settings.ECDC_TWEAK or "default",
                kdf=(settings.ECDC_KDF or "sha256").lower(),  # type: ignore[arg-type]
                iterations=settings.ECDC_ITER or 200_000,
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    # --- Users -----------------------------------------------------------------
    def tid_to_uid(self, tid: int) -> str:
        if tid is None:
            raise ValueError("tid_to_uid requires non-empty tid")
        if not self._enabled or not self._ecdc:
            return str(tid)
        return self._ecdc.enc_ttu(tid)

    def uid_to_tid(self, uid: UIDLike) -> int:
        if uid is None:
            raise ValueError("uid_to_tid requires non-empty uid")
        if not self._enabled or not self._ecdc:
            return int(uid)
        normalized = self._normalize_uid(uid)
        return self._ecdc.dec_utt(normalized)

    def normalize_uid(self, uid: UIDLike) -> str:
        if not self._enabled:
            if isinstance(uid, int):
                return str(uid)
            return uid
        return self._normalize_uid(uid)

    def build_identity(self, tid: int) -> UserIdentity:
        return UserIdentity(tid=tid, uid=self.tid_to_uid(tid))

    def is_admin(self, tid: int, admin_ids: list[Union[int, str]]) -> bool:
        if not admin_ids:
            return False
        if not self._enabled:
            return tid in admin_ids
        return self.tid_to_uid(tid) in admin_ids

    # --- Groups/chats ----------------------------------------------------------
    def tgid_to_ugid(self, tgid: int) -> Union[int, str]:
        if tgid is None:
            raise ValueError("tgid_to_ugid requires chat id")
        if not self._enabled or not self._ecdc:
            return tgid
        return self._ecdc.encg(tgid)

    def ugid_to_tgid(self, ugid: UGIDLike) -> int:
        if ugid is None:
            raise ValueError("ugid_to_tgid requires chat reference")
        if not self._enabled or not self._ecdc:
            return int(ugid)
        normalized = self._normalize_ugid(ugid)
        return self._ecdc.decg(normalized)

    def resolve_chat_reference(self, reference: Optional[ChatIdLike]) -> Optional[int]:
        """
        Convert chat references from settings (UGID or TGID) to numeric Telegram IDs.
        """
        if reference is None:
            return None
        if not self._enabled:
            return int(reference)

        ref_str = str(reference).strip()
        digits = re.sub(r"\D", "", ref_str)
        if len(digits) == 16:
            return self.ugid_to_tgid(ref_str)
        if digits:
            return int(reference)
        raise ValueError(f"Unsupported chat reference format: {reference!r}")

    # --- Internal helpers ------------------------------------------------------
    @staticmethod
    def _normalize_uid(uid: UIDLike) -> str:
        digits = re.sub(r"\D", "", str(uid))
        if len(digits) != 12:
            raise ValueError(f"UID must consist of 12 digits, got '{uid}'")
        return f"{digits[:4]}-{digits[4:8]}-{digits[8:]}"

    @staticmethod
    def _normalize_ugid(ugid: UGIDLike) -> str:
        digits = re.sub(r"\D", "", str(ugid))
        if len(digits) != 16:
            raise ValueError(f"UGID must consist of 16 digits, got '{ugid}'")
        return f"-{digits[:4]}-{digits[4:8]}-{digits[8:12]}-{digits[12:]}"


_BRIDGE: Optional[IdBridge] = None


def init_id_bridge(settings: Settings) -> IdBridge:
    global _BRIDGE
    _BRIDGE = IdBridge(settings)
    return _BRIDGE


def get_id_bridge() -> IdBridge:
    if _BRIDGE is None:
        raise RuntimeError("IdBridge is not initialized")
    return _BRIDGE


def is_admin_user(user_tid: int, settings: Settings) -> bool:
    try:
        bridge = get_id_bridge()
    except RuntimeError:
        bridge = None
    if bridge:
        return bridge.is_admin(user_tid, settings.ADMIN_IDS)
    return user_tid in settings.ADMIN_IDS


def admin_recipient_ids(settings: Settings) -> list[int]:
    recipients: list[int] = []
    if not settings.ADMIN_IDS:
        return recipients
    try:
        bridge = get_id_bridge()
    except RuntimeError:
        bridge = None
    if bridge and bridge.enabled:
        for admin_uid in settings.ADMIN_IDS:
            try:
                recipients.append(bridge.uid_to_tid(admin_uid))
            except Exception as exc:
                logging.error(f"Invalid admin UID {admin_uid}: {exc}")
    else:
        for admin_raw in settings.ADMIN_IDS:
            try:
                recipients.append(int(admin_raw))
            except (TypeError, ValueError):
                logging.error(f"Invalid admin identifier {admin_raw}")
    return recipients
