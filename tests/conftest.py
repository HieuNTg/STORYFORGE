"""Shared pytest fixtures for StoryForge test suite."""
import json
import time
from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch
from models.schemas import (
    Character, Chapter, ChapterOutline, WorldSetting,
    StoryDraft, EnhancedStory, PipelineOutput, AgentReview,
    SimulationResult, SimulationEvent, VideoScript, StoryboardPanel, VoiceLine,
    ShotType,
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
            name="Ly Huyen",
            role="protagonist",
            personality="Kien cuong, thong minh",
            motivation="Tim su that ve gia toc",
            background="Mo coi tu nho, duoc su phu nuoi duong",
            relationships=["Nguyen Minh: ban dong hanh", "Hoang Yen: ke thu"],
        ),
        Character(
            name="Nguyen Minh",
            role="sidekick",
            personality="Hai huoc, trung thanh",
            motivation="Bao ve ban be",
            background="Con trai thuong nhan giau co",
            relationships=["Ly Huyen: ban than"],
        ),
        Character(
            name="Hoang Yen",
            role="antagonist",
            personality="Xao quyet, tham vong",
            motivation="Chiem doat quyen luc",
            background="Truong lao phan boi tong mon",
            relationships=["Ly Huyen: ke thu"],
        ),
    ]


@pytest.fixture
def sample_chapters():
    """Create sample chapters for testing."""
    return [
        Chapter(
            chapter_number=1,
            title="Khoi dau",
            content="Ly Huyen buoc vao tong mon voi anh mat kien dinh. "
                    "Anh biet con duong phia truoc day gian nan, nhung quyet tam khong lui buoc.",
            summary="Ly Huyen gia nhap tong mon",
        ),
        Chapter(
            chapter_number=2,
            title="Thu thach dau tien",
            content="Tran dau dau tien cua Ly Huyen tai tong mon. "
                    "Doi thu la Hoang Yen, ke co suc manh vuot troi.",
            summary="Ly Huyen doi dau Hoang Yen",
        ),
        Chapter(
            chapter_number=3,
            title="Bi mat phat lo",
            content="Nguyen Minh phat hien bi mat cua tong mon. "
                    "Mot am muu dang hinh thanh trong bong toi.",
            summary="Phat hien am muu trong tong mon",
        ),
    ]


@pytest.fixture
def sample_world():
    """Create sample world setting."""
    return WorldSetting(
        name="Thanh Van Gioi",
        description="The gioi tu tien voi 9 canh gioi",
        rules=["Linh khi la nguon suc manh", "Tu luyen theo cap bac"],
        locations=["Thanh Van Tong", "Hac Phong Coc", "Long Uyen Ho"],
        era="Co dai",
    )


@pytest.fixture
def sample_outlines():
    """Create sample chapter outlines."""
    return [
        ChapterOutline(chapter_number=1, title="Khoi dau", summary="MC gia nhap tong mon"),
        ChapterOutline(chapter_number=2, title="Thu thach", summary="MC doi dau ke thu"),
        ChapterOutline(chapter_number=3, title="Bi mat", summary="Phat hien am muu"),
    ]


@pytest.fixture
def sample_story_draft(sample_characters, sample_chapters, sample_world, sample_outlines):
    """Create a complete story draft."""
    return StoryDraft(
        title="Thanh Van Kiem Khach",
        genre="tien_hiep",
        synopsis="Cau chuyen ve Ly Huyen tu luyen thanh kiem khach",
        characters=sample_characters,
        world=sample_world,
        outlines=sample_outlines,
        chapters=sample_chapters,
    )


@pytest.fixture
def sample_enhanced_story(sample_chapters):
    """Create a sample enhanced story."""
    return EnhancedStory(
        title="Thanh Van Kiem Khach (Enhanced)",
        genre="tien_hiep",
        chapters=sample_chapters,
        drama_score=0.75,
        enhancement_notes=["Tang xung dot giua MC va antagonist"],
    )


@pytest.fixture
def sample_simulation_result():
    """Create sample simulation result."""
    return SimulationResult(
        events=[
            SimulationEvent(
                round_number=1,
                event_type="confrontation",
                description="Ly Huyen doi dau Hoang Yen tai dai dien",
                drama_score=0.8,
                characters_involved=["Ly Huyen", "Hoang Yen"],
            ),
        ],
        drama_suggestions=["Them canh phan boi bat ngo"],
    )


@pytest.fixture
def sample_video_script():
    """Create sample video script."""
    return VideoScript(
        title="Thanh Van Kiem Khach",
        panels=[
            StoryboardPanel(
                panel_number=1,
                chapter_number=1,
                shot_type=ShotType.WIDE,
                description="Ly Huyen buoc vao tong mon",
                dialogue="Day chinh la noi ta se bat dau.",
                mood="determined",
            ),
        ],
        voice_lines=[
            VoiceLine(
                character="Ly Huyen",
                text="Day chinh la noi ta se bat dau.",
                emotion="determined",
            ),
        ],
        total_duration_seconds=300.0,
    )


@pytest.fixture
def sample_pipeline_output(
    sample_story_draft,
    sample_enhanced_story,
    sample_simulation_result,
    sample_video_script,
):
    """Create a complete pipeline output for agent testing."""
    return PipelineOutput(
        story_draft=sample_story_draft,
        enhanced_story=sample_enhanced_story,
        simulation_result=sample_simulation_result,
        video_script=sample_video_script,
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
