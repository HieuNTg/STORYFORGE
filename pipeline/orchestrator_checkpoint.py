"""Checkpoint management: save, list, resume pipeline state.

Sprint 3 Task 2 adds per-chapter checkpoint granularity so pipelines can resume
from the last completed chapter on crash/interrupt. Per-chapter files live in a
dedicated subdir and are auto-pruned to keep disk usage bounded.
"""

import json
import logging
import os
import re
import threading
from datetime import datetime

from models.schemas import EnhancedStory, PipelineOutput
from services.quality_scorer import QualityScorer

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = "output/checkpoints"
CHAPTER_CHECKPOINT_SUBDIR = "per_chapter"


def _chapter_checkpoint_dir() -> str:
    return os.path.join(CHECKPOINT_DIR, CHAPTER_CHECKPOINT_SUBDIR)


_CHAPTER_RE = re.compile(r"(?P<slug>.+)_ch(?P<ch>\d+)_layer(?P<layer>\d+)\.json$")


def _prune_chapter_checkpoints(out_dir: str, slug: str, layer: int, keep_last: int) -> None:
    """Keep newest `keep_last` files matching {slug}_ch*_layer{layer}.json; delete older."""
    if keep_last <= 0:
        return
    try:
        matches = []
        for fname in os.listdir(out_dir):
            m = _CHAPTER_RE.match(fname)
            if not m or m.group("slug") != slug or int(m.group("layer")) != layer:
                continue
            path = os.path.join(out_dir, fname)
            matches.append((os.path.getmtime(path), path))
        matches.sort(reverse=True)
        for _, path in matches[keep_last:]:
            try:
                os.remove(path)
            except OSError as e:
                logger.warning(f"Prune failed for {path}: {e}")
    except FileNotFoundError:
        return


class CheckpointManager:
    """Saves/loads/resumes PipelineOutput checkpoints."""

    def __init__(
        self,
        output: PipelineOutput,
        analyzer,
        simulator,
        enhancer,
    ):
        self.output = output
        self.analyzer = analyzer
        self.simulator = simulator
        self.enhancer = enhancer

    def save(self, layer: int, background: bool = True) -> str:
        """Save pipeline state after layer completion. Non-blocking by default."""
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)
        raw_title = self.output.story_draft.title[:30] if self.output.story_draft else "untitled"
        slug = re.sub(r"[^\w\-]", "_", raw_title)
        path = os.path.join(CHECKPOINT_DIR, f"{slug}_layer{layer}.json")
        data = self.output.model_dump_json(indent=2)

        def _write():
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(data)
                logger.info(f"Checkpoint saved: {path}")
            except Exception as e:
                logger.error(f"Checkpoint save failed: {e}")

        if background:
            threading.Thread(target=_write, daemon=True).start()
        else:
            _write()
        return path

    def save_chapter(self, chapter_number: int, layer: int, background: bool = True) -> str:
        """Sprint 3 Task 2: save pipeline state after a single chapter completes.

        Writes to output/checkpoints/per_chapter/{slug}_ch{N}_layer{L}.json.
        Caller is responsible for gating on config.enable_chapter_checkpoint — this
        method always writes when called. Returns the written path.

        After writing, prunes older per-chapter files beyond `keep_last` (caller
        passes this via the manager's state or it defaults to 5).
        """
        out_dir = _chapter_checkpoint_dir()
        os.makedirs(out_dir, exist_ok=True)
        raw_title = self.output.story_draft.title[:30] if self.output.story_draft else "untitled"
        slug = re.sub(r"[^\w\-]", "_", raw_title)
        path = os.path.join(out_dir, f"{slug}_ch{chapter_number}_layer{layer}.json")
        data = self.output.model_dump_json(indent=2)
        keep_last = getattr(self, "_chapter_keep_last", 5)

        def _write():
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(data)
                logger.info(f"Chapter checkpoint saved: {path}")
                _prune_chapter_checkpoints(out_dir, slug, layer, keep_last)
            except Exception as e:
                logger.error(f"Chapter checkpoint save failed: {e}")

        if background:
            threading.Thread(target=_write, daemon=True).start()
        else:
            _write()
        return path

    @staticmethod
    def list_chapter_checkpoints(slug: str | None = None, layer: int | None = None) -> list:
        """Return per-chapter checkpoint descriptors, newest-first.

        Filters by slug and/or layer when provided. Parses `{slug}_ch{N}_layer{L}.json`.
        """
        out_dir = _chapter_checkpoint_dir()
        if not os.path.exists(out_dir):
            return []
        entries = []
        for fname in os.listdir(out_dir):
            m = _CHAPTER_RE.match(fname)
            if not m:
                continue
            f_slug = m.group("slug")
            f_ch = int(m.group("ch"))
            f_layer = int(m.group("layer"))
            if slug is not None and f_slug != slug:
                continue
            if layer is not None and f_layer != layer:
                continue
            path = os.path.join(out_dir, fname)
            stat = os.stat(path)
            entries.append({
                "file": fname,
                "path": path,
                "slug": f_slug,
                "chapter": f_ch,
                "layer": f_layer,
                "size_kb": stat.st_size // 1024,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
        entries.sort(key=lambda e: (e["layer"], e["chapter"]), reverse=True)
        return entries

    def resume_from_chapter(self, checkpoint_path: str) -> tuple[PipelineOutput, int]:
        """Sprint 3 Task 2: load a per-chapter checkpoint and derive the next chapter number.

        Returns `(output, next_chapter_number)`. `next_chapter_number` is the chapter
        index to resume writing/enhancing from. Derivation rules:
          - If enhanced_story has chapters → next = max(enhanced ch#) + 1 (L2 resume)
          - Else if story_draft has chapters → next = max(draft ch#) + 1 (L1 resume)
          - Else next = 1
        """
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.output = PipelineOutput(**data)
        except Exception as e:
            raise ValueError(f"Per-chapter checkpoint corrupted or incompatible: {e}") from e

        enhanced = self.output.enhanced_story
        draft = self.output.story_draft
        if enhanced and getattr(enhanced, "chapters", None):
            last = max(c.chapter_number for c in enhanced.chapters)
        elif draft and getattr(draft, "chapters", None):
            last = max(c.chapter_number for c in draft.chapters)
        else:
            last = 0
        next_ch = last + 1
        logger.info(f"Resuming from chapter checkpoint {checkpoint_path}: next_chapter={next_ch}")
        return self.output, next_ch

    @staticmethod
    def list_checkpoints() -> list:
        """List available checkpoints sorted newest-first with metadata."""
        if not os.path.exists(CHECKPOINT_DIR):
            return []
        checkpoints = []
        for f in sorted(os.listdir(CHECKPOINT_DIR), reverse=True):
            if f.endswith(".json"):
                path = os.path.join(CHECKPOINT_DIR, f)
                stat = os.stat(path)
                entry = {
                    "file": f,
                    "path": path,
                    "size_kb": stat.st_size // 1024,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "title": "",
                    "genre": "",
                    "chapter_count": 0,
                    "current_layer": 0,
                }
                # Extract metadata from checkpoint JSON (partial read)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    draft = data.get("story_draft") or {}
                    enhanced = data.get("enhanced_story") or {}
                    entry["title"] = draft.get("title", "") or enhanced.get("title", "")
                    entry["genre"] = draft.get("genre", "")
                    chapters = enhanced.get("chapters") or draft.get("chapters") or []
                    entry["chapter_count"] = len(chapters)
                    entry["current_layer"] = data.get("current_layer", 0)
                except Exception:
                    pass
                checkpoints.append(entry)
        return checkpoints

    def resume(
        self,
        checkpoint_path: str,
        progress_callback=None,
        enable_agents: bool = True,
        enable_scoring: bool = True,
        **kwargs,
    ) -> PipelineOutput:
        """Resume pipeline from a saved checkpoint."""
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.output = PipelineOutput(**data)
        except (json.JSONDecodeError, Exception) as e:
            raise ValueError(f"Checkpoint corrupted or incompatible: {e}") from e
        last_layer = self.output.current_layer

        def _log(msg):
            self.output.logs.append(msg)
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        _log(f"Resuming from checkpoint: layer {last_layer}")

        if enable_agents:
            try:
                from pipeline.agents import register_all_agents
                register_all_agents()
            except Exception as e:
                logger.warning(f"Không thể khởi tạo agents: {e}")
                enable_agents = False

        draft = self.output.story_draft
        enhanced = self.output.enhanced_story

        if last_layer <= 1 and draft:
            _log("══════ RESUMING LAYER 2 ══════")
            self.output.current_layer = 2
            try:
                analysis = self.analyzer.analyze(draft)
                sim_result = self.simulator.run_simulation(
                    characters=draft.characters,
                    relationships=analysis["relationships"],
                    genre=draft.genre,
                    num_rounds=kwargs.get("num_sim_rounds", 5),
                    progress_callback=lambda m: _log(f"[L2] {m}"),
                )
                self.output.simulation_result = sim_result
                enhanced = self.enhancer.enhance_with_feedback(
                    draft=draft, sim_result=sim_result,
                    word_count=kwargs.get("word_count", 2000),
                    progress_callback=lambda m: _log(f"[L2] {m}"),
                )
                self.output.enhanced_story = enhanced
                self.output.progress = 0.66
                self.save(2)

                if enable_scoring:
                    try:
                        scorer = QualityScorer()
                        l2_score = scorer.score_story(enhanced.chapters, layer=2)
                        self.output.quality_scores.append(l2_score)
                        _log(f"[METRICS] Layer 2: {l2_score.overall:.1f}/5")
                    except Exception as e:
                        logger.warning(f"Quality scoring failed: {e}")
            except Exception as e:
                _log(f"Layer 2 lỗi: {e}")
                enhanced = EnhancedStory(
                    title=draft.title, genre=draft.genre,
                    chapters=list(draft.chapters),
                    enhancement_notes=["Layer 2 skipped"], drama_score=0.0,
                )
                self.output.enhanced_story = enhanced
                self.output.status = "partial"

        if last_layer <= 2 and enhanced:
            self.output.progress = 1.0
            if self.output.status != "partial":
                self.output.status = "completed"
            _log("PIPELINE HOÀN TẤT (resumed)!")

        return self.output
