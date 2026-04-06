"""Checkpoint management: save, list, resume pipeline state."""

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
