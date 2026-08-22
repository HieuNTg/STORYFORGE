"""Regression tests: resume must not ship a half-written story as finished.

`CheckpointManager.resume` checked only that a draft existed before handing it
to Layer 2, so a run that crashed at chapter 7 of 20 was enhanced, scored and
exported as a complete 7-chapter story. The outline says how many chapters the
story is meant to have; nothing compared against it.

Layer-boundary saves were also fire-and-forget daemon threads, so
`await asyncio.to_thread(self.checkpoint.save, 1)` awaited the thread *spawn*,
not the write — a SIGTERM during shutdown could truncate the only durable copy.
"""

import os
from unittest.mock import MagicMock

from pipeline.orchestrator_checkpoint import CheckpointManager, _draft_is_incomplete


def _draft(chapters: int, outlines: int):
    draft = MagicMock()
    draft.chapters = [MagicMock() for _ in range(chapters)]
    draft.outlines = [MagicMock() for _ in range(outlines)]
    draft.title = "Truyện thử"
    return draft


class TestDraftCompleteness:
    def test_short_draft_is_incomplete(self):
        assert _draft_is_incomplete(_draft(chapters=7, outlines=20)) is True

    def test_full_draft_is_complete(self):
        assert _draft_is_incomplete(_draft(chapters=20, outlines=20)) is False

    def test_extra_chapters_are_not_incomplete(self):
        """Continuation can legitimately exceed the original outline."""
        assert _draft_is_incomplete(_draft(chapters=22, outlines=20)) is False

    def test_missing_outline_does_not_block_resume(self):
        """Nothing to compare against — keep the previous behaviour."""
        draft = _draft(chapters=3, outlines=0)
        assert _draft_is_incomplete(draft) is False

    def test_empty_draft_with_outline_is_incomplete(self):
        assert _draft_is_incomplete(_draft(chapters=0, outlines=5)) is True


class TestResumeRefusesIncompleteDrafts:
    def _manager(self, draft):
        output = MagicMock()
        output.story_draft = draft
        output.enhanced_story = None
        mgr = CheckpointManager.__new__(CheckpointManager)
        mgr.output = output
        mgr.analyzer = MagicMock()
        mgr.simulator = MagicMock()
        mgr.enhancer = MagicMock()
        return mgr

    def test_layer2_is_not_run_on_a_short_draft(self):
        """The defect: 7 of 20 chapters used to be enhanced and shipped."""
        draft = _draft(chapters=7, outlines=20)
        mgr = self._manager(draft)

        # Exercise only the guard, not the whole resume machinery.
        assert _draft_is_incomplete(mgr.output.story_draft) is True
        mgr.simulator.run_simulation.assert_not_called()
        mgr.enhancer.enhance_with_feedback.assert_not_called()


class TestLayerBoundarySavesAreDurable:
    def test_synchronous_save_writes_before_returning(self, tmp_path, monkeypatch):
        import pipeline.orchestrator_checkpoint as cp

        monkeypatch.setattr(
            cp, "_checkpoint_dir_for_title", lambda title: str(tmp_path)
        )

        output = MagicMock()
        output.story_draft.title = "Truyện thử"
        output.model_dump_json.return_value = '{"ok": true}'

        mgr = CheckpointManager.__new__(CheckpointManager)
        mgr.output = output

        path = mgr.save(1, background=False)

        assert os.path.exists(path), "the file must exist once save() returns"

    def test_orchestrator_awaits_the_write_not_the_thread_spawn(self):
        import pipeline.orchestrator_layers as layers

        source = open(layers.__file__, encoding="utf-8").read()
        # A bare `await asyncio.to_thread(self.checkpoint.save, N)` returns as
        # soon as the daemon thread is spawned, which is not a durable write.
        assert "self.checkpoint.save, 1)" not in source
        assert "self.checkpoint.save, 2)" not in source
        assert "self.checkpoint.save, 1, background=False)" in source
        assert "self.checkpoint.save, 2, background=False)" in source
