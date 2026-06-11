"""Shared pytest fixtures for StoryForge test suite."""
import json
import os
import tempfile
import time
from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Hermetic config: redirect CONFIG_FILE for the WHOLE test session.
#
# Several tests exercise ConfigManager().save() / the settings API without
# patching CONFIG_FILE; each such test used to rewrite the developer's real
# data/config.json with fixture state (wiping api_key, fallback_models and
# the comic_*/panels_* flags). CI never saw this because data/config.json is
# gitignored there, so this redirect also makes local runs behave like CI.
# Done at import time so it precedes any ConfigManager() instantiation during
# collection. Tests that patch config.persistence.CONFIG_FILE themselves are
# unaffected.
# ---------------------------------------------------------------------------
from config import persistence as _config_persistence

_TEST_CONFIG_DIR = tempfile.mkdtemp(prefix="storyforge-test-config-")
_TEST_CONFIG_FILE = os.path.join(_TEST_CONFIG_DIR, "config.json")

# Seed the sandbox with a COPY of the developer's real config so tests see the
# same effective settings as before this guard existed (e.g. a reachable local
# LLM base_url — without it, unmocked LLM calls fall into multi-minute retry
# backoff against the unreachable dataclass-default URL). Reads stay realistic;
# writes can no longer touch the real file. On CI data/config.json is absent
# and tests run on pure dataclass defaults, as they always did.
if os.path.exists(_config_persistence.CONFIG_FILE):
    import shutil

    shutil.copyfile(_config_persistence.CONFIG_FILE, _TEST_CONFIG_FILE)

    # Hermetic LLM: point every base_url in the sandbox copy at a local
    # accept-and-close listener so an unmocked LLM call fails in milliseconds
    # instead of running a real generation against the developer's live proxy.
    # A listener (not a closed port) because Windows loopback takes ~2-4s to
    # refuse a connection — across the 12-attempt retry chain that exceeds the
    # 120s per-test timeout for pipeline tests. Paired with the no-op
    # retry-sleep fixture below, such tests fail fast and visibly rather than
    # hanging the suite or spending quota.
    import socket as _socket
    import threading as _threading

    _dead_srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    _dead_srv.bind(("127.0.0.1", 0))
    _dead_srv.listen(64)

    def _dead_llm_accept_loop():
        while True:
            try:
                _conn, _ = _dead_srv.accept()
                _conn.close()
            except OSError:
                return  # listener closed at interpreter exit

    _threading.Thread(
        target=_dead_llm_accept_loop, daemon=True, name="dead-llm-listener"
    ).start()
    _DEAD_LLM_URL = f"http://127.0.0.1:{_dead_srv.getsockname()[1]}/v1"
    def _rewrite_base_urls(_node):
        """Point every *base_url key (LLM endpoints at any nesting level —
        llm.base_url, cheap/layer1/layer2/long_context overrides,
        fallback_models[].base_url, api_keys[].base_url) at the dead listener.
        share_base_url is a public-link prefix, not an endpoint — leave it."""
        if isinstance(_node, dict):
            for _k, _v in _node.items():
                if isinstance(_v, (dict, list)):
                    _rewrite_base_urls(_v)
                elif (
                    isinstance(_k, str)
                    and _k.endswith("base_url")
                    and _k != "share_base_url"
                    and _v
                ):
                    _node[_k] = _DEAD_LLM_URL
        elif isinstance(_node, list):
            for _item in _node:
                _rewrite_base_urls(_item)

    try:
        with open(_TEST_CONFIG_FILE, encoding="utf-8") as _f:
            _sandbox_cfg = json.load(_f)
        _rewrite_base_urls(_sandbox_cfg)
        with open(_TEST_CONFIG_FILE, "w", encoding="utf-8") as _f:
            json.dump(_sandbox_cfg, _f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # malformed config — tests fall back to dataclass defaults anyway

_config_persistence.CONFIG_FILE = _TEST_CONFIG_FILE
_config_persistence._SECRETS_FILE = os.path.join(_TEST_CONFIG_DIR, "secrets.json")

from models.schemas import (
    Character, Chapter, ChapterOutline, WorldSetting,
    StoryDraft, EnhancedStory, PipelineOutput, SimulationResult, SimulationEvent,
)


# Sprint 1 P3: default the test suite to strict-mode handoff validation so any
# silent-empty regression fails loudly. Individual tests can opt out via
# `monkeypatch.delenv("STORYFORGE_HANDOFF_STRICT", raising=False)`.
@pytest.fixture(autouse=True)
def _default_strict_handoff(monkeypatch):
    if "STORYFORGE_HANDOFF_STRICT" not in os.environ:
        monkeypatch.setenv("STORYFORGE_HANDOFF_STRICT", "1")
    yield


# An unmocked LLM call in a test lands in services.llm.client's retry backoff
# (30s base, exponential) and hangs the whole suite past any per-test timeout.
# No-op the dedicated retry-sleep seam so such calls fail fast and visibly.
@pytest.fixture(autouse=True)
def _no_llm_retry_backoff(monkeypatch):
    import services.llm.client as _llm_client
    monkeypatch.setattr(_llm_client, "_retry_sleep", lambda *_a, **_k: None)
    yield


# Settings-API tests write through the ConfigManager singleton (and the
# sandbox config file), so e.g. a POST with base_url=http://localhost:8000/v1
# leaks a dead, SLOW-to-refuse endpoint into every later test — unmocked LLM
# calls then take minutes instead of milliseconds and blow the per-test
# timeout. Restore the LLM section and per-layer endpoint overrides (and the
# sandbox file) after every test.
_SANDBOX_CONFIG_BASELINE: bytes | None = None
if os.path.exists(_TEST_CONFIG_FILE):
    with open(_TEST_CONFIG_FILE, "rb") as _f:
        _SANDBOX_CONFIG_BASELINE = _f.read()

_PIPELINE_URL_FIELDS = ("layer1_base_url", "layer2_base_url", "long_context_base_url")


@pytest.fixture(autouse=True)
def _restore_llm_config():
    import copy

    from config import ConfigManager

    cfg = ConfigManager()
    saved_llm = copy.deepcopy(cfg.llm.__dict__)
    saved_pipeline = {
        k: getattr(cfg.pipeline, k)
        for k in _PIPELINE_URL_FIELDS
        if hasattr(cfg.pipeline, k)
    }
    yield
    cfg.llm.__dict__.clear()
    cfg.llm.__dict__.update(saved_llm)
    for k, v in saved_pipeline.items():
        setattr(cfg.pipeline, k, v)
    if _SANDBOX_CONFIG_BASELINE is not None:
        try:
            with open(_TEST_CONFIG_FILE, "rb") as f:
                current = f.read()
            if current != _SANDBOX_CONFIG_BASELINE:
                with open(_TEST_CONFIG_FILE, "wb") as f:
                    f.write(_SANDBOX_CONFIG_BASELINE)
        except OSError:
            pass


# LLMClient is a process-wide singleton. A test that monkeypatches a method
# directly on an instance (e.g. `monkeypatch.setattr(gen.llm, "generate_json",
# fake)`) gets the old *bound method* recorded as the restore value, so the
# undo writes that bound method into the singleton's __dict__ — permanently
# shadowing class-level patches for every later test (order-dependent
# failures). Strip such shadows after each test.
_LLM_METHOD_NAMES = (
    "generate", "generate_json", "generate_stream",
    "check_connection", "check_provider",
)


@pytest.fixture(autouse=True)
def _unshadow_llm_singleton():
    yield
    from services.llm.client import LLMClient
    inst = LLMClient._instance
    if inst is not None:
        for name in _LLM_METHOD_NAMES:
            inst.__dict__.pop(name, None)


# Reset orchestrator_layers' module-level sync engine before each test so
# fixtures that patch DATABASE_URL don't inherit a prior test's engine
# (which would silently write to the wrong DB). Dispose the pool to avoid
# leaking connections across tests.
@pytest.fixture(autouse=True)
def _reset_orchestrator_sync_engine():
    from pipeline import orchestrator_layers as _ol
    if _ol._sync_engine is not None:
        try:
            _ol._sync_engine.dispose()
        except Exception:
            pass
        _ol._sync_engine = None
    yield


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
