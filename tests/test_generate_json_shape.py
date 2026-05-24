"""Unit tests for the optional shape validation in ``GenerationMixin.generate_json``.

Covers the ``expect`` / ``list_key`` parameters added at the LLM JSON
boundary so callers don't have to defensively ``isinstance``-check the
parsed result.
"""

import json
from unittest.mock import MagicMock

import pytest

from services.llm.generation import GenerationMixin, _coerce_to_shape


class _Stub(GenerationMixin):
    """Concrete subclass of the mixin with the bits ``generate_json`` calls.

    ``_text_queue`` is a list of strings that ``_generate_json_text`` will
    return one at a time (so we can simulate a first-attempt shape mismatch
    followed by a correct retry).
    """

    def __init__(self, text_queue):
        self._text_queue = list(text_queue)
        # Track how many times the LLM was "called" so shape-retry tests can
        # assert exactly one retry happened.
        self.call_count = 0
        self.generate = MagicMock()  # used by the JSON-repair branch only

    def _generate_json_text(self, *_args, **_kwargs):
        self.call_count += 1
        return self._text_queue.pop(0)


# ---------------------------------------------------------------------------
# _coerce_to_shape — unit tests for the pure helper
# ---------------------------------------------------------------------------

class TestCoerceToShape:
    def test_dict_passthrough(self):
        v, ok = _coerce_to_shape({"a": 1}, "dict", None)
        assert ok and v == {"a": 1}

    def test_dict_wrap_bare_list_with_list_key(self):
        v, ok = _coerce_to_shape([1, 2, 3], "dict", "items")
        assert ok and v == {"items": [1, 2, 3]}

    def test_dict_bare_list_without_list_key_fails(self):
        _, ok = _coerce_to_shape([1, 2], "dict", None)
        assert ok is False

    def test_dict_unwraps_single_element_dict_list(self):
        # LLM drift: returned [{...}] instead of {...}. Unwrap silently.
        v, ok = _coerce_to_shape([{"relationships": [1, 2]}], "dict", None)
        assert ok and v == {"relationships": [1, 2]}

    def test_dict_unwrap_prefers_unwrap_over_list_key_wrap(self):
        # When both rules could apply, unwrap wins (it preserves the dict
        # the LLM clearly intended to return).
        v, ok = _coerce_to_shape([{"a": 1}], "dict", "items")
        assert ok and v == {"a": 1}

    def test_dict_multi_element_list_does_not_unwrap(self):
        # Ambiguous — two dicts can't collapse to one. Falls through to
        # list_key wrap (here: None → fails) so caller can retry.
        _, ok = _coerce_to_shape([{"a": 1}, {"b": 2}], "dict", None)
        assert ok is False

    def test_list_passthrough(self):
        v, ok = _coerce_to_shape([1, 2], "list", None)
        assert ok and v == [1, 2]

    def test_list_extract_from_single_list_valued_key(self):
        v, ok = _coerce_to_shape({"reveals": [1, 2]}, "list", None)
        assert ok and v == [1, 2]

    def test_list_extraction_ambiguous_dict_fails(self):
        # Two list-valued keys — can't disambiguate.
        _, ok = _coerce_to_shape({"a": [1], "b": [2]}, "list", None)
        assert ok is False

    def test_list_dict_without_list_value_fails(self):
        _, ok = _coerce_to_shape({"a": 1}, "list", None)
        assert ok is False


# ---------------------------------------------------------------------------
# generate_json — shape validation integration tests
# ---------------------------------------------------------------------------

class TestGenerateJsonExpectDict:
    def test_happy_path_returns_dict(self):
        stub = _Stub([json.dumps({"reveals": [], "hints": []})])
        result = stub.generate_json("sys", "user", expect="dict")
        assert result == {"reveals": [], "hints": []}
        assert stub.call_count == 1  # no retry needed

    def test_bare_list_auto_wraps_with_list_key(self):
        # Multi-element list — single-dict unwrap doesn't apply, falls
        # through to the list_key wrap branch.
        stub = _Stub([json.dumps([{"character": "Lan"}, {"character": "Hoa"}])])
        result = stub.generate_json(
            "sys", "user", expect="dict", list_key="reveals",
        )
        assert result == {"reveals": [{"character": "Lan"}, {"character": "Hoa"}]}
        assert stub.call_count == 1  # auto-wrap, no retry

    def test_bare_list_without_list_key_triggers_retry_then_raises(self):
        stub = _Stub([
            json.dumps([1, 2, 3]),  # first attempt: bare list
            json.dumps([4, 5, 6]),  # retry: still a list
        ])
        with pytest.raises(ValueError, match="schema mismatch after retry"):
            stub.generate_json("sys", "user", expect="dict")
        assert stub.call_count == 2  # one initial + one shape-retry

    def test_retry_succeeds_after_initial_shape_mismatch(self):
        stub = _Stub([
            json.dumps([1, 2]),                 # bad shape
            json.dumps({"reveals": [1, 2]}),    # retry returns dict
        ])
        result = stub.generate_json("sys", "user", expect="dict")
        assert result == {"reveals": [1, 2]}
        assert stub.call_count == 2


class TestGenerateJsonExpectList:
    def test_happy_path_returns_list(self):
        stub = _Stub([json.dumps([1, 2, 3])])
        result = stub.generate_json("sys", "user", expect="list")
        assert result == [1, 2, 3]
        assert stub.call_count == 1

    def test_single_list_valued_dict_extracted(self):
        stub = _Stub([json.dumps({"items": [1, 2]})])
        result = stub.generate_json("sys", "user", expect="list")
        assert result == [1, 2]
        assert stub.call_count == 1

    def test_unextractable_dict_triggers_retry_then_raises(self):
        stub = _Stub([
            json.dumps({"a": 1, "b": 2}),  # no list values
            json.dumps({"a": 1}),          # retry still bad
        ])
        with pytest.raises(ValueError, match="schema mismatch after retry"):
            stub.generate_json("sys", "user", expect="list")
        assert stub.call_count == 2


class TestGenerateJsonNoExpect:
    """Default ``expect=None`` must preserve legacy behavior exactly."""

    def test_dict_passthrough_unchanged(self):
        stub = _Stub([json.dumps({"a": 1})])
        assert stub.generate_json("sys", "user") == {"a": 1}

    def test_list_passthrough_unchanged(self):
        # Legacy callers that happen to receive a bare list still get it back
        # untouched — opt-in only.
        stub = _Stub([json.dumps([1, 2, 3])])
        assert stub.generate_json("sys", "user") == [1, 2, 3]
