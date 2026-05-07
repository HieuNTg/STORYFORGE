"""Behavior tests for L1 character & voice modules.

Covers:
  - character_generator: generate_characters, extract_character_states
  - character_memory_bank: extract_emotional_memories, format_memories_for_prompt, merge_memory_banks
  - character_secret_tracker: SecretRegistry, initialize_secrets, check_secret_reveal, audit_secrets
  - character_voice_profiler: generate_voice_profiles, format_voice_profiles_for_prompt, update_character_speech_patterns
"""

import pytest
from unittest.mock import MagicMock, patch

from models.schemas import Character
from pipeline.layer1_story.character_memory_bank import (
    CharacterMemoryBank,
    EmotionalMemory,
    extract_emotional_memories,
    format_memories_for_prompt,
    merge_memory_banks,
)
from pipeline.layer1_story.character_secret_tracker import (
    SecretRegistry,
    audit_secrets,
    check_secret_reveal,
    format_secret_warning,
    get_secret_enforcement_prompt,
    initialize_secrets,
)
from pipeline.layer1_story.character_voice_profiler import (
    format_voice_profiles_for_prompt,
    generate_voice_profiles,
    update_character_speech_patterns,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm(return_value):
    llm = MagicMock()
    llm.generate_json.return_value = return_value
    return llm


def _char(name="Nguyễn Minh Tuấn", role="chính", personality="can đảm, thẳng thắn", **kw):
    return Character(name=name, role=role, personality=personality, **kw)


# ---------------------------------------------------------------------------
# character_generator — generate_characters
# ---------------------------------------------------------------------------

class TestGenerateCharacters:
    def test_happy_path_returns_character_list(self):
        from pipeline.layer1_story.character_generator import generate_characters

        llm = _make_llm({
            "characters": [
                {
                    "name": "Trần Văn Lực",
                    "role": "chính",
                    "personality": "dũng cảm, trung thành",
                    "relationships": ["Lý Hoa: bạn thân"],
                }
            ]
        })
        result = generate_characters(llm, title="Kiếm Hiệp", genre="tiên hiệp", idea="Một chàng trai nghèo luyện đạo")
        assert len(result) == 1
        assert result[0].name == "Trần Văn Lực"
        assert result[0].role == "chính"
        assert isinstance(result[0].relationships, list)

    def test_relationship_normalization_string(self):
        from pipeline.layer1_story.character_generator import generate_characters

        llm = _make_llm({
            "characters": [
                {
                    "name": "Lý Hoa",
                    "role": "phụ",
                    "personality": "dịu dàng",
                    "relationships": "Minh: tình nhân, Tuấn: kẻ thù",
                }
            ]
        })
        result = generate_characters(llm, title="T", genre="ngôn tình", idea="I")
        assert len(result[0].relationships) == 2

    def test_relationship_normalization_list_of_dicts(self):
        from pipeline.layer1_story.character_generator import generate_characters

        llm = _make_llm({
            "characters": [
                {
                    "name": "Vũ Khắc Hào",
                    "role": "phản diện",
                    "personality": "tàn nhẫn",
                    "relationships": [
                        {"character": "Minh", "description": "kẻ thù không đội trời chung"},
                        {"character": "Lan", "relation": "tình cũ"},
                    ],
                }
            ]
        })
        result = generate_characters(llm, title="T", genre="hành động", idea="I")
        rels = result[0].relationships
        assert len(rels) == 2
        assert "Minh" in rels[0]

    def test_relationship_normalization_none(self):
        from pipeline.layer1_story.character_generator import generate_characters

        llm = _make_llm({
            "characters": [
                {"name": "Cô Đơn", "role": "phụ", "personality": "lặng lẽ", "relationships": None}
            ]
        })
        result = generate_characters(llm, title="T", genre="drama", idea="I")
        assert result[0].relationships == []

    def test_malformed_character_skipped(self):
        """Characters missing required 'name' field should be skipped without crash."""
        from pipeline.layer1_story.character_generator import generate_characters

        llm = _make_llm({
            "characters": [
                {"role": "phụ", "personality": "ok"},   # missing name
                {"name": "Nguyễn An", "role": "chính", "personality": "tốt bụng"},
            ]
        })
        result = generate_characters(llm, title="T", genre="drama", idea="I")
        assert len(result) == 1
        assert result[0].name == "Nguyễn An"

    def test_non_dict_integer_entry_skipped(self):
        """Integer entries (not str, not dict) are skipped without crash."""
        from pipeline.layer1_story.character_generator import generate_characters

        llm = _make_llm({"characters": [42, {"name": "Valid", "role": "chính", "personality": "x"}]})
        result = generate_characters(llm, title="T", genre="drama", idea="I")
        assert len(result) == 1
        assert result[0].name == "Valid"

    def test_flat_string_list_coerced_to_characters(self):
        """LLM returns flat string list — must not crash; each string becomes a Character with role='supporting'."""
        from pipeline.layer1_story.character_generator import generate_characters

        llm = _make_llm({"characters": ["Alice", "Bob"]})
        result = generate_characters(llm, title="T", genre="drama", idea="I")
        assert len(result) == 2
        assert all(c.role == "supporting" for c in result)
        assert {c.name for c in result} == {"Alice", "Bob"}

    def test_empty_characters_list(self):
        from pipeline.layer1_story.character_generator import generate_characters

        llm = _make_llm({"characters": []})
        result = generate_characters(llm, title="T", genre="drama", idea="I")
        assert result == []

    def test_llm_failure_propagates(self):
        from pipeline.layer1_story.character_generator import generate_characters

        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("LLM down")
        with pytest.raises(RuntimeError, match="LLM down"):
            generate_characters(llm, title="T", genre="drama", idea="I")

    def test_personality_fallback_from_traits(self):
        from pipeline.layer1_story.character_generator import generate_characters

        llm = _make_llm({
            "characters": [
                {"name": "Bí Ẩn", "role": "phụ", "traits": "lạnh lùng, thần bí"}
            ]
        })
        result = generate_characters(llm, title="T", genre="kinh dị", idea="I")
        assert result[0].personality == "lạnh lùng, thần bí"

    def test_title_wrapped_in_user_input_tags(self):
        """wrap_user_input is called; LLM prompt should contain the title within tags."""
        from pipeline.layer1_story.character_generator import generate_characters

        llm = _make_llm({"characters": []})
        generate_characters(llm, title="Cô Gái Rồng Lửa", genre="fantasy", idea="Idea here")
        call_kwargs = llm.generate_json.call_args
        prompt_text = call_kwargs[1].get("user_prompt") or call_kwargs[0][1]
        assert "<user_input>" in prompt_text
        assert "Cô Gái Rồng Lửa" in prompt_text


# ---------------------------------------------------------------------------
# character_generator — extract_character_states
# ---------------------------------------------------------------------------

class TestExtractCharacterStates:
    def test_happy_path_returns_states(self):
        from pipeline.layer1_story.character_generator import extract_character_states

        llm = _make_llm({
            "character_states": [
                {"name": "Minh", "mood": "tức giận", "arc_position": "crisis"},
            ]
        })
        chars = [_char(name="Minh")]
        result = extract_character_states(llm, content="Minh đánh Tuấn.", characters=chars)
        assert len(result) == 1
        assert result[0].name == "Minh"
        assert result[0].mood == "tức giận"

    def test_malformed_state_skipped(self):
        from pipeline.layer1_story.character_generator import extract_character_states

        llm = _make_llm({
            "character_states": [
                {"mood": "buồn"},  # missing 'name'
                {"name": "Lan", "mood": "vui"},
            ]
        })
        result = extract_character_states(llm, content="...", characters=[_char(name="Lan")])
        assert len(result) == 1
        assert result[0].name == "Lan"

    def test_empty_states_returns_empty_list(self):
        from pipeline.layer1_story.character_generator import extract_character_states

        llm = _make_llm({"character_states": []})
        result = extract_character_states(llm, content="...", characters=[])
        assert result == []


# ---------------------------------------------------------------------------
# character_memory_bank — extract_emotional_memories
# ---------------------------------------------------------------------------

class TestExtractEmotionalMemories:
    @patch("services.text_utils.excerpt_text", side_effect=lambda t, **kw: t)
    def test_happy_path_returns_banks(self, _mock_excerpt):
        llm = _make_llm({
            "characters": [
                {
                    "character_name": "Phương Linh",
                    "emotional_memories": [
                        {
                            "chapter": 3,
                            "trigger_event": "bị phản bội",
                            "emotion": "đau lòng",
                            "intensity": 0.9,
                            "target_character": "Hùng",
                            "resolved": False,
                        }
                    ],
                    "persistent_mood_modifiers": ["mất niềm tin"],
                    "relationship_emotions": {"Hùng": "thù hận"},
                }
            ]
        })
        result = extract_emotional_memories(llm, "Phương Linh bị phản bội.", ["Phương Linh"], chapter_num=3)
        assert "Phương Linh" in result
        bank = result["Phương Linh"]
        assert len(bank.emotional_memories) == 1
        assert bank.emotional_memories[0].emotion == "đau lòng"
        assert bank.emotional_memories[0].intensity == 0.9
        assert bank.relationship_emotions["Hùng"] == "thù hận"

    @patch("services.text_utils.excerpt_text", side_effect=lambda t, **kw: t)
    def test_accepts_character_objects(self, _):
        llm = _make_llm({"characters": [
            {"character_name": "Minh", "emotional_memories": [], "persistent_mood_modifiers": [], "relationship_emotions": {}}
        ]})
        char = _char(name="Minh")
        result = extract_emotional_memories(llm, "text", [char], chapter_num=1)
        assert "Minh" in result

    def test_empty_character_list_returns_empty(self):
        llm = _make_llm({})
        result = extract_emotional_memories(llm, "text", [], chapter_num=1)
        assert result == {}
        llm.generate_json.assert_not_called()

    @patch("services.text_utils.excerpt_text", side_effect=lambda t, **kw: t)
    def test_llm_returns_list_directly(self, _):
        """LLM may return a list instead of {characters: [...]}."""
        llm = _make_llm([
            {
                "character_name": "Hùng",
                "emotional_memories": [],
                "persistent_mood_modifiers": [],
                "relationship_emotions": {},
            }
        ])
        result = extract_emotional_memories(llm, "text", ["Hùng"], chapter_num=2)
        assert "Hùng" in result

    @patch("services.text_utils.excerpt_text", side_effect=lambda t, **kw: t)
    def test_malformed_memory_entry_skips_whole_character(self, _):
        """When ANY memory in a bank is malformed, the entire character bank is skipped."""
        llm = _make_llm({"characters": [
            {
                "character_name": "Lan",
                "emotional_memories": [
                    {"trigger_event": "x", "emotion": "y", "intensity": 2.5},  # intensity out of range
                ],
                "persistent_mood_modifiers": [],
                "relationship_emotions": {},
            },
            {
                "character_name": "Minh",
                "emotional_memories": [
                    {"chapter": 1, "trigger_event": "ok", "emotion": "vui", "intensity": 0.5, "target_character": "", "resolved": False},
                ],
                "persistent_mood_modifiers": [],
                "relationship_emotions": {},
            },
        ]})
        result = extract_emotional_memories(llm, "text", ["Lan", "Minh"], chapter_num=1)
        # Valid character should still be present
        assert "Minh" in result
        assert len(result["Minh"].emotional_memories) == 1
        # Malformed character is dropped entirely
        assert "Lan" not in result


# ---------------------------------------------------------------------------
# character_memory_bank — format_memories_for_prompt
# ---------------------------------------------------------------------------

class TestFormatMemoriesForPrompt:
    def test_empty_banks_returns_fallback(self):
        out = format_memories_for_prompt({})
        assert "Không có" in out

    def test_single_memory_formatted(self):
        bank = CharacterMemoryBank(
            character_name="Tuấn",
            emotional_memories=[
                EmotionalMemory(chapter=2, trigger_event="gặp kẻ thù", emotion="lo sợ", intensity=0.7, target_character="Ác Nhân")
            ],
        )
        out = format_memories_for_prompt({"Tuấn": bank})
        assert "Tuấn" in out
        assert "lo sợ" in out
        assert "Ác Nhân" in out

    def test_persistent_mood_modifier_included(self):
        bank = CharacterMemoryBank(
            character_name="Mai",
            emotional_memories=[],
            persistent_mood_modifiers=["mang nỗi oan khuất"],
        )
        out = format_memories_for_prompt({"Mai": bank})
        assert "mang nỗi oan khuất" in out

    def test_last_n_limits_memories(self):
        memories = [
            EmotionalMemory(chapter=i, trigger_event=f"e{i}", emotion="buồn", intensity=0.5)
            for i in range(1, 6)
        ]
        bank = CharacterMemoryBank(character_name="Long", emotional_memories=memories)
        out = format_memories_for_prompt({"Long": bank}, last_n=2)
        # Only the last 2 trigger events should appear
        assert "e4" in out
        assert "e5" in out
        assert "e1" not in out


# ---------------------------------------------------------------------------
# character_memory_bank — merge_memory_banks
# ---------------------------------------------------------------------------

class TestMergeMemoryBanks:
    def _bank(self, name, emotions=None, mods=None, rel=None):
        return CharacterMemoryBank(
            character_name=name,
            emotional_memories=emotions or [],
            persistent_mood_modifiers=mods or [],
            relationship_emotions=rel or {},
        )

    def _mem(self, ch=1):
        return EmotionalMemory(chapter=ch, trigger_event="t", emotion="e", intensity=0.5)

    def test_new_character_added(self):
        existing = {}
        new = {"Minh": self._bank("Minh", emotions=[self._mem()])}
        result = merge_memory_banks(existing, new)
        assert "Minh" in result

    def test_existing_memories_extended(self):
        existing = {"Lan": self._bank("Lan", emotions=[self._mem(1)])}
        new = {"Lan": self._bank("Lan", emotions=[self._mem(2)])}
        result = merge_memory_banks(existing, new)
        assert len(result["Lan"].emotional_memories) == 2

    def test_mood_modifiers_deduplicated(self):
        existing = {"A": self._bank("A", mods=["mệt mỏi"])}
        new = {"A": self._bank("A", mods=["mệt mỏi", "cô đơn"])}
        result = merge_memory_banks(existing, new)
        mods = result["A"].persistent_mood_modifiers
        assert mods.count("mệt mỏi") == 1
        assert "cô đơn" in mods

    def test_relationship_emotions_overwritten_with_latest(self):
        existing = {"B": self._bank("B", rel={"X": "bạn"})}
        new = {"B": self._bank("B", rel={"X": "kẻ thù"})}
        result = merge_memory_banks(existing, new)
        assert result["B"].relationship_emotions["X"] == "kẻ thù"


# ---------------------------------------------------------------------------
# character_secret_tracker — SecretRegistry
# ---------------------------------------------------------------------------

class TestSecretRegistry:
    def test_add_and_get_unrevealed(self):
        reg = SecretRegistry()
        reg.add_secret("Minh", "Minh là hoàng tử giả mạo", reveal_chapter=10)
        unrevealed = reg.get_unrevealed()
        assert len(unrevealed) == 1
        assert unrevealed[0].character == "Minh"

    def test_mark_revealed_returns_true(self):
        reg = SecretRegistry()
        reg.add_secret("Lan", "Lan có phép thuật")
        ok = reg.mark_revealed("Lan", chapter=5, revealed_to=["Tuấn"])
        assert ok is True
        assert reg.secrets[0].actual_reveal == 5
        assert reg.secrets[0].revealed_to == ["Tuấn"]

    def test_mark_revealed_unknown_character_returns_false(self):
        reg = SecretRegistry()
        result = reg.mark_revealed("Nobody", chapter=1)
        assert result is False

    def test_get_overdue(self):
        reg = SecretRegistry()
        reg.add_secret("A", "secret A", reveal_chapter=3)
        reg.add_secret("B", "secret B", reveal_chapter=10)
        overdue = reg.get_overdue(current_chapter=7)
        assert len(overdue) == 1
        assert overdue[0].character == "A"

    def test_add_hint_recorded(self):
        reg = SecretRegistry()
        reg.add_secret("C", "secret C")
        reg.add_hint("C", chapter=2, hint="một gợi ý nhỏ")
        assert len(reg.secrets[0].partial_hints) == 1
        assert reg.secrets[0].partial_hints[0]["hint"] == "một gợi ý nhỏ"

    def test_get_unrevealed_by_chapter_filters_deadline(self):
        reg = SecretRegistry()
        reg.add_secret("X", "sẽ tiết lộ sớm", reveal_chapter=2)
        reg.add_secret("Y", "tiết lộ muộn", reveal_chapter=15)
        # At chapter 5, secrets with reveal_chapter < 5 should be filtered out
        result = reg.get_unrevealed(by_chapter=5)
        names = [s.character for s in result]
        assert "Y" in names
        assert "X" not in names


# ---------------------------------------------------------------------------
# character_secret_tracker — initialize_secrets
# ---------------------------------------------------------------------------

class TestInitializeSecrets:
    def test_secret_extracted_from_character(self):
        char = _char(name="Hào", secret="Hào là điệp viên (reveal ch 7)")
        reg = initialize_secrets([char])
        assert len(reg.secrets) == 1
        assert reg.secrets[0].character == "Hào"
        assert reg.secrets[0].reveal_chapter == 7

    def test_character_without_secret_skipped(self):
        char = _char(name="Bình", secret="")
        reg = initialize_secrets([char])
        assert len(reg.secrets) == 0

    def test_vietnamese_reveal_tag_parsed(self):
        char = _char(name="Hoa", secret="Hoa là tiên nữ (tiết lộ ch 12)")
        reg = initialize_secrets([char])
        assert reg.secrets[0].reveal_chapter == 12

    def test_multiple_characters(self):
        chars = [
            _char(name="A", secret="bí mật A"),
            _char(name="B", secret=""),
            _char(name="C", secret="bí mật C (reveal ch 5)"),
        ]
        reg = initialize_secrets(chars)
        assert len(reg.secrets) == 2


# ---------------------------------------------------------------------------
# character_secret_tracker — check_secret_reveal
# ---------------------------------------------------------------------------

class TestCheckSecretReveal:
    def _registry_with_secret(self, char="Tuấn", reveal_chapter=None):
        reg = SecretRegistry()
        reg.add_secret(char, f"bí mật của {char}", reveal_chapter=reveal_chapter)
        return reg

    def test_no_unrevealed_secrets_skips_llm(self):
        reg = SecretRegistry()  # empty
        llm = MagicMock()
        result = check_secret_reveal(llm, "content", 1, reg)
        llm.generate_json.assert_not_called()
        assert result == {"reveals": [], "hints": [], "premature": []}

    def test_reveal_updates_registry(self):
        reg = self._registry_with_secret("Lan")
        llm = _make_llm({"reveals": [{"character": "Lan", "revealed_to": ["Minh"]}], "hints": []})
        result = check_secret_reveal(llm, "Lan tiết lộ bí mật.", 3, reg)
        assert len(result["reveals"]) == 1
        assert reg.secrets[0].actual_reveal == 3

    def test_premature_reveal_detected(self):
        reg = self._registry_with_secret("Hùng", reveal_chapter=10)
        llm = _make_llm({"reveals": [{"character": "Hùng", "revealed_to": []}], "hints": []})
        result = check_secret_reveal(llm, "Hùng lỡ miệng.", 4, reg)
        assert len(result["premature"]) == 1
        assert result["premature"][0]["planned_chapter"] == 10

    def test_hints_recorded(self):
        reg = self._registry_with_secret("Mai")
        llm = _make_llm({"reveals": [], "hints": [{"character": "Mai", "hint": "một dấu hiệu bí ẩn"}]})
        result = check_secret_reveal(llm, "text", 2, reg)
        assert len(result["hints"]) == 1
        assert reg.secrets[0].partial_hints[0]["hint"] == "một dấu hiệu bí ẩn"


# ---------------------------------------------------------------------------
# character_secret_tracker — audit_secrets & format helpers
# ---------------------------------------------------------------------------

class TestAuditAndFormat:
    def test_audit_counts_correctly(self):
        reg = SecretRegistry()
        reg.add_secret("A", "s1", reveal_chapter=3)
        reg.add_secret("B", "s2", reveal_chapter=8)
        reg.mark_revealed("A", chapter=5)  # late reveal (> planned)
        # A revealed at 5 but planned at 3 → not premature (5 > 3 means it's LATE not premature)
        audit = audit_secrets(reg, final_chapter=10)
        assert audit["total"] == 2
        assert audit["revealed"] == 1
        assert audit["unrevealed"] == 1

    def test_audit_detects_premature(self):
        reg = SecretRegistry()
        reg.add_secret("C", "secret", reveal_chapter=10)
        reg.mark_revealed("C", chapter=3)  # premature
        audit = audit_secrets(reg, final_chapter=5)
        assert audit["premature"] == 1

    def test_format_secret_warning_premature(self):
        check_result = {
            "premature": [{"character": "X", "actual_chapter": 2, "planned_chapter": 8}],
            "reveals": [],
            "hints": [],
        }
        out = format_secret_warning(check_result, chapter_number=2)
        assert "TIẾT LỘ SỚM" in out
        assert "X" in out

    def test_get_secret_enforcement_prompt_empty_when_no_secrets(self):
        reg = SecretRegistry()
        out = get_secret_enforcement_prompt(reg, chapter_number=1)
        assert out == ""

    def test_get_secret_enforcement_prompt_includes_secret(self):
        reg = SecretRegistry()
        reg.add_secret("Diệp", "Diệp là sát thủ bí ẩn", reveal_chapter=20)
        out = get_secret_enforcement_prompt(reg, chapter_number=5)
        assert "Diệp" in out
        assert "KHÔNG" in out  # enforcement language


# ---------------------------------------------------------------------------
# character_voice_profiler — generate_voice_profiles
# ---------------------------------------------------------------------------

class TestGenerateVoiceProfiles:
    def _profile(self, name="Minh"):
        return {
            "name": name,
            "vocabulary_level": "formal",
            "sentence_style": "long_flowing",
            "verbal_tics": ["hay nói 'thật ra là...'"],
            "emotional_expression": {"anger": "lạnh lùng im lặng", "joy": "mỉm cười nhẹ", "sadness": "cúi mặt"},
            "dialogue_examples": ["Thật ra là, chúng ta không có lựa chọn nào khác."],
        }

    def test_happy_path_list_response(self):
        chars = [_char(name="Nguyễn Tuấn")]
        llm = _make_llm([self._profile("Nguyễn Tuấn")])
        result = generate_voice_profiles(llm, chars, genre="tiên hiệp")
        assert len(result) == 1
        assert result[0]["name"] == "Nguyễn Tuấn"
        assert result[0]["vocabulary_level"] == "formal"

    def test_dict_wrapper_profiles_key(self):
        chars = [_char(name="Lan")]
        llm = _make_llm({"profiles": [self._profile("Lan")]})
        result = generate_voice_profiles(llm, chars, genre="ngôn tình")
        assert len(result) == 1

    def test_dict_wrapper_characters_key(self):
        chars = [_char(name="Hoa")]
        llm = _make_llm({"characters": [self._profile("Hoa")]})
        result = generate_voice_profiles(llm, chars, genre="drama")
        assert len(result) == 1

    def test_single_profile_dict_no_wrapper(self):
        """When LLM returns a single profile dict directly (1 character)."""
        chars = [_char(name="Solo")]
        llm = _make_llm(self._profile("Solo"))
        result = generate_voice_profiles(llm, chars, genre="fantasy")
        assert len(result) == 1
        assert result[0]["name"] == "Solo"

    def test_single_profile_no_name_inferred(self):
        chars = [_char(name="InferMe")]
        profile = self._profile("InferMe")
        del profile["name"]
        llm = _make_llm(profile)
        result = generate_voice_profiles(llm, chars, genre="fantasy")
        assert len(result) == 1
        assert result[0]["name"] == "InferMe"

    def test_empty_characters_returns_empty(self):
        llm = MagicMock()
        result = generate_voice_profiles(llm, [], genre="fantasy")
        assert result == []
        llm.generate_json.assert_not_called()

    def test_llm_failure_returns_empty_list(self):
        llm = MagicMock()
        llm.generate_json.side_effect = Exception("timeout")
        result = generate_voice_profiles(llm, [_char()], genre="fantasy")
        assert result == []

    def test_legacy_alias_dialogue_example_canonicalised(self):
        """'dialogue_example' alias should be mapped to 'dialogue_examples'."""
        chars = [_char(name="Ali")]
        profile = {
            "name": "Ali",
            "vocabulary_level": "casual",
            "sentence_style": "short_punchy",
            "verbal_tics": [],
            "emotional_expression": {},
            "dialogue_example": ["câu ví dụ"],  # legacy key
        }
        llm = _make_llm([profile])
        result = generate_voice_profiles(llm, chars, genre="drama")
        assert "dialogue_examples" in result[0]
        assert "dialogue_example" not in result[0]

    def test_non_dict_profiles_dropped(self):
        chars = [_char(name="A"), _char(name="B")]
        llm = _make_llm([self._profile("A"), "bad entry"])
        result = generate_voice_profiles(llm, chars, genre="drama")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# character_voice_profiler — format_voice_profiles_for_prompt
# ---------------------------------------------------------------------------

class TestFormatVoiceProfilesForPrompt:
    def test_empty_returns_empty_string(self):
        assert format_voice_profiles_for_prompt([]) == ""

    def test_contains_character_name_and_vocal_info(self):
        profile = {
            "name": "Bảo",
            "vocabulary_level": "archaic",
            "sentence_style": "poetic",
            "verbal_tics": ["hay thêm 'vậy đó'"],
            "emotional_expression": {"anger": "quát lớn"},
            "dialogue_examples": ["Ta sẽ không tha thứ."],
        }
        out = format_voice_profiles_for_prompt([profile])
        assert "Bảo" in out
        assert "archaic" in out
        assert "vậy đó" in out
        assert "quát lớn" in out

    def test_dialogue_example_alias_handled(self):
        profile = {
            "name": "Cúc",
            "vocabulary_level": "casual",
            "sentence_style": "fragmented",
            "verbal_tics": [],
            "emotional_expression": {},
            "dialogue_example": ["Ừ thì... vậy đó."],  # legacy alias
        }
        out = format_voice_profiles_for_prompt([profile])
        assert "Cúc" in out


# ---------------------------------------------------------------------------
# character_voice_profiler — update_character_speech_patterns
# ---------------------------------------------------------------------------

class TestUpdateCharacterSpeechPatterns:
    def test_speech_pattern_updated_on_match(self):
        char = _char(name="Đức")
        profiles = [
            {
                "name": "Đức",
                "vocabulary_level": "formal",
                "sentence_style": "long_flowing",
                "verbal_tics": ["thường dùng ẩn dụ"],
                "emotional_expression": {"anger": "thở dài"},
                "dialogue_examples": ["Điều đó không thể thay đổi."],
            }
        ]
        update_character_speech_patterns([char], profiles)
        assert "formal" in char.speech_pattern
        assert "long_flowing" in char.speech_pattern

    def test_case_insensitive_name_match(self):
        char = _char(name="nguyễn hoa")
        profiles = [{"name": "Nguyễn Hoa", "vocabulary_level": "casual", "sentence_style": "short_punchy",
                     "verbal_tics": [], "emotional_expression": {}, "dialogue_examples": []}]
        update_character_speech_patterns([char], profiles)
        assert "casual" in char.speech_pattern

    def test_unmatched_character_unchanged(self):
        char = _char(name="Vô Danh")
        char.speech_pattern = "original"
        update_character_speech_patterns([char], [])
        assert char.speech_pattern == "original"

    def test_multiple_characters_updated(self):
        chars = [_char(name="A"), _char(name="B")]
        profiles = [
            {"name": "A", "vocabulary_level": "formal", "sentence_style": "poetic",
             "verbal_tics": [], "emotional_expression": {}, "dialogue_examples": []},
            {"name": "B", "vocabulary_level": "casual", "sentence_style": "fragmented",
             "verbal_tics": [], "emotional_expression": {}, "dialogue_examples": []},
        ]
        update_character_speech_patterns(chars, profiles)
        assert "formal" in chars[0].speech_pattern
        assert "casual" in chars[1].speech_pattern
