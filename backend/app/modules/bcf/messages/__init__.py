# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Self-contained i18n bundle for the BCF module.

OpenEstimate principle #2: i18n EVERYWHERE - zero hardcoded user-facing
strings. This mirrors the design of
:mod:`app.core.validation.messages`: a module-local ``messages/``
directory makes the BCF module "plugin-like" - it carries its own
translations without touching the global locales.

Resolution chain: requested locale → ``en`` → humanised key fallback.
``str.format`` placeholders match the platform i18n convention.

Public API
    * :func:`translate(key, locale="en", **params) -> str`
    * :func:`available_locales() -> list[str]`
    * :func:`reload_bundle()` - test helper.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LOCALE = "en"
_MESSAGES_DIR = Path(__file__).parent
_LOCK = Lock()


class _Bundle:
    """In-memory, lazily-loaded flattened message table keyed by locale."""

    def __init__(self) -> None:
        self._loaded: dict[str, dict[str, str]] = {}
        self._is_loaded = False
        self._warned: set[str] = set()

    def load(self) -> None:
        if self._is_loaded:
            return
        self._loaded.clear()
        for locale_file in sorted(_MESSAGES_DIR.glob("*.json")):
            locale = locale_file.stem
            try:
                with locale_file.open(encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                logger.exception("Failed to load BCF messages for %r", locale)
                continue
            self._loaded[locale] = _flatten(data)
        self._is_loaded = True

    def reload(self) -> None:
        self._is_loaded = False
        self._warned.clear()
        self.load()

    def translate(self, key: str, locale: str, **params: Any) -> str:
        with _LOCK:
            self.load()
        requested = self._loaded.get(locale, {})
        en = self._loaded.get(DEFAULT_LOCALE, {})
        template = requested.get(key) or en.get(key)
        if template is None:
            if key not in self._warned:
                self._warned.add(key)
                logger.warning(
                    "BCF message key %r missing for locale %r - humanising",
                    key,
                    locale,
                )
            template = _humanise(key)
        if not params:
            return template
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            return template

    def available_locales(self) -> list[str]:
        with _LOCK:
            self.load()
        return sorted(self._loaded.keys())


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for raw_key, value in data.items():
        key = f"{prefix}.{raw_key}" if prefix else raw_key
        if isinstance(value, dict):
            flat.update(_flatten(value, key))
        else:
            flat[key] = str(value)
    return flat


def _humanise(key: str) -> str:
    segments = [s for s in key.replace("/", ".").split(".") if s]
    if not segments:
        return "BCF error"
    words = segments[-1].replace("_", " ").replace("-", " ").strip()
    return (words[0].upper() + words[1:]) if words else "BCF error"


_default = _Bundle()


def translate(key: str, locale: str = DEFAULT_LOCALE, **params: Any) -> str:
    """Resolve a BCF message key for ``locale`` with ``str.format`` params."""
    return _default.translate(key, locale, **params)


def available_locales() -> list[str]:
    """List locales currently loaded into the BCF bundle."""
    return _default.available_locales()


def reload_bundle() -> None:
    """Force a cache refresh (test helper)."""
    _default.reload()


__all__ = ["available_locales", "reload_bundle", "translate"]
