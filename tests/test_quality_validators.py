"""Tests for quality_validators: world rules + dialogue voice validation."""

from unittest.mock import MagicMock
from models.schemas import StoryContext
from pipeline.layer1_story.quality_validators import validate_world_rules, validate_dialogue_voice
from pipeline.layer1_story.chapter_writer import _append_consistency_context


class TestValidateWorldRules:
    def test_returns_violations(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "violations": ["Nhân vật dùng phép bay nhưng quy tắc cấm bay"]
        }
        result = validate_world_rules(llm, "content", ["Không ai được bay"], 3)
        assert len(result) == 1
        assert "bay" in result[0]

    def test_empty_rules_skips_llm(self):
        llm = MagicMock()
        result = validate_world_rules(llm, "content", [], 1)
        assert result == []
        llm.generate_json.assert_not_called()

    def test_no_violations(self):
        llm = MagicMock()
        llm.generate_json.return_value = {"violations": []}
        result = validate_world_rules(llm, "content", ["rule1"], 1)
        assert result == []

    def test_filters_empty_strings(self):
        llm = MagicMock()
        llm.generate_json.return_value = {"violations": ["real issue", "", None]}
        result = validate_world_rules(llm, "content", ["rule1"], 1)
        assert result == ["real issue"]

    def test_llm_failure_propagates(self):
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("API down")
        try:
            validate_world_rules(llm, "content", ["rule1"], 1)
            assert False, "Should raise"
        except RuntimeError:
            pass


class TestValidateDialogueVoice:
    def test_returns_warnings(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "warnings": ["Minh: dùng từ quá học thuật, không đúng vocab level 'bình dân'"]
        }
        profiles = [{"name": "Minh", "vocabulary_level": "bình dân", "sentence_style": "ngắn gọn"}]
        result = validate_dialogue_voice(llm, "content", profiles, 3)
        assert len(result) == 1
        assert "Minh" in result[0]

    def test_empty_profiles_skips_llm(self):
        llm = MagicMock()
        result = validate_dialogue_voice(llm, "content", [], 1)
        assert result == []
        llm.generate_json.assert_not_called()

    def test_no_warnings(self):
        llm = MagicMock()
        llm.generate_json.return_value = {"warnings": []}
        profiles = [{"name": "A", "vocabulary_level": "cao"}]
        result = validate_dialogue_voice(llm, "content", profiles, 1)
        assert result == []

    def test_filters_empty_strings(self):
        llm = MagicMock()
        llm.generate_json.return_value = {"warnings": ["real warning", ""]}
        profiles = [{"name": "A", "vocabulary_level": "cao"}]
        result = validate_dialogue_voice(llm, "content", profiles, 1)
        assert result == ["real warning"]

    def test_llm_failure_propagates(self):
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("API down")
        profiles = [{"name": "A", "vocabulary_level": "cao"}]
        try:
            validate_dialogue_voice(llm, "content", profiles, 1)
            assert False, "Should raise"
        except RuntimeError:
            pass


class TestAppendConsistencyContextPhase2:
    def _context(self, **kwargs):
        return StoryContext(total_chapters=20, **kwargs)

    def test_world_violations_injected(self):
        ctx = self._context(world_rule_violations=["Vi phạm quy tắc cấm bay"])
        parts = []
        _append_consistency_context(parts, ctx)
        assert any("VI PHẠM QUY TẮC THẾ GIỚI" in p for p in parts)
        assert any("PHẢI" in p for p in parts)

    def test_world_violations_capped_at_5(self):
        ctx = self._context(world_rule_violations=[f"v{i}" for i in range(10)])
        parts = []
        _append_consistency_context(parts, ctx)
        viol_block = [p for p in parts if "QUY TẮC THẾ GIỚI" in p][0]
        assert viol_block.count("- v") == 5

    def test_dialogue_warnings_injected(self):
        ctx = self._context(dialogue_voice_warnings=["Minh: giọng quá trang trọng"])
        parts = []
        _append_consistency_context(parts, ctx)
        assert any("GIỌNG NÓI NHÂN VẬT" in p for p in parts)

    def test_dialogue_warnings_capped_at_5(self):
        ctx = self._context(dialogue_voice_warnings=[f"w{i}" for i in range(8)])
        parts = []
        _append_consistency_context(parts, ctx)
        voice_block = [p for p in parts if "GIỌNG NÓI" in p][0]
        assert voice_block.count("- w") == 5

    def test_no_injection_when_empty(self):
        ctx = self._context()
        parts = []
        _append_consistency_context(parts, ctx)
        assert not any("QUY TẮC THẾ GIỚI" in p for p in parts)
        assert not any("GIỌNG NÓI" in p for p in parts)
