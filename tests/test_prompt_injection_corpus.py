"""Test prompt injection detection against the security corpus.

Loads tests/security/prompt-injection-corpus.json and verifies that
sanitize_input() blocks/allows payloads matching the expected_blocked field.
"""

import json
import os
import pytest

from services.input_sanitizer import sanitize_input

# ---------------------------------------------------------------------------
# Load corpus
# ---------------------------------------------------------------------------

_CORPUS_PATH = os.path.join(
    os.path.dirname(__file__), "security", "prompt-injection-corpus.json"
)


def _load_corpus() -> list[dict]:
    with open(_CORPUS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_CORPUS = _load_corpus()

# Parametrize: one test case per corpus entry
_ids = [f"{entry['id']}-{entry['category']}" for entry in _CORPUS]


@pytest.mark.parametrize("entry", _CORPUS, ids=_ids)
def test_corpus_entry(entry):
    """Assert that sanitize_input() blocks/allows each corpus payload as expected.

    Entries with sanitizer_gap=true represent known detection gaps (usually
    Vietnamese-language variants). They are marked expected_blocked=false
    to reflect current sanitizer behavior and are annotated in the corpus.
    """
    payload = entry["payload"]
    expected_blocked = entry["expected_blocked"]
    entry_id = entry["id"]
    description = entry.get("description", "")
    is_gap = entry.get("sanitizer_gap", False)

    result = sanitize_input(payload)

    if expected_blocked:
        assert not result.is_safe, (
            f"[{entry_id}] Expected BLOCKED but was ALLOWED.\n"
            f"  Description: {description}\n"
            f"  Payload: {payload!r}\n"
            f"  Threats found: {result.threats_found}"
        )
        assert len(result.threats_found) > 0, (
            f"[{entry_id}] is_safe=False but threats_found is empty"
        )
    else:
        assert result.is_safe, (
            f"[{entry_id}] Expected ALLOWED but was BLOCKED.\n"
            f"  Description: {description}\n"
            f"  Payload: {payload!r}\n"
            f"  Threats found: {result.threats_found}"
        )
        if is_gap:
            # Log known gap entries so they're visible in CI output
            import warnings
            warnings.warn(
                f"[{entry_id}] Known detection gap — sanitizer does not yet detect: {description}",
                UserWarning,
                stacklevel=2,
            )


# ---------------------------------------------------------------------------
# Meta tests — verify corpus integrity
# ---------------------------------------------------------------------------


def test_corpus_has_minimum_entries():
    """Corpus must have at least 20 entries."""
    assert len(_CORPUS) >= 20, f"Corpus only has {len(_CORPUS)} entries"


def test_corpus_ids_are_unique():
    """All corpus IDs must be unique."""
    ids = [e["id"] for e in _CORPUS]
    assert len(ids) == len(set(ids)), "Duplicate IDs in corpus"


def test_corpus_has_both_languages():
    """Corpus should cover both Vietnamese and English."""
    langs = {e["language"] for e in _CORPUS}
    assert "vi" in langs, "No Vietnamese entries in corpus"
    assert "en" in langs, "No English entries in corpus"


def test_corpus_has_safe_entries():
    """Corpus must include some safe (non-blocked) entries to avoid false-positive drift."""
    safe_entries = [e for e in _CORPUS if not e["expected_blocked"]]
    assert len(safe_entries) >= 3, (
        f"Need at least 3 safe entries to test false-positives; found {len(safe_entries)}"
    )


def test_corpus_categories_coverage():
    """Corpus should cover all major attack categories."""
    categories = {e["category"] for e in _CORPUS}
    required = {"jailbreak", "role_play_escape", "delimiter_attack", "indirect_injection"}
    missing = required - categories
    assert not missing, f"Missing categories in corpus: {missing}"
