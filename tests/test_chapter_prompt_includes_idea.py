"""Verify build_chapter_prompt injects the user's idea block into the prompt.

Backstops the idea-fidelity fix: the chapter LLM must SEE the original idea text
(or its head/tail+summary form when long), not just downstream paraphrases.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from models.schemas import Character, ChapterOutline, WorldSetting
from pipeline.layer1_story.chapter_writer import build_chapter_prompt


def _mk_config():
    pipeline = SimpleNamespace(
        rag_enabled=False,
        use_long_context=False,
        enable_voice_lock=False,
        enable_tiered_context=False,
        enable_chapter_contracts=False,
        enable_proactive_constraints=False,
        enable_thread_enforcement=False,
        enable_l1_causal_graph=False,
        enable_emotional_memory=False,
        enable_foreshadowing_enforcement=False,
        enable_scene_decomposition=False,
        enable_scene_beat_writing=False,
        enable_self_review=False,
    )
    return SimpleNamespace(pipeline=pipeline)


def _build(idea="", idea_summary=""):
    config = _mk_config()
    outline = ChapterOutline(chapter_number=1, title="C1", summary="Things happen")
    world = WorldSetting(name="W", description="d")
    chars = [Character(name="Hùng", role="protagonist", personality="brave", background="hero")]
    with patch("pipeline.layer1_story.chapter_writer.build_adaptive_write_prompt", side_effect=lambda p, *a, **kw: p), \
         patch("pipeline.layer1_story.narrative_context_block.build_narrative_block") as mock_nb:
        mock_nb.return_value.render.return_value = ""
        _, user_prompt = build_chapter_prompt(
            config, "S", "fantasy", "vivid",
            chars, world, outline, 2000,
            idea=idea, idea_summary=idea_summary,
        )
    return user_prompt


def test_short_idea_injected_verbatim():
    idea = "Lý Phong gặp Tô Vân tại Lạc Dương, hai người tu luyện ở Thiên Sơn."
    prompt = _build(idea=idea)
    assert "Ý TƯỞNG GỐC CỦA TÁC GIẢ" in prompt
    assert "Lý Phong" in prompt
    assert "Tô Vân" in prompt
    assert "Lạc Dương" in prompt
    assert "Thiên Sơn" in prompt


def test_long_idea_uses_head_tail_plus_summary():
    head_marker = "MARKER_HEAD_LÝ_PHONG"
    tail_marker = "MARKER_TAIL_TÔ_VÂN"
    summary = "Tóm tắt giữ tên: Lý Phong, Tô Vân, Lạc Dương."
    middle_padding = "x" * 4000
    idea = head_marker + middle_padding + tail_marker
    assert len(idea) > 3000
    prompt = _build(idea=idea, idea_summary=summary)
    assert "ĐOẠN ĐẦU NGUYÊN VĂN" in prompt
    assert "ĐOẠN CUỐI NGUYÊN VĂN" in prompt
    assert "TÓM TẮT GIỮ TÊN RIÊNG" in prompt
    assert head_marker in prompt
    assert tail_marker in prompt
    assert "Tóm tắt giữ tên" in prompt
    # Middle padding should NOT appear in full (head=2000, tail=500, padding=4000)
    assert middle_padding not in prompt


def test_empty_idea_uses_placeholder():
    prompt = _build(idea="")
    assert "Ý TƯỞNG GỐC CỦA TÁC GIẢ" in prompt
    assert "Tác giả không cung cấp" in prompt
