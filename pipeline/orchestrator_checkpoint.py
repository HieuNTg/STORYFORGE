"""Checkpoint management: save, list, resume pipeline state.

Sprint 3 Task 2 adds per-chapter checkpoint granularity so pipelines can resume
from the last completed chapter on crash/interrupt. Per-chapter files live in a
dedicated subdir and are auto-pruned to keep disk usage bounded.
"""

import hashlib
import json
import logging
import os
import re
import threading
from datetime import datetime

from models.schemas import EnhancedStory, PipelineOutput
from services.output_paths import OUTPUT_ROOT, checkpoints_dir as _story_checkpoints_dir
from services.quality_scorer import QualityScorer

logger = logging.getLogger(__name__)

# Legacy flat checkpoint dir. Checkpoints are now written per-story under
# ``output/<story-slug>/checkpoints/`` (see services.output_paths), but this
# constant is retained as a back-compat *read* location: pre-migration
# installs and the by-filename API lookups still scan it. New writes go through
# ``_checkpoint_dir_for_title``.
# Use a forward slash (not os.path.join) so the public constant keeps its
# historical "output/checkpoints" form on every OS; Windows accepts forward
# slashes for all filesystem calls, so the listdir/isdir reads below are happy.
CHECKPOINT_DIR = f"{OUTPUT_ROOT}/checkpoints"
CHAPTER_CHECKPOINT_SUBDIR = "per_chapter"


def _checkpoint_dir_for_title(title: str) -> str:
    """Per-story checkpoint dir for a story title (the new write location)."""
    return _story_checkpoints_dir(title)


def _all_checkpoint_dirs() -> list[str]:
    """Every directory that may hold layer checkpoints, newest layout first.

    Includes each per-story ``output/<slug>/checkpoints`` plus the legacy flat
    ``output/checkpoints`` so listings and by-filename lookups keep finding
    pre-migration files without a forced migration.

    The per-story scan root is derived from ``CHECKPOINT_DIR``'s parent rather
    than a hard-coded ``OUTPUT_ROOT`` so that tests (and any caller) which patch
    ``CHECKPOINT_DIR`` to an isolated directory redirect the *entire* scan, not
    just the legacy leg. In production ``CHECKPOINT_DIR`` is ``OUTPUT_ROOT/checkpoints``
    so its parent is ``OUTPUT_ROOT`` and behavior is unchanged.
    """
    dirs: list[str] = []
    scan_root = os.path.dirname(CHECKPOINT_DIR) or OUTPUT_ROOT
    try:
        for entry in os.listdir(scan_root):
            cdir = os.path.join(scan_root, entry, "checkpoints")
            if os.path.isdir(cdir):
                dirs.append(cdir)
    except (FileNotFoundError, NotADirectoryError):
        pass
    if os.path.isdir(CHECKPOINT_DIR) and CHECKPOINT_DIR not in dirs:
        dirs.append(CHECKPOINT_DIR)
    return dirs


def _chapter_checkpoint_dir(title: str | None = None) -> str:
    """Per-chapter checkpoint dir. Falls back to legacy flat dir when no title."""
    base = _checkpoint_dir_for_title(title) if title else CHECKPOINT_DIR
    return os.path.join(base, CHAPTER_CHECKPOINT_SUBDIR)


def _all_chapter_checkpoint_dirs() -> list[str]:
    """Every per_chapter dir across stories + the legacy flat per_chapter dir."""
    return [os.path.join(d, CHAPTER_CHECKPOINT_SUBDIR) for d in _all_checkpoint_dirs()]


def find_checkpoint_path(filename: str) -> str | None:
    """Resolve a bare checkpoint filename to its on-disk path.

    The HTTP API addresses checkpoints by bare filename (the layout is an
    implementation detail the frontend never sees). Now that checkpoints live
    in per-story folders, this searches every checkpoint dir (and per_chapter
    subdirs) and returns the first match, so the bare-filename contract holds
    across the new layout and legacy flat files alike.
    """
    if not filename:
        return None
    base = os.path.basename(filename)
    for d in _all_checkpoint_dirs():
        cand = os.path.join(d, base)
        if os.path.isfile(cand):
            return cand
        cand_pc = os.path.join(d, CHAPTER_CHECKPOINT_SUBDIR, base)
        if os.path.isfile(cand_pc):
            return cand_pc
    return None


_CHAPTER_RE = re.compile(
    r"(?P<slug>.+)_ch(?P<ch>\d+)_layer(?P<layer>\d+)(?:_[0-9a-f]+)?\.json$"
)


def _atomic_write_text(path: str, data: str) -> None:
    """Write `data` to `path` atomically.

    Writes to a sibling `.tmp` file (same directory, so `os.replace` stays on one
    filesystem), flushes + fsyncs the bytes to disk, then renames over the final
    path. `os.replace` is atomic on POSIX and Windows, so a crash/SIGKILL during
    a checkpoint write can never leave a torn, half-written JSON file at `path`:
    a reader either sees the previous complete checkpoint or the new complete one.
    On failure the partial tmp file is best-effort removed so it cannot accumulate.
    """
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _prune_chapter_checkpoints(
    out_dir: str, slug: str, layer: int, keep_last: int
) -> None:
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
        raw_title = (
            self.output.story_draft.title if self.output.story_draft else "untitled"
        )
        out_dir = _checkpoint_dir_for_title(raw_title)
        os.makedirs(out_dir, exist_ok=True)
        hash_id = hashlib.sha256(raw_title.encode()).hexdigest()[:16]
        slug = re.sub(r"[^\w\-]", "_", raw_title[:30])
        path = os.path.join(out_dir, f"{slug}_layer{layer}_{hash_id}.json")
        data = self.output.model_dump_json(indent=2)

        def _write():
            try:
                _atomic_write_text(path, data)
                logger.info(f"Checkpoint saved: {path}")
            except Exception as e:
                logger.error(f"Checkpoint save failed: {e}")

        if background:
            threading.Thread(target=_write, daemon=True).start()
        else:
            _write()
        return path

    def save_chapter(
        self, chapter_number: int, layer: int, background: bool = True
    ) -> str:
        """Sprint 3 Task 2: save pipeline state after a single chapter completes.

        Writes to output/checkpoints/per_chapter/{slug}_ch{N}_layer{L}.json.
        Caller is responsible for gating on config.enable_chapter_checkpoint — this
        method always writes when called. Returns the written path.

        After writing, prunes older per-chapter files beyond `keep_last` (caller
        passes this via the manager's state or it defaults to 5).
        """
        raw_title = (
            self.output.story_draft.title if self.output.story_draft else "untitled"
        )
        out_dir = _chapter_checkpoint_dir(raw_title)
        os.makedirs(out_dir, exist_ok=True)
        hash_id = hashlib.sha256(raw_title.encode()).hexdigest()[:16]
        slug = re.sub(r"[^\w\-]", "_", raw_title[:30])
        path = os.path.join(
            out_dir, f"{slug}_ch{chapter_number}_layer{layer}_{hash_id}.json"
        )
        data = self.output.model_dump_json(indent=2)
        keep_last = getattr(self, "_chapter_keep_last", 5)

        def _write():
            try:
                _atomic_write_text(path, data)
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
    def list_chapter_checkpoints(
        slug: str | None = None, layer: int | None = None
    ) -> list:
        """Return per-chapter checkpoint descriptors, newest-first.

        Filters by slug and/or layer when provided. Parses `{slug}_ch{N}_layer{L}.json`.
        Scans every per-story per_chapter dir plus the legacy flat dir.
        """
        entries = []
        seen: set[str] = set()
        for out_dir in _all_chapter_checkpoint_dirs():
            if not os.path.exists(out_dir):
                continue
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
                if fname in seen:
                    continue
                seen.add(fname)
                path = os.path.join(out_dir, fname)
                stat = os.stat(path)
                entries.append(
                    {
                        "file": fname,
                        "path": path,
                        "slug": f_slug,
                        "chapter": f_ch,
                        "layer": f_layer,
                        "size_kb": stat.st_size // 1024,
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                    }
                )
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
            raise ValueError(
                f"Per-chapter checkpoint corrupted or incompatible: {e}"
            ) from e

        enhanced = self.output.enhanced_story
        draft = self.output.story_draft
        if enhanced and getattr(enhanced, "chapters", None):
            last = max(c.chapter_number for c in enhanced.chapters)
        elif draft and getattr(draft, "chapters", None):
            last = max(c.chapter_number for c in draft.chapters)
        else:
            last = 0
        next_ch = last + 1
        logger.info(
            f"Resuming from chapter checkpoint {checkpoint_path}: next_chapter={next_ch}"
        )
        return self.output, next_ch

    @staticmethod
    def list_checkpoints() -> list:
        """List available checkpoints sorted newest-first with metadata.

        Scans every per-story ``output/<slug>/checkpoints`` plus the legacy flat
        ``output/checkpoints``. Files are de-duplicated by basename (the
        bare-filename API contract assumes basenames are unique).
        """
        checkpoints = []
        seen: set[str] = set()
        listing: list[tuple[str, str]] = []
        for cdir in _all_checkpoint_dirs():
            try:
                for f in os.listdir(cdir):
                    listing.append((f, os.path.join(cdir, f)))
            except FileNotFoundError:
                continue
        for f, path in sorted(listing, key=lambda t: t[0], reverse=True):
            if f.endswith((".usage.json", ".history.json")):
                continue  # advisory sidecars co-located with checkpoints, not stories
            if f.endswith(".json") and not os.path.isdir(path):
                if f in seen:
                    continue
                seen.add(f)
                stat = os.stat(path)
                entry = {
                    "file": f,
                    "path": path,
                    "size_kb": stat.st_size // 1024,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    "title": "",
                    "genre": "",
                    "chapter_count": 0,
                    "current_layer": 0,
                    "outline_count": 0,
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
                    # Outline length doubles as the original target chapter count —
                    # used by /pipeline/checkpoints to derive the "interrupted" flag.
                    outlines = draft.get("outlines") or []
                    entry["outline_count"] = len(outlines)
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
                    draft=draft,
                    sim_result=sim_result,
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
                    title=draft.title,
                    genre=draft.genre,
                    chapters=list(draft.chapters),
                    enhancement_notes=["Layer 2 skipped"],
                    drama_score=0.0,
                )
                self.output.enhanced_story = enhanced
                self.output.status = "partial"

        if last_layer <= 2 and enhanced:
            self.output.progress = 1.0
            if self.output.status != "partial":
                self.output.status = "completed"
            _log("PIPELINE HOÀN TẤT (resumed)!")

        return self.output
