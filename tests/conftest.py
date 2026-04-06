"""Shared pytest fixtures for StoryForge test suite."""
import json
import time
from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch
from models.schemas import (
    Character, Chapter, ChapterOutline, WorldSetting,
    StoryDraft, EnhancedStory, PipelineOutput, SimulationResult, SimulationEvent,
)


# ---------------------------------------------------------------------------
# CI Timing Plugin
# ---------------------------------------------------------------------------

_TIMINGS_FILE = Path(__file__).parent.parent / "data" / "test_timings.json"
_TOP_N = 50

_timing_records: list[dict] = []
_session_start: float = 0.0


def pytest_sessionstart(session):  # noqa: ARG001
    global _session_start, _timing_records
    _session_start = time.time()
    _timing_records = []


def pytest_runtest_makereport(item, call):
    if call.when == "call":
        record = {
            "name": item.nodeid,
            "duration": call.duration,
            "status": "passed" if call.excinfo is None else "failed",
        }
        _timing_records.append(record)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    total = time.time() - _session_start
    top = sorted(_timing_records, key=lambda r: r["duration"], reverse=True)[:_TOP_N]
    payload = {
        "timestamp": time.time(),
        "total_duration": total,
        "tests": top,
    }
    try:
        _TIMINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TIMINGS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass  # Never fail the test run because of timing writes


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_characters():
    """Create sample characters for testing."""
    return [
        Character(
            name="Lý Huyền",
            role="protagonist",
            personality="Kiên cường, thông minh",
            motivation="Tìm sự thật về gia tộc",
            background="Mồ côi từ nhỏ, được sư phụ nuôi dưỡng",
            relationships=["Nguyễn Minh: bạn đồng hành", "Hoàng Yến: kẻ thù"],
        ),
        Character(
            name="Nguyễn Minh",
            role="sidekick",
            personality="Hài hước, trung thành",
            motivation="Bảo vệ bạn bè",
            background="Con trai thương nhân giàu có",
            relationships=["Lý Huyền: bạn thân"],
        ),
        Character(
            name="Hoàng Yến",
            role="antagonist",
            personality="Xảo quyệt, tham vọng",
            motivation="Chiếm đoạt quyền lực",
            background="Trưởng lão phản bội tông môn",
            relationships=["Lý Huyền: kẻ thù"],
        ),
    ]


@pytest.fixture
def sample_chapters():
    """Create sample chapters for testing."""
    return [
        Chapter(
            chapter_number=1,
            title="Khởi đầu",
            content="Lý Huyền bước vào tông môn với ánh mắt kiên định. "
                    "Anh biết con đường phía trước đầy gian nan, nhưng quyết tâm không lui bước.",
            summary="Lý Huyền gia nhập tông môn",
        ),
        Chapter(
            chapter_number=2,
            title="Thử thách đầu tiên",
            content="Trận đấu đầu tiên của Lý Huyền tại tông môn. "
                    "Đối thủ là Hoàng Yến, kẻ có sức mạnh vượt trội.",
            summary="Lý Huyền đối đầu Hoàng Yến",
        ),
        Chapter(
            chapter_number=3,
            title="Bí mật phát lộ",
            content="Nguyễn Minh phát hiện bí mật của tông môn. "
                    "Một âm mưu đang hình thành trong bóng tối.",
            summary="Phát hiện âm mưu trong tông môn",
        ),
    ]


@pytest.fixture
def sample_world():
    """Create sample world setting."""
    return WorldSetting(
        name="Thanh Vân Giới",
        description="Thế giới tu tiên với 9 cảnh giới",
        rules=["Linh khí là nguồn sức mạnh", "Tu luyện theo cấp bậc"],
        locations=["Thanh Vân Tông", "Hắc Phong Cốc", "Long Uyên Hồ"],
        era="Cổ đại",
    )


@pytest.fixture
def sample_outlines():
    """Create sample chapter outlines."""
    return [
        ChapterOutline(chapter_number=1, title="Khởi đầu", summary="MC gia nhập tông môn"),
        ChapterOutline(chapter_number=2, title="Thử thách", summary="MC đối đầu kẻ thù"),
        ChapterOutline(chapter_number=3, title="Bí mật", summary="Phát hiện âm mưu"),
    ]


@pytest.fixture
def sample_story_draft(sample_characters, sample_chapters, sample_world, sample_outlines):
    """Create a complete story draft."""
    return StoryDraft(
        title="Thanh Vân Kiếm Khách",
        genre="tien_hiep",
        synopsis="Câu chuyện về Lý Huyền tu luyện thành kiếm khách",
        characters=sample_characters,
        world=sample_world,
        outlines=sample_outlines,
        chapters=sample_chapters,
    )


@pytest.fixture
def sample_enhanced_story(sample_chapters):
    """Create a sample enhanced story."""
    return EnhancedStory(
        title="Thanh Vân Kiếm Khách (Enhanced)",
        genre="tien_hiep",
        chapters=sample_chapters,
        drama_score=0.75,
        enhancement_notes=["Tăng xung đột giữa MC và antagonist"],
    )


@pytest.fixture
def sample_simulation_result():
    """Create sample simulation result."""
    return SimulationResult(
        events=[
            SimulationEvent(
                round_number=1,
                event_type="confrontation",
                description="Lý Huyền đối đầu Hoàng Yến tại đại điện",
                drama_score=0.8,
                characters_involved=["Lý Huyền", "Hoàng Yến"],
            ),
        ],
        drama_suggestions=["Thêm cảnh phản bội bất ngờ"],
    )


@pytest.fixture
def sample_pipeline_output(
    sample_story_draft,
    sample_enhanced_story,
    sample_simulation_result,
):
    """Create a complete pipeline output for agent testing."""
    return PipelineOutput(
        story_draft=sample_story_draft,
        enhanced_story=sample_enhanced_story,
        simulation_result=sample_simulation_result,
        reviews=[],
    )


@pytest.fixture
def mock_llm_client():
    """Create a mocked LLM client."""
    with patch("services.llm_client.LLMClient") as mock_cls:
        client = MagicMock()
        client.generate.return_value = "Mocked LLM response"
        client.generate_json.return_value = {
            "score": 0.8,
            "issues": [],
            "suggestions": ["Tot roi"],
        }
        mock_cls.return_value = client
        yield client
