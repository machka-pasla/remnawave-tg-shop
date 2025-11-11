import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Optional


class FileIDCache:
    """Simple async-aware cache for storing Telegram file IDs in JSON."""

    def __init__(self, cache_path: Path) -> None:
        self._cache_path = cache_path
        self._cache: Optional[Dict[str, str]] = None
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self) -> Dict[str, str]:
        if self._cache is not None:
            return self._cache

        cache: Dict[str, str] = {}
        if self._cache_path.exists():
            try:
                with self._cache_path.open("r", encoding="utf-8") as cache_file:
                    data = json.load(cache_file)
                if isinstance(data, dict):
                    cache = {
                        str(key): str(value)
                        for key, value in data.items()
                        if isinstance(value, str)
                    }
            except Exception as exc:
                logging.warning(
                    "Failed to load file_id cache from %s: %s",
                    self._cache_path,
                    exc,
                )

        self._cache = cache
        return self._cache

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            cache = await self._ensure_loaded()
            return cache.get(key)

    async def set(self, key: str, value: str) -> None:
        if not value:
            return

        async with self._lock:
            cache = await self._ensure_loaded()
            if cache.get(key) == value:
                return

            cache[key] = value

            try:
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                with self._cache_path.open("w", encoding="utf-8") as cache_file:
                    json.dump(cache, cache_file, ensure_ascii=False, indent=2)
            except Exception as exc:
                logging.warning(
                    "Failed to save file_id cache to %s: %s",
                    self._cache_path,
                    exc,
                )
