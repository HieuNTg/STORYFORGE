"""spaCy NER service for PERSON entity extraction (Sprint 2, P4).

Lazy singleton wrapping `xx_ent_wiki_sm` (multilingual, ~12 MB).
Primary use: character presence detection in structural checks.

Tradeoff (D2): `xx_ent_wiki_sm` is weak on Vietnamese — canonical-name
substring fallback (word-boundary `\b` regex) in the structural detector
carries most of the load for Vietnamese names. The NER layer catches
multi-word names like "Nguyễn Long" reliably when the model fires, and
the substring fallback handles cases where NER misses.

Model download (one-time, post-install):
    python -m spacy download xx_ent_wiki_sm
or
    python scripts/install_spacy_model.py
"""

from __future__ import annotations

import logging
import threading
import unicodedata

logger = logging.getLogger(__name__)


class NERService:
    """Lazy singleton wrapping spaCy xx_ent_wiki_sm.

    Use `get_ner_service()` rather than constructing directly so the
    process-wide singleton (and loaded model) is reused across chapters.
    """

    def __init__(self) -> None:
        self._nlp = None
        self._available: bool | None = None  # None = not probed yet
        self._lock = threading.Lock()

    # -- lifecycle ----------------------------------------------------------

    def _load(self) -> None:
        """Load xx_ent_wiki_sm on first use. Idempotent and thread-safe."""
        if self._nlp is not None or self._available is False:
            return
        with self._lock:
            if self._nlp is not None or self._available is False:
                return
            try:
                import spacy  # noqa: PLC0415 — intentional lazy import
                self._nlp = spacy.load("xx_ent_wiki_sm")
                self._available = True
                logger.info("NER model loaded: xx_ent_wiki_sm")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "spaCy xx_ent_wiki_sm load failed (%s); "
                    "NER degraded to canonical-name substring fallback.",
                    exc,
                )
                self._nlp = None
                self._available = False

    def is_available(self) -> bool:
        if self._available is None:
            self._load()
        return bool(self._available)

    # -- API ----------------------------------------------------------------

    def extract_persons(self, text: str) -> set[str]:
        """Return PER entity strings from *text*.

        Returns NFC-normalised, whitespace-stripped entity strings.
        Falls back to empty set if the model failed to load.
        """
        if not self.is_available():
            return set()
        assert self._nlp is not None
        doc = self._nlp(text)
        result: set[str] = set()
        for ent in doc.ents:
            if ent.label_ in ("PER", "PERSON"):
                norm = unicodedata.normalize("NFC", ent.text).strip()
                if norm:
                    result.add(norm)
        return result


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service: NERService | None = None
_singleton_lock = threading.Lock()


def get_ner_service() -> NERService:
    """Process-wide singleton accessor."""
    global _service
    with _singleton_lock:
        if _service is None:
            _service = NERService()
        return _service


def reset_ner_service() -> None:
    """Test helper — drops the singleton so the next call creates a fresh one."""
    global _service
    with _singleton_lock:
        _service = None


__all__ = [
    "NERService",
    "get_ner_service",
    "reset_ner_service",
]
