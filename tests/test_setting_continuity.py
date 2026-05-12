"""Regression tests for setting_continuity extraction edge cases."""

from unittest.mock import patch

from pipeline.layer2_enhance.setting_continuity import SettingContinuityGraph


def test_extract_handles_null_owner_from_llm():
    """LLM may return {"owner": null} — must not raise Pydantic validation error."""
    graph = SettingContinuityGraph()
    payload = {
        "locations": [],
        "objects": [
            {"name": "thanh kiếm cổ", "description": "kiếm bí ẩn", "location": "hang động", "owner": None}
        ],
        "time_markers": [],
        "characters_at_locations": {},
    }
    with patch.object(graph.llm, "generate_json", return_value=payload):
        graph.extract_from_chapter("chương nội dung", chapter_number=3)

    assert "thanh kiếm cổ" in graph.objects
    assert graph.objects["thanh kiếm cổ"].current_owner == ""
