"""Internationalization service — simple dict-based string lookup.

Loads JSON locale files from locales/ directory. Vietnamese is canonical,
English is best-effort translation. Fallback chain: requested lang -> vi -> raw key.
"""

import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

LOCALES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "locales",
)

SUPPORTED_LANGUAGES = {
    "vi": "Tiếng Việt",
    "en": "English",
}


class I18n:
    """Singleton for internationalized string lookup.

    Language is set at startup and persists for the session.
    The singleton construction is thread-safe; runtime t() calls
    rely on CPython's GIL for dict read atomicity.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._lang = "vi"
        self._strings: dict[str, str] = {}
        self._fallback: dict[str, str] = {}
        self._load_fallback()
        self._load(self._lang)

    def _load_fallback(self):
        """Load Vietnamese as fallback (canonical locale)."""
        self._fallback = self._read_locale("vi")

    def _load(self, lang: str):
        """Load locale file for given language."""
        if lang == "vi":
            self._strings = self._fallback
        else:
            self._strings = self._read_locale(lang)

    def _read_locale(self, lang: str) -> dict[str, str]:
        """Read JSON locale file."""
        path = os.path.join(LOCALES_DIR, f"{lang}.json")
        if not os.path.exists(path):
            logger.warning(f"Locale file not found: {path}")
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load locale {lang}: {e}")
            return {}

    def t(self, key: str, **kwargs) -> str:
        """Translate key. Supports {variable} interpolation.

        Fallback: requested lang -> Vietnamese -> raw key.
        """
        text = self._strings.get(key) or self._fallback.get(key) or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text

    def set_language(self, lang: str):
        """Switch active language."""
        if lang not in SUPPORTED_LANGUAGES:
            logger.warning(f"Unsupported language: {lang}")
            return
        self._lang = lang
        self._load(lang)
        logger.info(f"Language set to: {lang}")

    @property
    def lang(self) -> str:
        return self._lang

    @staticmethod
    def available_languages() -> dict[str, str]:
        """Return dict of lang_code -> display_name."""
        return dict(SUPPORTED_LANGUAGES)
