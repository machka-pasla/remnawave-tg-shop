import re
import unicodedata
from typing import Optional

_OBFUSCATION_CHARS = " .\\-/\\\\•﹒٫＿․·∙‧ꞏ‒–—﹘﹣⁻−"

_URL_PATTERNS = [
    re.compile(r"(?i)https?://\S+"),
    re.compile(r"(?i)www\.\S+"),
    re.compile(r"(?i)tg://\S+"),
    re.compile(r"(?i)telegram\.me\S*"),
    re.compile(r"(?i)t\.me/\+\S*"),
    re.compile(r"(?i)joinchat\S*"),
]

_OBFUSCATED_DOMAIN_PATTERNS = [
    re.compile(
        r"(?i)[tт][\s{}\u2022]*[\.{}\u2022]*[\s{}\u2022]*[mм][eе]".format(
            re.escape(_OBFUSCATION_CHARS),
            re.escape(_OBFUSCATION_CHARS),
            re.escape(_OBFUSCATION_CHARS),
        )
    ),
    re.compile(
        r"(?i)[tт][{}\s]*[eе][{}\s]*[lłl1i|][{}\s]*[eе]"
        r"[{}\s]*[gɢgqг][{}\s]*[rр][{}\s]*[aа]"
        r"[{}\s]*(?:[mм]|rn)".format(
            re.escape(_OBFUSCATION_CHARS),
            re.escape(_OBFUSCATION_CHARS),
            re.escape(_OBFUSCATION_CHARS),
            re.escape(_OBFUSCATION_CHARS),
            re.escape(_OBFUSCATION_CHARS),
            re.escape(_OBFUSCATION_CHARS),
            re.escape(_OBFUSCATION_CHARS),
        )
    ),
    re.compile(r"(?i)t\.me\S*"),
]

_ENGLISH_SERVICE_PATTERNS = [
    re.compile(r"(?i)telegram"),
    re.compile(r"(?i)teleqram"),
    re.compile(r"(?i)teiegram"),
    re.compile(r"(?i)teieqram"),
    re.compile(r"(?i)telegrarn"),
    re.compile(r"(?i)service"),
    re.compile(r"(?i)notif(?:ication)?"),
    re.compile(r"(?i)system"),
    re.compile(r"(?i)security"),
    re.compile(r"(?i)safety"),
    re.compile(r"(?i)support"),
    re.compile(r"(?i)moderation"),
    re.compile(r"(?i)review"),
    re.compile(r"(?i)compliance"),
    re.compile(r"(?i)abuse"),
    re.compile(r"(?i)spam"),
    re.compile(r"(?i)report"),
]

_RUSSIAN_SERVICE_PATTERNS = [
    re.compile(r"(?i)телеграм\w*"),
    re.compile(r"(?i)служебн\w*"),
    re.compile(r"(?i)уведомлен\w*"),
    re.compile(r"(?i)поддержк\w*"),
    re.compile(r"(?i)безопасн\w*"),
    re.compile(r"(?i)модерац\w*"),
    re.compile(r"(?i)жалоб\w*"),
    re.compile(r"(?i)абуз\w*"),
]

_PRE_LOWER_TRANSLATION = str.maketrans(
    {
        "I": "l",
        "İ": "l",
        "Q": "g",
        "＠": " ",
    }
)

_POST_LOWER_TRANSLATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "і": "i",
        "й": "i",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sh",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
        "＿": "_",
    }
)

_NORMALIZED_BANNED_TOKENS = {
    "tme",
    "telegram",
    "teleqram",
    "teiegram",
    "teieqram",
    "telegrarn",
    "joinchat",
    "http",
    "https",
    "www",
    "tg",
    "service",
    "notification",
    "system",
    "security",
    "safety",
    "support",
    "moderation",
    "review",
    "compliance",
    "abuse",
    "spam",
    "report",
}

_USERNAME_PLACEHOLDER = "клиент"


def _normalize_for_detection(value: str) -> str:
    if not value:
        return ""

    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.translate(_PRE_LOWER_TRANSLATION)
    normalized = normalized.lower()
    normalized = "".join(
        ch for ch in normalized if unicodedata.category(ch) != "Mn"
    )
    normalized = normalized.translate(_POST_LOWER_TRANSLATION)
    normalized = normalized.replace("rn", "m")

    pattern = rf"[{re.escape(_OBFUSCATION_CHARS)}\s]+"
    normalized = re.sub(pattern, "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    return normalized


def _remove_patterns(value: str) -> str:
    updated = value
    for pattern in (
        _URL_PATTERNS
        + _OBFUSCATED_DOMAIN_PATTERNS
        + _ENGLISH_SERVICE_PATTERNS
        + _RUSSIAN_SERVICE_PATTERNS
    ):
        updated = pattern.sub(" ", updated)
    return updated


def _finalize(value: str) -> Optional[str]:
    compacted = re.sub(r"\s+", " ", value)
    compacted = compacted.strip(" \t\r\n-_.,/\\")
    compacted = compacted.strip()
    if not compacted:
        return None

    normalized = _normalize_for_detection(compacted)
    if any(token in normalized for token in _NORMALIZED_BANNED_TOKENS):
        return None
    return compacted


def sanitize_display_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    clean = value.replace("@", " ")
    clean = _remove_patterns(clean)
    return _finalize(clean)


def sanitize_username(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    clean = value.strip()
    clean = clean.lstrip("@")
    clean = _remove_patterns(clean)
    return _finalize(clean)


def username_for_display(username: Optional[str], with_at: bool = False) -> str:
    sanitized = sanitize_username(username)
    if not sanitized:
        return _USERNAME_PLACEHOLDER
    return f"@{sanitized}" if with_at else sanitized


def display_name_or_fallback(
    first_name: Optional[str],
    fallback: Optional[str] = None,
) -> str:
    sanitized = sanitize_display_name(first_name)
    if sanitized:
        return sanitized
    if fallback is not None:
        return fallback
    return _USERNAME_PLACEHOLDER
