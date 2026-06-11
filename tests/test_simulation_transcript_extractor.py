"""Unit tests for services/simulation_transcript_extractor.py (previously untested).

The extractor is pure and sync: SimulationResult | dict → SimulationTranscript.
"""

from __future__ import annotations

from models.schemas import AgentPost, SimulationResult, SimulationTranscript
from services.simulation_transcript_extractor import extract


def _post(name="Lan Anh", content="Xin chào", round_number=1, sentiment="vui"):
    return AgentPost(
        agent_name=name,
        content=content,
        action_type="post",
        sentiment=sentiment,
        round_number=round_number,
    )


class TestExtractFromSimulationResult:
    def test_maps_posts_to_transcript_turns(self):
        result = SimulationResult(
            agent_posts=[_post(), _post(name="Hải Long", round_number=2)],
            drama_suggestions=["Mâu thuẫn leo thang", "Bí mật bị lộ"],
        )
        transcript = extract(result)
        assert isinstance(transcript, SimulationTranscript)
        assert [t.id for t in transcript.logs] == ["t01-000", "t02-001"]
        first = transcript.logs[0]
        assert first.senderId == "Lan Anh"
        assert first.senderName == "Lan Anh"
        assert first.emotion == "vui"
        assert first.speech == "Xin chào"
        assert first.actionDetails == ""
        assert transcript.outcomeSummary == "Mâu thuẫn leo thang\nBí mật bị lộ"

    def test_blank_agent_name_falls_back_to_narrator(self):
        result = SimulationResult(agent_posts=[_post(name="  ")])
        transcript = extract(result)
        assert transcript.logs[0].senderId == "narrator"


class TestExtractFromDict:
    def test_coerces_dict_posts(self):
        artifact = {
            "agent_posts": [
                {
                    "agent_name": "Thu Hà",
                    "content": "Tôi không đồng ý",
                    "action_type": "comment",
                    "round_number": 3,
                }
            ],
            "drama_suggestions": ["Đối đầu trực diện"],
        }
        transcript = extract(artifact)
        assert transcript.logs[0].id == "t03-000"
        assert transcript.logs[0].speech == "Tôi không đồng ý"

    def test_malformed_posts_are_skipped(self):
        artifact = {
            "agent_posts": [
                {"agent_name": "thiếu action_type"},  # fails validation
                "not a dict",
                {
                    "agent_name": "Minh",
                    "content": "ok",
                    "action_type": "post",
                },
            ]
        }
        transcript = extract(artifact)
        assert len(transcript.logs) == 1
        assert transcript.logs[0].senderName == "Minh"

    def test_non_string_suggestions_are_ignored(self):
        artifact = {"agent_posts": [], "drama_suggestions": [None, 42, "  ", "Giữ lại"]}
        assert extract(artifact).outcomeSummary == "Giữ lại"


class TestEdgeCases:
    def test_unknown_artifact_type_returns_empty_transcript(self):
        transcript = extract(12345)
        assert transcript.logs == []
        assert transcript.outcomeSummary == ""

    def test_summary_truncated_to_4000_chars_with_ellipsis(self):
        artifact = {"agent_posts": [], "drama_suggestions": ["x" * 5000]}
        summary = extract(artifact).outcomeSummary
        assert len(summary) == 4000
        assert summary.endswith("…")

    def test_long_speech_capped_at_2000_chars(self):
        result = SimulationResult(agent_posts=[_post(content="y" * 3000)])
        assert len(extract(result).logs[0].speech) == 2000
