from types import SimpleNamespace

import mcp_server
from config import ConfigManager


class FakeOrch:
    async def run_full_pipeline(self, **kw):
        return SimpleNamespace(status="completed", enhanced_story=SimpleNamespace(chapters=[1, 2]))


def test_job_completes_with_fake_orchestrator():
    mcp_server._jobs.clear()
    mcp_server._set_job("s1", {"status": "queued"})
    mcp_server._run_job("s1", {"genre": "x", "num_chapters": 2, "language": "en"}, orchestrator_factory=FakeOrch)
    job = mcp_server._get_job("s1")
    assert job["status"] == "completed" and job["chapter_count"] == 2


def test_job_does_not_touch_global_language():
    mcp_server._jobs.clear()
    mcp_server._set_job("s2", {"status": "queued"})
    before = ConfigManager().pipeline.language
    mcp_server._run_job("s2", {"genre": "x", "num_chapters": 1, "language": "zz"}, orchestrator_factory=FakeOrch)
    assert ConfigManager().pipeline.language == before
    assert mcp_server._get_job("s2")["status"] == "completed"
