"""Unit tests for services/simulation_continue_service.py (previously untested).

The LLM is a MagicMock returning canned JSON, so the formatting, language
pinning, sender clamping, and lane-contract prompt are exercised without
network calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from models.schemas import TranscriptTurn
from services.simulation_continue_service import (
    CONTINUE_SYSTEM_PROMPT,
    _format_chars,
    _format_history,
    continue_dialogue,
)


def _chars():
    return [
        {"name": "Hải Long", "role": "protagonist"},
        {"name": "Mộc Lan", "role": "rival"},
    ]


def _llm(payload: dict | None = None) -> MagicMock:
    llm = MagicMock()
    llm.generate.return_value = json.dumps(
        payload
        or {
            "senderId": "Hải Long",
            "senderName": "Hải Long",
            "emotion": "phẫn nộ",
            "actionDetails": "đập bàn",
            "speech": "Đủ rồi!",
        },
        ensure_ascii=False,
    )
    return llm


class TestFormatChars:
    def test_name_and_role_lines(self):
        out = _format_chars(_chars())
        assert out == "- Hải Long (protagonist)\n- Mộc Lan (rival)"

    def test_sendername_fallback_and_skip_non_dicts(self):
        out = _format_chars(["chuỗi rác", {"senderName": "Vô Danh"}])
        assert out == "- Vô Danh"

    def test_caps_at_ten_characters(self):
        out = _format_chars([{"name": f"NV{i}"} for i in range(15)])
        assert len(out.splitlines()) == 10

    def test_empty_list_placeholder(self):
        assert _format_chars([]) == "- (không có)"


class TestFormatHistory:
    def test_mixes_models_and_dicts(self):
        turn = TranscriptTurn(
            id="t1",
            senderId="Hải Long",
            senderName="Hải Long",
            emotion="giận",
            actionDetails="đập bàn",
            speech="Đủ rồi!",
        )
        out = _format_history([turn, {"senderName": "Mộc Lan", "speech": "Vậy sao?"}])
        assert out.splitlines() == [
            "[Hải Long] (giận) *đập bàn* « Đủ rồi! »",
            "[Mộc Lan] « Vậy sao? »",
        ]

    def test_keeps_only_last_six_turns(self):
        history = [{"senderName": f"NV{i}", "speech": "..."} for i in range(10)]
        out = _format_history(history)
        assert len(out.splitlines()) == 6
        assert out.splitlines()[0].startswith("[NV4]")

    def test_skips_unknown_entry_types(self):
        assert _format_history(["rác", 42]) == "(chưa có)"

    def test_empty_history_placeholder(self):
        assert _format_history([]) == "(chưa có)"


class TestContinueDialogue:
    def test_returns_validated_turn_with_generated_id(self):
        turn = continue_dialogue(_llm(), _chars(), [], "tranh đoạt bí kíp")
        assert isinstance(turn, TranscriptTurn)
        assert turn.id.startswith("t-cont-")
        assert turn.senderName == "Hải Long"
        assert turn.speech == "Đủ rồi!"

    def test_empty_topic_rejected(self):
        with pytest.raises(ValueError, match="topic"):
            continue_dialogue(_llm(), _chars(), [], "   ")

    def test_empty_characters_rejected(self):
        with pytest.raises(ValueError, match="characters"):
            continue_dialogue(_llm(), [], [], "chủ đề")

    def test_unknown_sender_clamped_to_first_character(self):
        llm = _llm({"senderId": "Kẻ Lạ", "senderName": "Kẻ Lạ", "speech": "Ta là ai?"})
        turn = continue_dialogue(llm, _chars(), [], "chủ đề")
        assert turn.senderName == "Hải Long"
        assert turn.senderId == "Hải Long"

    def test_known_sender_preserved_and_id_mirrored(self):
        llm = _llm({"senderName": "Mộc Lan", "speech": "Vậy sao?"})
        turn = continue_dialogue(llm, _chars(), [], "chủ đề")
        assert turn.senderName == "Mộc Lan"
        assert turn.senderId == "Mộc Lan"

    def test_braces_in_topic_do_not_break_formatting(self):
        llm = _llm()
        turn = continue_dialogue(llm, _chars(), [], "luật {cấm} bí mật")
        assert isinstance(turn, TranscriptTurn)
        user_prompt = llm.generate.call_args.kwargs["user_prompt"]
        assert "luật {cấm} bí mật" in user_prompt

    def test_vietnamese_default_keeps_lane_anchored_system_prompt(self):
        llm = _llm()
        continue_dialogue(llm, _chars(), [], "chủ đề")
        kwargs = llm.generate.call_args.kwargs
        assert kwargs["system_prompt"] == CONTINUE_SYSTEM_PROMPT
        assert "OUTPUT LANGUAGE: Vietnamese (tiếng Việt)" in kwargs["user_prompt"]

    def test_non_vi_language_swaps_system_prompt(self):
        llm = _llm()
        continue_dialogue(llm, _chars(), [], "chủ đề", language="en")
        kwargs = llm.generate.call_args.kwargs
        assert "respond entirely in English" in kwargs["system_prompt"]
        # lane contract survives the swap: simulator never critiques craft
        assert "Do NOT comment on prose style" in kwargs["system_prompt"]
        assert "OUTPUT LANGUAGE: English" in kwargs["user_prompt"]

    def test_llm_call_contract(self):
        llm = _llm()
        continue_dialogue(llm, _chars(), [], "chủ đề", model="custom-model")
        kwargs = llm.generate.call_args.kwargs
        assert kwargs["temperature"] == 0.9
        assert kwargs["json_mode"] is True
        assert kwargs["model_tier"] == "cheap"
        assert kwargs["model"] == "custom-model"

    def test_history_rendered_into_prompt(self):
        llm = _llm()
        history = [{"senderName": "Mộc Lan", "speech": "Ngươi dám?"}]
        continue_dialogue(llm, _chars(), history, "chủ đề")
        user_prompt = llm.generate.call_args.kwargs["user_prompt"]
        assert "[Mộc Lan] « Ngươi dám? »" in user_prompt
