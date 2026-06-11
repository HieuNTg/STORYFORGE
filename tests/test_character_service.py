"""Unit tests for services/character_service.py (previously untested).

The LLM is a MagicMock whose .generate returns canned JSON strings, so the
parse → validate → retry path is exercised without any network calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from services.character_service import (
    _build_character_system_prompt,
    _language_label,
    generate_character,
)


def _valid_payload(name="Hải Long", role="protagonist") -> str:
    return json.dumps(
        {
            "name": name,
            "role": role,
            "traits": {"strength": 80, "wisdom": 60, "agility": 70, "scheme": 30},
            "description": "Cao lớn, chính trực",
            "backstory": "Sinh ra ở làng chài. Mất cha từ nhỏ.",
            "secret": "Mang huyết mạch long tộc",
            "conflict": "Trung thành hay tự do",
        },
        ensure_ascii=False,
    )


class TestLanguageHelpers:
    def test_default_locale_is_vietnamese(self):
        assert _language_label(None) == "Vietnamese (tiếng Việt)"
        assert _language_label("vi") == "Vietnamese (tiếng Việt)"

    def test_known_locale_maps_to_label(self):
        assert _language_label("EN ") == "English"

    def test_unknown_locale_passes_through(self):
        assert _language_label("de") == "de"

    def test_system_prompt_pins_language_and_naming_rule(self):
        prompt = _build_character_system_prompt("en")
        assert "Respond ENTIRELY in English" in prompt
        assert "Vietnamese names by default" in prompt


class TestGenerateCharacter:
    def test_success_forces_name_and_role_from_request(self):
        llm = MagicMock()
        # LLM drifts on name/role — service must force the requested values
        llm.generate.return_value = _valid_payload(name="Tên Khác", role="rival")
        char = generate_character(llm, "Hải Long", "protagonist", "tiên hiệp")
        assert char.name == "Hải Long"
        assert char.role == "protagonist"
        assert char.traits["strength"] == 80
        llm.generate.assert_called_once()

    def test_retry_once_on_bad_json_then_succeed(self):
        llm = MagicMock()
        llm.generate.side_effect = ["không phải json", _valid_payload()]
        char = generate_character(llm, "Hải Long", "protagonist", "tiên hiệp")
        assert char.name == "Hải Long"
        assert llm.generate.call_count == 2
        retry_prompt = llm.generate.call_args_list[1].kwargs["user_prompt"]
        assert "QUAN TRỌNG" in retry_prompt

    def test_raises_after_two_failures(self):
        llm = MagicMock()
        llm.generate.return_value = "vẫn không phải json"
        with pytest.raises(Exception):
            generate_character(llm, "Hải Long", "protagonist", "tiên hiệp")
        assert llm.generate.call_count == 2

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError, match="name"):
            generate_character(MagicMock(), "  ", "protagonist", "tiên hiệp")

    def test_empty_genre_rejected(self):
        with pytest.raises(ValueError, match="genre"):
            generate_character(MagicMock(), "Hải Long", "protagonist", "")

    def test_out_of_range_traits_are_clamped_by_schema(self):
        payload = json.loads(_valid_payload())
        payload["traits"]["strength"] = 150
        payload["traits"]["scheme"] = -10
        llm = MagicMock()
        llm.generate.return_value = json.dumps(payload, ensure_ascii=False)
        char = generate_character(llm, "Hải Long", "protagonist", "tiên hiệp")
        assert char.traits["strength"] == 100
        assert char.traits["scheme"] == 0

    def test_llm_called_with_cheap_tier_and_json_mode(self):
        llm = MagicMock()
        llm.generate.return_value = _valid_payload()
        generate_character(llm, "Hải Long", "protagonist", "tiên hiệp", language="en")
        kwargs = llm.generate.call_args.kwargs
        assert kwargs["model_tier"] == "cheap"
        assert kwargs["json_mode"] is True
        assert "OUTPUT LANGUAGE: English" in kwargs["user_prompt"]
