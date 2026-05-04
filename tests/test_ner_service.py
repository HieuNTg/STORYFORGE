"""Coverage tests for `services.ner_service` (Sprint 2 P7).

The real spaCy model (`xx_ent_wiki_sm`) is mocked to keep the suite hermetic:
- successful load path returns a fake nlp callable
- failure path simulates a missing model
- `extract_persons` returns NFC-normalised, deduplicated PER entities
"""

from __future__ import annotations

import sys
import types
import unicodedata
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers — fake spaCy doc/ent objects
# ---------------------------------------------------------------------------


class _FakeEnt:
    def __init__(self, text: str, label: str = "PER") -> None:
        self.text = text
        self.label_ = label


class _FakeDoc:
    def __init__(self, ents: list[_FakeEnt]) -> None:
        self.ents = ents


def _fake_nlp_factory(per_per_text: dict[str, list[_FakeEnt]]):
    """Return a callable that mimics `nlp(text) -> Doc`."""

    def _nlp(text: str) -> _FakeDoc:
        return _FakeDoc(per_per_text.get(text, []))

    return _nlp


# ---------------------------------------------------------------------------
# Fixture: reset the singleton between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_ner():
    from services.ner_service import reset_ner_service

    reset_ner_service()
    yield
    reset_ner_service()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSingletonAccessor:
    def test_returns_same_instance(self):
        from services.ner_service import get_ner_service

        a = get_ner_service()
        b = get_ner_service()
        assert a is b

    def test_reset_drops_singleton(self):
        from services.ner_service import get_ner_service, reset_ner_service

        a = get_ner_service()
        reset_ner_service()
        b = get_ner_service()
        assert a is not b


class TestLoadAvailableTrue:
    def test_is_available_true_when_spacy_loads(self):
        from services.ner_service import get_ner_service

        fake_nlp = _fake_nlp_factory({})
        fake_spacy = types.ModuleType("spacy")
        fake_spacy.load = MagicMock(return_value=fake_nlp)

        with patch.dict(sys.modules, {"spacy": fake_spacy}):
            svc = get_ner_service()
            assert svc.is_available() is True
            fake_spacy.load.assert_called_once_with("xx_ent_wiki_sm")

    def test_is_available_idempotent(self):
        """Calling _load again must not re-import or rebind the model."""
        from services.ner_service import get_ner_service

        fake_nlp = _fake_nlp_factory({})
        fake_spacy = types.ModuleType("spacy")
        fake_spacy.load = MagicMock(return_value=fake_nlp)

        with patch.dict(sys.modules, {"spacy": fake_spacy}):
            svc = get_ner_service()
            assert svc.is_available() is True
            assert svc.is_available() is True
            # Only the first call should invoke spacy.load
            assert fake_spacy.load.call_count == 1


class TestLoadAvailableFalse:
    def test_load_failure_marks_unavailable(self):
        from services.ner_service import get_ner_service

        fake_spacy = types.ModuleType("spacy")
        fake_spacy.load = MagicMock(side_effect=OSError("model not found"))

        with patch.dict(sys.modules, {"spacy": fake_spacy}):
            svc = get_ner_service()
            assert svc.is_available() is False

    def test_unavailable_short_circuits_subsequent_calls(self):
        """After a failed load, _load must not retry."""
        from services.ner_service import get_ner_service

        fake_spacy = types.ModuleType("spacy")
        fake_spacy.load = MagicMock(side_effect=OSError("model not found"))

        with patch.dict(sys.modules, {"spacy": fake_spacy}):
            svc = get_ner_service()
            assert svc.is_available() is False
            assert svc.is_available() is False
            # Only one attempt
            assert fake_spacy.load.call_count == 1

    def test_extract_persons_returns_empty_when_unavailable(self):
        from services.ner_service import get_ner_service

        fake_spacy = types.ModuleType("spacy")
        fake_spacy.load = MagicMock(side_effect=OSError("nope"))

        with patch.dict(sys.modules, {"spacy": fake_spacy}):
            svc = get_ner_service()
            result = svc.extract_persons("Long đi vào động.")
            assert result == set()


class TestExtractPersons:
    def test_extracts_per_entities_only(self):
        from services.ner_service import get_ner_service

        text = "Long và Mai đi cùng nhau"
        ents = [
            _FakeEnt("Long", "PER"),
            _FakeEnt("Mai", "PERSON"),
            _FakeEnt("Hà Nội", "LOC"),  # excluded
            _FakeEnt("Apple", "ORG"),  # excluded
        ]
        fake_nlp = _fake_nlp_factory({text: ents})
        fake_spacy = types.ModuleType("spacy")
        fake_spacy.load = MagicMock(return_value=fake_nlp)

        with patch.dict(sys.modules, {"spacy": fake_spacy}):
            svc = get_ner_service()
            assert svc.extract_persons(text) == {"Long", "Mai"}

    def test_nfc_normalisation_applied(self):
        """Decomposed NFD input must collapse to NFC form on output."""
        from services.ner_service import get_ner_service

        # NFD form of "Long" with combining diacritic on the o
        nfd_name = unicodedata.normalize("NFD", "Lông")
        assert nfd_name != "Lông"  # sanity: NFD differs from NFC

        text = "raw"
        ents = [_FakeEnt(nfd_name, "PER")]
        fake_nlp = _fake_nlp_factory({text: ents})
        fake_spacy = types.ModuleType("spacy")
        fake_spacy.load = MagicMock(return_value=fake_nlp)

        with patch.dict(sys.modules, {"spacy": fake_spacy}):
            svc = get_ner_service()
            persons = svc.extract_persons(text)
            assert "Lông" in persons  # NFC form
            # Ensure no NFD form leaked through
            for p in persons:
                assert p == unicodedata.normalize("NFC", p)

    def test_strips_whitespace_and_drops_empty(self):
        from services.ner_service import get_ner_service

        text = "raw"
        ents = [
            _FakeEnt("  Long  ", "PER"),
            _FakeEnt("", "PER"),
            _FakeEnt("   ", "PER"),
        ]
        fake_nlp = _fake_nlp_factory({text: ents})
        fake_spacy = types.ModuleType("spacy")
        fake_spacy.load = MagicMock(return_value=fake_nlp)

        with patch.dict(sys.modules, {"spacy": fake_spacy}):
            svc = get_ner_service()
            assert svc.extract_persons(text) == {"Long"}

    def test_deduplicates_repeated_entities(self):
        from services.ner_service import get_ner_service

        text = "Long, Long, Long again"
        ents = [_FakeEnt("Long", "PER")] * 3
        fake_nlp = _fake_nlp_factory({text: ents})
        fake_spacy = types.ModuleType("spacy")
        fake_spacy.load = MagicMock(return_value=fake_nlp)

        with patch.dict(sys.modules, {"spacy": fake_spacy}):
            svc = get_ner_service()
            assert svc.extract_persons(text) == {"Long"}


class TestThreadSafety:
    def test_lock_prevents_double_load(self):
        """Two probes from the same instance still produce one load call."""
        from services.ner_service import NERService

        fake_nlp = _fake_nlp_factory({})
        fake_spacy = types.ModuleType("spacy")
        fake_spacy.load = MagicMock(return_value=fake_nlp)

        with patch.dict(sys.modules, {"spacy": fake_spacy}):
            svc = NERService()
            svc.is_available()
            svc.is_available()
            assert fake_spacy.load.call_count == 1
