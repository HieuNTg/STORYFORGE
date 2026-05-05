"""Behavior tests for 5 L1 dialogue/style modules.

Modules covered:
- dialogue_attribution_validator
- dialogue_consistency_checker
- dialogue_strategy
- show_dont_tell_enforcer
- pov_drift_detector
"""

from unittest.mock import MagicMock

import pytest

from models.schemas import Character
from pipeline.layer1_story.dialogue_attribution_validator import (
    detect_rapid_exchange,
    extract_dialogue_lines,
    format_attribution_warning,
    get_attribution_enforcement_prompt,
    validate_dialogue_attribution,
)
from pipeline.layer1_story.dialogue_consistency_checker import (
    check_voice_consistency,
    dialogue_consistency_check,
    extract_dialogue_by_character,
    format_voice_warnings,
)
from pipeline.layer1_story.dialogue_strategy import (
    build_dialogue_context,
    get_speech_pattern_reminder,
)
from pipeline.layer1_story.pov_drift_detector import (
    detect_pov_drift,
    detect_pov_type,
    format_pov_warning,
    validate_chapter_pov,
)
from pipeline.layer1_story.show_dont_tell_enforcer import (
    SENSORY_PALETTE,
    audit_chapter_telling,
    build_rewrite_telling_prompt,
    build_show_dont_tell_guidance,
)

# ---------------------------------------------------------------------------
# Vietnamese prose fixtures
# ---------------------------------------------------------------------------

# Clear attribution — each line names the speaker
CLEAR_ATTRIBUTION_PROSE = """
Tuấn nói với giọng trầm: "Chúng ta không thể tiếp tục như vậy nữa."
Linh hỏi nhẹ nhàng: "Tại sao anh lại nghĩ thế?"
Tuấn đáp: "Vì tôi đã mất đi niềm tin từ lâu rồi."
Linh thì thầm: "Nhưng em vẫn tin vào anh, dù thế nào đi nữa."
"""

# Unclear attribution — dialogue blocks with no speaker tags
UNCLEAR_ATTRIBUTION_PROSE = """
"Chúng ta không thể tiếp tục như vậy nữa."
"Tại sao anh lại nghĩ thế?"
"Vì tôi đã mất đi niềm tin từ lâu rồi."
"Nhưng em vẫn tin vào anh, dù thế nào đi nữa."
"Thật sự như vậy sao?"
"Vâng, thật sự."
"""

# Trailing dash attribution
TRAILING_ATTR_PROSE = """
"Anh đã làm đúng rồi." - Minh nói.
"Nhưng hậu quả thì sao?" - Lan hỏi.
"""

# Rapid exchange — many dialogue lines in a row
RAPID_EXCHANGE_PROSE = """
"Anh đi đâu vậy?"
"Ra ngoài."
"Bao giờ về?"
"Tối."
"Ăn cơm chưa?"
"Chưa."
"Nhớ ăn nhé."
"""

# First-person POV prose (Vietnamese)
FIRST_PERSON_PROSE = """
Tôi bước vào căn phòng tối, tim tôi đập mạnh. Tôi nhìn quanh và thấy bóng người
đứng ở góc tường. Tôi tự nhủ rằng mình phải giữ bình tĩnh. Trong lòng tôi hiểu
rằng đây là cơ hội duy nhất. Tôi hít thở sâu, mình cần phải hành động ngay bây giờ.
Tôi đã chuẩn bị cho khoảnh khắc này suốt nhiều năm. Mình không thể để nó qua đi.
Tôi bước thêm một bước, tôi cảm thấy sàn nhà kẽo kẹt dưới chân tôi mình phải cẩn thận.
Tôi dừng lại. Tôi lắng nghe. Tôi chờ đợi.
"""

# Third-person POV prose
THIRD_PERSON_PROSE = """
Hắn bước vào căn phòng tối, nhìn quanh cẩn thận. Anh ấy nghĩ thầm rằng nơi này
ẩn chứa nhiều bí mật. Gã lính gác đứng im, không hay biết sự hiện diện của kẻ xâm
nhập. Nàng quan sát từ phía sau, tự nhủ rằng giờ chưa phải lúc ra tay. Cô ấy và
hắn đã đồng ý với nhau từ trước. Gã lính gác cuối cùng cũng phát hiện ra anh ấy.
"""

# Mixed POV prose
MIXED_POV_PROSE = """
Tôi bước vào phòng. Hắn nhìn tôi từ đầu đến chân, anh ấy không tin tưởng tôi.
Tôi cảm thấy cái nhìn của hắn sắc bén. Tự nhủ rằng mình cần phải cẩn thận hơn.
Trong lòng tôi hiểu rằng anh ấy đang nghĩ thầm điều gì đó. Tôi đứng im.
"""

# Telling prose — directly states emotions/traits
TELLING_PROSE = """
Anh ấy rất buồn khi nghe tin đó. Cô ấy hạnh phúc vô cùng khi gặp lại người thân.
Hắn tức giận đến mức không kiểm soát được bản thân. Cô ấy rất thông minh và luôn
biết cách giải quyết vấn đề. Cuộc chiến diễn ra ác liệt suốt nhiều giờ đồng hồ.
Họ nói chuyện với nhau rất lâu về tương lai. Vì sợ hãi nên anh ta không dám bước
ra ngoài. Do tức giận, cô ấy đã nói những điều không hay.
"""

# Showing prose — conveys emotions through action/sensory detail
SHOWING_PROSE = """
Anh đặt ly xuống bàn, đôi tay run nhẹ. Anh không nhìn về phía cửa sổ nữa.
Khóe miệng cô nhếch lên dù cô không để ý, tay cô siết chặt tay người phụ nữ
đứng trước mặt. Hàm hắn siết lại, nắm tay trắng bợt bên hông.
Đường kiếm lướt qua, tiếng gió rít, đối thủ lùi lại hai bước, mồ hôi thấm áo.
"""

# Good dialogue prose with attribution and subtext
GOOD_DIALOGUE_PROSE = """
Minh đặt hồ sơ xuống bàn, giọng bình thản: "Chúng tôi cần câu trả lời trước sáng mai."
Lan ngước nhìn, ngón tay vẫn gõ nhịp trên bàn phím: "Sáng mai là quá sớm."
"Đó không phải lời tôi muốn nghe." Minh nói.
Lan dừng gõ phím. "Vậy anh muốn nghe gì?"
"""


def _make_char(name: str, speech_pattern: str = "", voice_profile: str = "") -> Character:
    c = Character(name=name, role="chính", personality="Kiên quyết")
    c.speech_pattern = speech_pattern
    # voice_profile is not on the schema but modules use getattr fallback
    return c


# ===========================================================================
# dialogue_attribution_validator
# ===========================================================================


class TestExtractDialogueLines:
    def test_clear_attribution_detected(self):
        lines = extract_dialogue_lines(CLEAR_ATTRIBUTION_PROSE)
        assert len(lines) >= 3
        clear = [d for d in lines if d.attribution_type != "unclear"]
        assert len(clear) >= 2

    def test_unclear_attribution_flagged(self):
        lines = extract_dialogue_lines(UNCLEAR_ATTRIBUTION_PROSE)
        unclear = [d for d in lines if d.attribution_type == "unclear"]
        assert len(unclear) >= 3

    def test_trailing_attribution_detected(self):
        lines = extract_dialogue_lines(TRAILING_ATTR_PROSE)
        suffix = [d for d in lines if d.attribution_type == "suffix"]
        assert len(suffix) >= 1

    def test_empty_content_returns_empty(self):
        lines = extract_dialogue_lines("")
        assert lines == []

    def test_no_dialogue_returns_empty(self):
        lines = extract_dialogue_lines("Không có hội thoại ở đây. Chỉ là văn xuôi.")
        assert lines == []

    def test_short_dialogue_skipped(self):
        # Dialogue under 5 chars should be ignored
        lines = extract_dialogue_lines('"Ừ"\nAnh nói.')
        assert lines == []

    def test_confidence_clear_vs_unclear(self):
        lines = extract_dialogue_lines(CLEAR_ATTRIBUTION_PROSE)
        clear = [d for d in lines if d.attribution_type != "unclear"]
        for d in clear:
            assert d.confidence > 0.0

    def test_dialogue_line_text_truncated_at_100(self):
        long_line = '"' + "a" * 200 + '" Tuấn nói.'
        lines = extract_dialogue_lines(long_line)
        for d in lines:
            assert len(d.text) <= 100


class TestValidateDialogueAttribution:
    def test_empty_content_returns_perfect_score(self):
        llm = MagicMock()
        result = validate_dialogue_attribution(llm, "", [])
        assert result["clarity_score"] == 1.0
        assert result["total_lines"] == 0
        llm.generate_json.assert_not_called()

    def test_clear_prose_high_score(self):
        llm = MagicMock()
        result = validate_dialogue_attribution(llm, CLEAR_ATTRIBUTION_PROSE, [])
        assert result["clarity_score"] >= 0.5
        assert result["total_lines"] > 0

    def test_unclear_prose_low_score(self):
        llm = MagicMock()
        llm.generate_json.return_value = {"attributions": []}
        result = validate_dialogue_attribution(llm, UNCLEAR_ATTRIBUTION_PROSE, [])
        assert result["clarity_score"] < 1.0
        assert len(result["unclear_lines"]) >= 3

    def test_llm_suggestions_on_unclear(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "attributions": [
                {"line": 2, "likely_speaker": "Tuấn", "reason": "giọng cương quyết"}
            ]
        }
        chars = [_make_char("Tuấn"), _make_char("Linh")]
        result = validate_dialogue_attribution(llm, UNCLEAR_ATTRIBUTION_PROSE, chars)
        assert any("Tuấn" in s for s in result["suggestions"])

    def test_llm_failure_is_non_fatal(self):
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("API error")
        chars = [_make_char("Tuấn")]
        result = validate_dialogue_attribution(llm, UNCLEAR_ATTRIBUTION_PROSE, chars)
        # Should still return result without raising
        assert "clarity_score" in result


class TestDetectRapidExchange:
    def test_detects_rapid_exchange(self):
        exchanges = detect_rapid_exchange(RAPID_EXCHANGE_PROSE, threshold=4)
        assert len(exchanges) >= 1
        assert exchanges[0]["dialogue_count"] >= 4

    def test_no_rapid_exchange_in_clear_prose(self):
        exchanges = detect_rapid_exchange(CLEAR_ATTRIBUTION_PROSE, threshold=10)
        assert exchanges == []

    def test_custom_threshold(self):
        # threshold=3 should catch the rapid exchange prose
        exchanges = detect_rapid_exchange(RAPID_EXCHANGE_PROSE, threshold=3)
        assert len(exchanges) >= 1

    def test_empty_content(self):
        exchanges = detect_rapid_exchange("", threshold=4)
        assert exchanges == []


class TestFormatAttributionWarning:
    def test_no_warning_for_high_score(self):
        result = {"clarity_score": 0.9, "clear_attribution": 9, "total_lines": 10}
        assert format_attribution_warning(result) == ""

    def test_warning_for_low_score(self):
        result = {
            "clarity_score": 0.5,
            "clear_attribution": 5,
            "total_lines": 10,
            "suggestions": ["5 câu không rõ"],
        }
        warning = format_attribution_warning(result)
        assert "CẢNH BÁO" in warning
        assert "50%" in warning

    def test_enforcement_prompt_empty_when_not_needed(self):
        prompt = get_attribution_enforcement_prompt([], unclear_count=0)
        assert prompt == ""

    def test_enforcement_prompt_with_rapid_exchange(self):
        exchanges = [{"start_line": 1, "end_line": 7, "dialogue_count": 6}]
        prompt = get_attribution_enforcement_prompt(exchanges, unclear_count=0)
        assert "thoại nhanh" in prompt

    def test_enforcement_prompt_with_many_unclear(self):
        prompt = get_attribution_enforcement_prompt([], unclear_count=5)
        assert "không rõ" in prompt


# ===========================================================================
# dialogue_consistency_checker
# ===========================================================================


class TestExtractDialogueByCharacter:
    def test_extracts_for_known_characters(self):
        content = 'Tuấn nói: "Chúng ta cần phải hành động ngay bây giờ."\nLinh hỏi: "Tại sao vậy?"'
        chars = [_make_char("Tuấn"), _make_char("Linh")]
        result = extract_dialogue_by_character(content, chars)
        assert "Tuấn" in result
        assert "Linh" in result

    def test_unknown_characters_not_in_result(self):
        content = 'Tuấn nói: "Câu này của Tuấn."'
        chars = [_make_char("Tuấn")]
        result = extract_dialogue_by_character(content, chars)
        assert set(result.keys()) == {"Tuấn"}

    def test_empty_content_empty_lists(self):
        chars = [_make_char("Tuấn")]
        result = extract_dialogue_by_character("", chars)
        assert result["Tuấn"] == []

    def test_short_dialogue_skipped(self):
        content = 'Tuấn nói: "Ừ."'
        chars = [_make_char("Tuấn")]
        result = extract_dialogue_by_character(content, chars)
        assert result["Tuấn"] == []


class TestCheckVoiceConsistency:
    def test_no_voice_profiles_returns_consistent(self):
        llm = MagicMock()
        chars = [_make_char("Tuấn"), _make_char("Linh")]
        result = check_voice_consistency(llm, GOOD_DIALOGUE_PROSE, chars)
        assert result["consistent"] is True
        assert result["score"] == 1.0
        llm.generate_json.assert_not_called()

    def test_consistent_dialogue_passes(self):
        llm = MagicMock()
        llm.generate_json.return_value = {"match": True, "confidence": 0.9, "issue": ""}
        chars = [_make_char("Minh", speech_pattern="lạnh lùng, ngắn gọn, chuyên nghiệp")]
        result = check_voice_consistency(llm, GOOD_DIALOGUE_PROSE, chars)
        assert result["consistent"] is True
        assert result["score"] == 1.0

    def test_inconsistent_dialogue_flagged(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "match": False,
            "confidence": 0.85,
            "issue": "dùng từ quá dân dã, không phù hợp nhân vật học thuật",
        }
        chars = [_make_char("Tuấn", speech_pattern="học thuật, trang trọng, dùng từ Hán-Việt")]
        result = check_voice_consistency(llm, CLEAR_ATTRIBUTION_PROSE, chars)
        assert len(result["violations"]) >= 1
        assert result["violations"][0]["character"] == "Tuấn"
        assert result["score"] < 1.0

    def test_llm_failure_does_not_add_violation(self):
        llm = MagicMock()
        llm.generate_json.side_effect = Exception("LLM down")
        chars = [_make_char("Tuấn", speech_pattern="formal")]
        # Should not raise, violations should be empty
        result = check_voice_consistency(llm, CLEAR_ATTRIBUTION_PROSE, chars)
        assert result["violations"] == []

    def test_score_decreases_with_violations(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "match": False,
            "confidence": 0.9,
            "issue": "không khớp",
        }
        chars = [_make_char("Minh", speech_pattern="formal")]
        result = check_voice_consistency(llm, GOOD_DIALOGUE_PROSE, chars)
        assert result["score"] < 1.0


class TestDialogueConsistencyCheck:
    def test_passes_when_score_above_threshold(self):
        llm = MagicMock()
        llm.generate_json.return_value = {"match": True, "confidence": 0.95, "issue": ""}
        chars = [_make_char("Minh", speech_pattern="concise")]
        passed, warning = dialogue_consistency_check(llm, GOOD_DIALOGUE_PROSE, chars, threshold=0.7)
        assert passed is True
        assert warning == ""

    def test_fails_when_score_below_threshold(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "match": False,
            "confidence": 0.9,
            "issue": "giọng không khớp",
        }
        chars = [_make_char("Tuấn", speech_pattern="archaic")]
        passed, warning = dialogue_consistency_check(llm, CLEAR_ATTRIBUTION_PROSE, chars, threshold=0.7)
        assert passed is False
        assert "CẢNH BÁO" in warning

    def test_format_voice_warnings_empty_when_consistent(self):
        result = {"consistent": True, "violations": []}
        assert format_voice_warnings(result) == ""

    def test_format_voice_warnings_lists_violations(self):
        result = {
            "consistent": False,
            "violations": [
                {
                    "character": "Tuấn",
                    "dialogue": "Này bro, chill đi.",
                    "expected_pattern": "formal Hán-Việt",
                    "issue": "dùng tiếng lóng",
                }
            ],
        }
        warning = format_voice_warnings(result)
        assert "Tuấn" in warning
        assert "CẢNH BÁO" in warning


# ===========================================================================
# dialogue_strategy
# ===========================================================================


class TestBuildDialogueContext:
    def test_includes_character_speech_patterns(self):
        chars = [
            _make_char("Tuấn", speech_pattern="ngắn gọn, cứng rắn"),
            _make_char("Linh", speech_pattern="dịu dàng, vòng vo"),
        ]
        context = build_dialogue_context(chars, "Ngôn Tình")
        assert "Tuấn" in context
        assert "ngắn gọn" in context
        assert "Linh" in context
        assert "dịu dàng" in context

    def test_includes_general_dialogue_rules(self):
        chars = [_make_char("Tuấn", speech_pattern="trang trọng")]
        context = build_dialogue_context(chars, "Kiếm Hiệp")
        assert "QUY TẮC ĐỐI THOẠI" in context
        assert "reveal" in context.lower() or "advance" in context.lower()

    def test_no_characters_with_patterns_still_includes_rules(self):
        # Characters without speech_pattern
        chars = [_make_char("Tuấn"), _make_char("Linh")]
        context = build_dialogue_context(chars, "Trinh Thám")
        assert "QUY TẮC ĐỐI THOẠI" in context
        # PHONG CÁCH section should not appear
        assert "PHONG CÁCH" not in context

    def test_empty_characters_list(self):
        context = build_dialogue_context([], "Dị Giới")
        assert "QUY TẮC ĐỐI THOẠI" in context
        assert "Subtext" in context

    def test_subtext_guidance_present(self):
        chars = [_make_char("A", speech_pattern="x")]
        context = build_dialogue_context(chars, "Đô Thị")
        assert "Subtext" in context


class TestGetSpeechPatternReminder:
    def test_returns_reminder_for_known_character(self):
        chars = [_make_char("Minh", speech_pattern="lạnh lùng, súc tích")]
        reminder = get_speech_pattern_reminder("Minh", chars)
        assert "Minh" in reminder
        assert "lạnh lùng" in reminder

    def test_returns_empty_for_unknown_character(self):
        chars = [_make_char("Minh", speech_pattern="lạnh lùng")]
        reminder = get_speech_pattern_reminder("Lan", chars)
        assert reminder == ""

    def test_returns_empty_when_no_speech_pattern(self):
        chars = [_make_char("Minh")]
        reminder = get_speech_pattern_reminder("Minh", chars)
        assert reminder == ""

    def test_empty_characters_list(self):
        reminder = get_speech_pattern_reminder("Minh", [])
        assert reminder == ""


# ===========================================================================
# show_dont_tell_enforcer
# ===========================================================================


class TestBuildShowDontTellGuidance:
    def test_known_genre_uses_specific_palette(self):
        guidance = build_show_dont_tell_guidance("Tiên Hiệp")
        assert "Tiên Hiệp" not in guidance or "khí" in guidance or "tu luyện" in guidance
        assert "SHOW DON'T TELL" in guidance

    def test_unknown_genre_uses_default_palette(self):
        guidance = build_show_dont_tell_guidance("Thể Loại Lạ")
        assert "SHOW DON'T TELL" in guidance
        # default palette should appear
        assert "thị giác" in guidance or "xúc giác" in guidance

    def test_climax_pacing_has_fast_rhythm_note(self):
        guidance = build_show_dont_tell_guidance("Kiếm Hiệp", pacing_type="climax")
        assert "70%" in guidance
        assert "Câu ngắn" in guidance

    def test_cooldown_pacing_note(self):
        guidance = build_show_dont_tell_guidance("Ngôn Tình", pacing_type="cooldown")
        assert "60%" in guidance

    def test_setup_pacing_note(self):
        guidance = build_show_dont_tell_guidance("Dị Giới", pacing_type="setup")
        assert "50%" in guidance

    def test_default_pacing_balanced_ratio(self):
        guidance = build_show_dont_tell_guidance("Trinh Thám")
        assert "60%" in guidance

    def test_anti_patterns_section_present(self):
        guidance = build_show_dont_tell_guidance("Đô Thị")
        assert "Anti-patterns" in guidance

    @pytest.mark.parametrize("genre", list(SENSORY_PALETTE.keys()))
    def test_all_genres_produce_guidance(self, genre):
        if genre == "_default":
            pytest.skip("_default is internal key")
        guidance = build_show_dont_tell_guidance(genre)
        assert len(guidance) > 100


class TestAuditChapterTelling:
    def test_telling_prose_flagged(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "violations": [
                {
                    "excerpt": "Anh ấy rất buồn",
                    "issue": "nêu thẳng cảm xúc",
                    "suggestion": "Mô tả hành động cụ thể",
                }
            ]
        }
        violations = audit_chapter_telling(llm, TELLING_PROSE, "Ngôn Tình")
        assert len(violations) == 1
        assert "excerpt" in violations[0]
        assert "suggestion" in violations[0]

    def test_clean_prose_no_violations(self):
        llm = MagicMock()
        llm.generate_json.return_value = {"violations": []}
        violations = audit_chapter_telling(llm, SHOWING_PROSE, "Kiếm Hiệp")
        assert violations == []

    def test_llm_failure_returns_empty_list(self):
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("API down")
        violations = audit_chapter_telling(llm, TELLING_PROSE, "Tiên Hiệp")
        assert violations == []

    def test_malformed_llm_response_returns_empty(self):
        llm = MagicMock()
        llm.generate_json.return_value = {"violations": "not a list"}
        violations = audit_chapter_telling(llm, TELLING_PROSE, "Dị Giới")
        assert violations == []

    def test_non_dict_items_filtered(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "violations": [
                {"excerpt": "hắn tức giận", "issue": "telling", "suggestion": "fix"},
                "stray string",
                None,
            ]
        }
        violations = audit_chapter_telling(llm, TELLING_PROSE, "Đô Thị")
        assert len(violations) == 1
        assert violations[0]["excerpt"] == "hắn tức giận"


class TestBuildRewriteTellingPrompt:
    def test_empty_violations_returns_empty_string(self):
        prompt = build_rewrite_telling_prompt(TELLING_PROSE, [])
        assert prompt == ""

    def test_prompt_includes_original_content(self):
        violations = [{"excerpt": "Anh ấy rất buồn", "issue": "telling", "suggestion": "dùng hành động"}]
        prompt = build_rewrite_telling_prompt(TELLING_PROSE, violations)
        assert "ĐOẠN VĂN GỐC" in prompt
        assert TELLING_PROSE in prompt

    def test_prompt_lists_each_violation(self):
        violations = [
            {"excerpt": "Anh ấy rất buồn", "issue": "cảm xúc trực tiếp", "suggestion": "mô tả hành động"},
            {"excerpt": "cô ấy hạnh phúc", "issue": "nói thẳng", "suggestion": "cử chỉ cụ thể"},
        ]
        prompt = build_rewrite_telling_prompt(TELLING_PROSE, violations)
        assert "Anh ấy rất buồn" in prompt
        assert "cô ấy hạnh phúc" in prompt
        assert "1." in prompt
        assert "2." in prompt

    def test_prompt_includes_rewrite_instructions(self):
        violations = [{"excerpt": "x", "issue": "y", "suggestion": "z"}]
        prompt = build_rewrite_telling_prompt("content", violations)
        assert "showing" in prompt.lower() or "SHOW" in prompt


# ===========================================================================
# pov_drift_detector
# ===========================================================================


class TestDetectPovType:
    def test_first_person_detected(self):
        pov = detect_pov_type(FIRST_PERSON_PROSE)
        assert pov == "first"

    def test_third_person_detected(self):
        pov = detect_pov_type(THIRD_PERSON_PROSE)
        assert pov == "third"

    def test_mixed_pov_detected(self):
        pov = detect_pov_type(MIXED_POV_PROSE)
        assert pov in ("mixed", "first", "third")  # mixed or dominant

    def test_empty_returns_unknown(self):
        pov = detect_pov_type("")
        assert pov == "unknown"

    def test_single_line_no_indicators(self):
        pov = detect_pov_type("Trời hôm nay đẹp.")
        assert pov == "unknown"


class TestDetectPovDrift:
    def test_short_content_is_consistent(self):
        llm = MagicMock()
        chars = [_make_char("Tuấn")]
        result = detect_pov_drift(llm, "Tuấn bước vào phòng.", chars, expected_pov="Tuấn")
        assert result["consistent"] is True
        assert result["drifts"] == []
        llm.generate_json.assert_not_called()

    def test_consistent_chapter_no_drifts(self):
        # Build a long chapter (>1000 words) with stable third POV
        long_content = (THIRD_PERSON_PROSE + " ") * 30
        llm = MagicMock()
        llm.generate_json.return_value = {
            "character": "Hắn",
            "pov_type": "third",
            "confidence": 0.9,
        }
        chars = [_make_char("Hắn")]
        result = detect_pov_drift(llm, long_content, chars)
        assert result["consistent"] is True
        assert len(result["drifts"]) == 0

    def test_pov_drift_detected(self):
        # Use exactly 1000-1500 words so we get exactly 2 segments (no mid-segment)
        # THIRD_PERSON_PROSE ~60 words; 17 repeats ≈ 1020 words → 2 segments
        long_content = (THIRD_PERSON_PROSE.strip() + " ") * 17
        llm = MagicMock()
        # 2 segments → llm called twice (first + last, no mid since len==2)
        llm.generate_json.side_effect = [
            {"character": "Hắn", "pov_type": "third", "confidence": 0.9},
            {"character": "Linh", "pov_type": "third", "confidence": 0.85},
        ]
        chars = [_make_char("Hắn"), _make_char("Linh")]
        result = detect_pov_drift(llm, long_content, chars)
        assert len(result["drifts"]) >= 1
        assert result["drifts"][0]["from_char"] == "Hắn"
        assert result["drifts"][0]["to_char"] == "Linh"

    def test_low_confidence_drift_ignored(self):
        # Same 2-segment setup
        long_content = (THIRD_PERSON_PROSE.strip() + " ") * 17
        llm = MagicMock()
        # Low confidence on last segment should not produce a drift
        llm.generate_json.side_effect = [
            {"character": "Hắn", "pov_type": "third", "confidence": 0.9},
            {"character": "Linh", "pov_type": "third", "confidence": 0.5},
        ]
        chars = [_make_char("Hắn"), _make_char("Linh")]
        result = detect_pov_drift(llm, long_content, chars)
        assert result["consistent"] is True


class TestFormatPovWarning:
    def test_no_warning_when_consistent(self):
        result = {"consistent": True, "primary_pov": "Tuấn", "drifts": []}
        assert format_pov_warning(result) == ""

    def test_warning_lists_drifts(self):
        result = {
            "consistent": False,
            "primary_pov": "Tuấn",
            "drifts": [
                {"position": "segment 2/4", "from_char": "Tuấn", "to_char": "Linh"}
            ],
        }
        warning = format_pov_warning(result)
        assert "CẢNH BÁO POV" in warning
        assert "Tuấn" in warning
        assert "Linh" in warning


class TestValidateChapterPov:
    def test_short_content_passes(self):
        llm = MagicMock()
        chars = [_make_char("Tuấn")]
        passed, warning = validate_chapter_pov(llm, "Một câu ngắn.", chars)
        assert passed is True
        assert warning == ""

    def test_consistent_long_chapter_passes(self):
        long_content = (THIRD_PERSON_PROSE + " ") * 30
        llm = MagicMock()
        llm.generate_json.return_value = {
            "character": "Hắn",
            "pov_type": "third",
            "confidence": 0.9,
        }
        chars = [_make_char("Hắn")]
        passed, warning = validate_chapter_pov(llm, long_content, chars)
        assert passed is True
