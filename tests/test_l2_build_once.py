"""Sprint 2 — expensive per-draft objects must be built once, not per chapter.

`_build_voice_engine` was called from five sites: once per chapter, and again
on every contract or voice retry. When the draft carries no `voice_profiles`,
building it fires a cheap LLM call per character — roughly 50 identical calls
on a 10-chapter, 5-character story, all producing the same fingerprints.

`_theme_profile` had the same shape plus a race: chapters are enhanced
concurrently, and read-then-assign let each of them start its own
`extract_theme` before any had stored a result.
"""

import threading
from unittest.mock import MagicMock, patch

from models.schemas import StoryDraft
from pipeline.layer2_enhance import enhancer as E


def _draft():
    return StoryDraft(title="Bóng tối Hà Nội", genre="hiện đại")


class TestVoiceEngineBuiltOnce:
    def test_repeated_calls_reuse_one_engine(self):
        draft = _draft()
        built = MagicMock()
        with patch(
            "pipeline.layer2_enhance.voice_fingerprint.VoiceFingerprintEngine",
            return_value=built,
        ) as ctor:
            first = E._build_voice_engine(draft)
            for _ in range(4):
                E._build_voice_engine(draft)

        assert first is built
        assert ctor.call_count == 1, "the engine was rebuilt per call site"

    def test_concurrent_chapters_share_one_build(self):
        """Chapters run under asyncio.gather; only one build may start."""
        draft = _draft()
        starts = []

        class SlowEngine:
            def build_from_draft(self, _draft, **kwargs):
                starts.append(1)
                threading.Event().wait(0.02)

        with patch(
            "pipeline.layer2_enhance.voice_fingerprint.VoiceFingerprintEngine",
            SlowEngine,
        ):
            threads = [
                threading.Thread(target=lambda: E._build_voice_engine(draft))
                for _ in range(8)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(starts) == 1, f"{len(starts)} concurrent builds"

    def test_a_failed_build_is_not_retried_on_every_call(self):
        draft = _draft()
        with patch(
            "pipeline.layer2_enhance.voice_fingerprint.VoiceFingerprintEngine",
            side_effect=RuntimeError("provider down"),
        ) as ctor:
            assert E._build_voice_engine(draft) is None
            assert E._build_voice_engine(draft) is None
            assert E._build_voice_engine(draft) is None

        assert ctor.call_count == 1, "a failed build was retried per call site"

    def test_separate_drafts_get_separate_engines(self):
        a, b = _draft(), _draft()
        with patch(
            "pipeline.layer2_enhance.voice_fingerprint.VoiceFingerprintEngine",
            side_effect=lambda: MagicMock(),
        ) as ctor:
            E._build_voice_engine(a)
            E._build_voice_engine(b)
        assert ctor.call_count == 2

    def test_none_draft_is_handled(self):
        assert E._build_voice_engine(None) is None


class TestThemeProfileBuiltOnce:
    def test_repeated_calls_extract_once(self):
        draft = _draft()
        tracker = MagicMock()
        tracker.extract_theme.return_value = MagicMock(central_theme="mất mát")
        with patch(
            "pipeline.layer2_enhance.thematic_tracker.ThematicTracker",
            return_value=tracker,
        ):
            first = E._get_theme_profile(draft)
            for _ in range(4):
                E._get_theme_profile(draft)

        assert tracker.extract_theme.call_count == 1
        assert E._get_theme_profile(draft) is first

    def test_concurrent_chapters_extract_once(self):
        draft = _draft()
        calls = []

        class Tracker:
            def extract_theme(self, _draft):
                calls.append(1)
                threading.Event().wait(0.02)
                return MagicMock(central_theme="mất mát")

        with patch(
            "pipeline.layer2_enhance.thematic_tracker.ThematicTracker", Tracker
        ):
            threads = [
                threading.Thread(target=lambda: E._get_theme_profile(draft))
                for _ in range(8)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(calls) == 1, f"{len(calls)} concurrent theme extractions"

    def test_none_draft_is_handled(self):
        assert E._get_theme_profile(None) is None
