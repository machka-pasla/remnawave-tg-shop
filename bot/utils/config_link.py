import base64
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from config.settings import Settings

CRYPT4_PREFIX = "happ://crypt4/"


@lru_cache(maxsize=1)
def _load_crypt4_public_key() -> Optional[RSAPublicKey]:
    """Load and cache the happ crypt4 public key from the project root."""
    pem_path = Path(__file__).resolve().parent.parent.parent / "happ-crypt4.pem"
    try:
        pem_bytes = pem_path.read_bytes()
        key = serialization.load_pem_public_key(pem_bytes)
        return key if isinstance(key, RSAPublicKey) else None
    except FileNotFoundError:
        logging.error("Crypt4 public key file not found at %s", pem_path)
    except Exception as exc:
        logging.error("Failed to load crypt4 public key: %s", exc, exc_info=True)
    return None


def _encrypt_raw_link(raw_link: str) -> Optional[str]:
    """Encrypt the raw subscription URL with RSA PKCS#1 v1.5 and return base64 payload."""
    public_key = _load_crypt4_public_key()
    if not public_key:
        return None

    try:
        encrypted = public_key.encrypt(raw_link.encode("utf-8"), padding.PKCS1v15())
        return base64.b64encode(encrypted).decode("utf-8")
    except Exception as exc:
        logging.error("Failed to encrypt config link with crypt4: %s", exc, exc_info=True)
        return None


def prepare_config_links(settings: Settings, raw_link: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Build the user-facing connection key and the URL for the connect button.

    Returns (display_link, button_link). When CRYPT4 is enabled the display link
    is encrypted and prefixed with happ://crypt4/, and the button link is wrapped
    with CRYPT4_REDIRECT_URL if provided.
    """
    if not raw_link:
        return None, None

    cleaned = raw_link.strip()
    if not cleaned:
        return None, None

    display_link = cleaned
    button_link = cleaned

    if settings.CRYPT4_ENABLED:
        encrypted_payload = _encrypt_raw_link(cleaned)
        if encrypted_payload:
            display_link = f"{CRYPT4_PREFIX}{encrypted_payload}"
            button_link = display_link
        else:
            logging.error("CRYPT4_ENABLED is set but encryption failed; using raw link as fallback.")

    redirect_base = (settings.CRYPT4_REDIRECT_URL or "").strip()
    if redirect_base and settings.CRYPT4_ENABLED and display_link:
        button_link = f"{redirect_base}{display_link}"

    return display_link, button_link
