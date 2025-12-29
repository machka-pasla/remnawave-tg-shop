import logging
from typing import Optional, Tuple

from config.settings import Settings
from bot.services.panel_api_service import PanelApiService

CRYPT4_PREFIX = "happ://crypt4/"


async def _encrypt_raw_link(settings: Settings, raw_link: str) -> Optional[str]:
    """Encrypt the raw subscription URL using the panel's happ crypt4 API."""
    async with PanelApiService(settings) as panel_service:
        encrypted_link = await panel_service.encrypt_happ_link(raw_link)
        if encrypted_link:
            return encrypted_link
    return None


async def prepare_config_links(settings: Settings, raw_link: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
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
        encrypted_payload = await _encrypt_raw_link(settings, cleaned)
        if encrypted_payload:
            display_link = f"{CRYPT4_PREFIX}{encrypted_payload}"
            button_link = display_link
        else:
            logging.error("CRYPT4_ENABLED is set but encryption failed; using raw link as fallback.")

    redirect_base = (settings.CRYPT4_REDIRECT_URL or "").strip()
    if redirect_base and settings.CRYPT4_ENABLED and display_link:
        button_link = f"{redirect_base}{display_link}"

    return display_link, button_link
