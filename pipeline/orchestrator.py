"""Điều phối pipeline 3 lớp: Tạo truyện → Mô phỏng kịch tính → Video."""

import logging
import json
import os
import re
import time
from datetime import datetime
from typing import Optional

from models.schemas import PipelineOutput, StoryDraft, EnhancedStory
from pipeline.layer1_story.generator import StoryGenerator
from pipeline.layer2_enhance.analyzer import StoryAnalyzer
from pipeline.layer2_enhance.simulator import DramaSimulator
from pipeline.layer2_enhance.enhancer import StoryEnhancer
from pipeline.layer3_video.storyboard import StoryboardGenerator
from config import ConfigManager

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Điều phối toàn bộ pipeline từ input đến output."""

    CHECKPOINT_DIR = "output/checkpoints"

    def __init__(self):
        self.config = ConfigManager()
        self.story_gen = StoryGenerator()
        self.analyzer = StoryAnalyzer()
        self.simulator = DramaSimulator()
        self.enhancer = StoryEnhancer()
        self.storyboard_gen = StoryboardGenerator()
        self.output = PipelineOutput()

    def run_full_pipeline(
        self,
        title: str,
        genre: str,
        idea: str,
        style: str = "Miêu tả chi tiết",
        num_chapters: int = 10,
        num_characters: int = 5,
        word_count: int = 2000,
        num_sim_rounds: int = 5,
        shots_per_chapter: int = 8,
        progress_callback=None,
        stream_callback=None,
        enable_agents: bool = True,
    ) -> PipelineOutput:
        """Chạy toàn bộ pipeline 3 lớp."""

        def _log(msg):
            self.output.logs.append(msg)
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        self.output = PipelineOutput(status="running", current_layer=1)
        draft = None
        enhanced = None
        pipeline_start = time.time()

        # Fail-fast: kiểm tra kết nối trước khi bắt đầu
        from services.llm_client import LLMClient
        ok, msg = LLMClient().check_connection()
        if not ok:
            self.output.status = "error"
            _log(f"❌ Không kết nối được LLM: {msg}")
            return self.output

        # Khởi tạo agents một lần duy nhất
        if enable_agents:
            try:
                from pipeline.agents import register_all_agents
                from pipeline.agents.agent_registry import AgentRegistry
                register_all_agents()
                _log("[AGENTS] Da khoi tao phong ban danh gia.")
            except Exception as e:
                logger.warning(f"Khong the khoi tao agents: {e}")
                enable_agents = False

        _log("══════ LAYER 1: TẠO TRUYỆN ══════")
        self.output.current_layer = 1
        layer_start = time.time()
        try:
            draft = self.story_gen.generate_full_story(
                title=title,
                genre=genre,
                idea=idea,
                style=style,
                num_chapters=num_chapters,
                num_characters=num_characters,
                word_count=word_count,
                progress_callback=lambda m: _log(f"[L1] {m}"),
                stream_callback=stream_callback,
            )
            self.output.story_draft = draft
            self.output.progress = 0.33
            _log(f"⏱️ Layer 1 hoàn tất trong {time.time() - layer_start:.1f}s")
            self._save_checkpoint(1)

            if enable_agents:
                _log("[AGENTS] Phong ban dang danh gia Layer 1...")
                try:
                    reviews = AgentRegistry().run_review_cycle(
                        self.output, layer=1, max_iterations=3,
                        progress_callback=lambda m: _log(m),
                    )
                    self.output.reviews.extend(reviews)
                except Exception as e:
                    logger.warning(f"Agent review Layer 1 loi: {e}")
        except Exception as e:
            self.output.status = "error"
            _log(f"❌ Layer 1 thất bại: {str(e)}")
            logger.exception("Layer 1 error")
            return self.output

        _log("══════ LAYER 2: MÔ PHỎNG TĂNG KỊCH TÍNH ══════")
        self.output.current_layer = 2
        layer_start = time.time()
        try:
            # Phân tích truyện
            _log("[L2] 🔍 Đang phân tích cấu trúc truyện...")
            analysis = self.analyzer.analyze(draft)

            # Mô phỏng tương tác nhân vật
            _log(f"[L2] 🎭 Bắt đầu mô phỏng {num_sim_rounds} vòng...")
            sim_result = self.simulator.run_simulation(
                characters=draft.characters,
                relationships=analysis["relationships"],
                genre=genre,
                num_rounds=num_sim_rounds,
                progress_callback=lambda m: _log(f"[L2] {m}"),
            )
            self.output.simulation_result = sim_result

            # Tăng cường kịch tính
            _log("[L2] ✍️ Đang viết lại truyện với kịch tính cao hơn...")
            enhanced = self.enhancer.enhance_story(
                draft=draft,
                sim_result=sim_result,
                word_count=word_count,
                progress_callback=lambda m: _log(f"[L2] {m}"),
            )
            self.output.enhanced_story = enhanced
            self.output.progress = 0.66
            _log(f"⏱️ Layer 2 hoàn tất trong {time.time() - layer_start:.1f}s")
            self._save_checkpoint(2)

            if enable_agents:
                _log("[AGENTS] Phong ban dang danh gia Layer 2...")
                try:
                    reviews = AgentRegistry().run_review_cycle(
                        self.output, layer=2, max_iterations=3,
                        progress_callback=lambda m: _log(m),
                    )
                    self.output.reviews.extend(reviews)
                except Exception as e:
                    logger.warning(f"Agent review Layer 2 loi: {e}")
        except Exception as e:
            # Layer 2 thất bại: dùng story_draft làm fallback EnhancedStory
            logger.warning(f"Layer 2 thất bại, dùng bản thảo gốc: {e}")
            _log(f"⚠️ Layer 2 lỗi ({str(e)}), tiếp tục với bản thảo gốc.")
            enhanced = EnhancedStory(
                title=draft.title,
                genre=draft.genre,
                chapters=list(draft.chapters),
                enhancement_notes=["Layer 2 skipped due to error"],
                drama_score=0.0,
            )
            self.output.enhanced_story = enhanced
            self.output.progress = 0.66
            self.output.status = "partial"

        _log("══════ LAYER 3: TẠO KỊCH BẢN VIDEO ══════")
        self.output.current_layer = 3
        layer_start = time.time()
        try:
            video_script = self.storyboard_gen.generate_full_video_script(
                story=enhanced,
                characters=draft.characters,
                shots_per_chapter=shots_per_chapter,
                progress_callback=lambda m: _log(f"[L3] {m}"),
            )
            self.output.video_script = video_script
            self.output.progress = 1.0
            if self.output.status != "partial":
                self.output.status = "completed"
            self._save_checkpoint(3)

            if enable_agents:
                _log("[AGENTS] Phong ban dang danh gia Layer 3...")
                try:
                    reviews = AgentRegistry().run_review_cycle(
                        self.output, layer=3, max_iterations=3,
                        progress_callback=lambda m: _log(m),
                    )
                    self.output.reviews.extend(reviews)
                except Exception as e:
                    logger.warning(f"Agent review Layer 3 loi: {e}")

            _log(f"⏱️ Layer 3 hoàn tất trong {time.time() - layer_start:.1f}s")
            _log("🎉 PIPELINE HOÀN TẤT!")
            total_time = time.time() - pipeline_start
            _log(f"📊 Tổng kết: {len(enhanced.chapters)} chương, "
                 f"{len(video_script.panels)} panels video, "
                 f"~{video_script.total_duration_seconds/60:.1f} phút, "
                 f"tổng thời gian: {total_time:.0f}s")
        except Exception as e:
            # Layer 3 thất bại: vẫn có enhanced_story
            logger.warning(f"Layer 3 thất bại: {e}")
            _log(f"⚠️ Layer 3 lỗi ({str(e)}), pipeline dừng sau Layer 2.")
            self.output.status = "partial"

        return self.output

    def run_layer1_only(
        self, title, genre, idea, style, num_chapters, num_characters,
        word_count, progress_callback=None,
    ) -> StoryDraft:
        """Chỉ chạy Layer 1."""
        return self.story_gen.generate_full_story(
            title=title, genre=genre, idea=idea, style=style,
            num_chapters=num_chapters, num_characters=num_characters,
            word_count=word_count, progress_callback=progress_callback,
        )

    def run_layer2_only(
        self, draft: StoryDraft, num_sim_rounds: int = 5,
        word_count: int = 2000, progress_callback=None,
    ) -> EnhancedStory:
        """Chỉ chạy Layer 2 trên bản thảo có sẵn."""
        analysis = self.analyzer.analyze(draft)
        sim_result = self.simulator.run_simulation(
            characters=draft.characters,
            relationships=analysis["relationships"],
            genre=draft.genre,
            num_rounds=num_sim_rounds,
            progress_callback=progress_callback,
        )
        return self.enhancer.enhance_story(
            draft=draft, sim_result=sim_result,
            word_count=word_count, progress_callback=progress_callback,
        )

    def export_output(self, output_dir: str = "output", formats: list = None):
        """Xuất kết quả ra file."""
        if formats is None:
            formats = ["TXT", "Markdown", "JSON"]
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if "TXT" in formats:
            # Xuất truyện gốc
            if self.output.story_draft:
                path = os.path.join(output_dir, f"{timestamp}_draft.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"# {self.output.story_draft.title}\n\n")
                    for ch in self.output.story_draft.chapters:
                        f.write(f"\n## Chương {ch.chapter_number}: {ch.title}\n\n")
                        f.write(ch.content + "\n")

            # Xuất truyện tăng cường
            if self.output.enhanced_story:
                path = os.path.join(output_dir, f"{timestamp}_enhanced.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"# {self.output.enhanced_story.title} (Phiên bản kịch tính)\n\n")
                    for ch in self.output.enhanced_story.chapters:
                        f.write(f"\n## Chương {ch.chapter_number}: {ch.title}\n\n")
                        f.write(ch.content + "\n")

        if "JSON" in formats:
            # Xuất kịch bản video
            if self.output.video_script:
                path = os.path.join(output_dir, f"{timestamp}_video_script.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(
                        self.output.video_script.model_dump(),
                        f, ensure_ascii=False, indent=2,
                    )

            # Xuất log mô phỏng
            if self.output.simulation_result:
                path = os.path.join(output_dir, f"{timestamp}_simulation.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(
                        self.output.simulation_result.model_dump(),
                        f, ensure_ascii=False, indent=2,
                    )

        if "Markdown" in formats:
            self._export_markdown(output_dir, timestamp)

        return output_dir

    def _export_markdown(self, output_dir: str, timestamp: str):
        """Export story as formatted Markdown."""
        story = self.output.enhanced_story or self.output.story_draft
        if not story:
            return
        path = os.path.join(output_dir, f"{timestamp}_story.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {story.title}\n\n")
            if hasattr(story, 'genre'):
                f.write(f"**Thể loại:** {story.genre}\n")
            if hasattr(story, 'drama_score'):
                f.write(f"**Điểm kịch tính:** {story.drama_score:.2f}\n")
            f.write("\n---\n\n")
            for ch in story.chapters:
                f.write(f"## Chương {ch.chapter_number}: {ch.title}\n\n")
                f.write(ch.content + "\n\n")

    def _save_checkpoint(self, layer: int):
        """Save pipeline state after layer completion."""
        os.makedirs(self.CHECKPOINT_DIR, exist_ok=True)
        raw_title = self.output.story_draft.title[:30] if self.output.story_draft else "untitled"
        slug = re.sub(r'[^\w\-]', '_', raw_title)
        path = os.path.join(self.CHECKPOINT_DIR, f"{slug}_layer{layer}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.output.model_dump_json(indent=2))
        logger.info(f"Checkpoint saved: {path}")
        return path

    @classmethod
    def list_checkpoints(cls) -> list:
        """List available checkpoints."""
        if not os.path.exists(cls.CHECKPOINT_DIR):
            return []
        checkpoints = []
        for f in sorted(os.listdir(cls.CHECKPOINT_DIR), reverse=True):
            if f.endswith(".json"):
                path = os.path.join(cls.CHECKPOINT_DIR, f)
                stat = os.stat(path)
                checkpoints.append({
                    "file": f,
                    "path": path,
                    "size_kb": stat.st_size // 1024,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                })
        return checkpoints

    def resume_from_checkpoint(self, checkpoint_path: str, progress_callback=None, enable_agents=True, **kwargs) -> PipelineOutput:
        """Resume pipeline from a saved checkpoint."""
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.output = PipelineOutput(**data)
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
                from pipeline.agents.agent_registry import AgentRegistry
                register_all_agents()
            except Exception as e:
                logger.warning(f"Khong the khoi tao agents: {e}")
                enable_agents = False

        draft = self.output.story_draft
        enhanced = self.output.enhanced_story

        # Resume from appropriate layer
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
                enhanced = self.enhancer.enhance_story(
                    draft=draft, sim_result=sim_result,
                    word_count=kwargs.get("word_count", 2000),
                    progress_callback=lambda m: _log(f"[L2] {m}"),
                )
                self.output.enhanced_story = enhanced
                self.output.progress = 0.66
                self._save_checkpoint(2)
            except Exception as e:
                _log(f"Layer 2 loi: {e}")
                enhanced = EnhancedStory(
                    title=draft.title, genre=draft.genre,
                    chapters=list(draft.chapters),
                    enhancement_notes=["Layer 2 skipped"], drama_score=0.0,
                )
                self.output.enhanced_story = enhanced
                self.output.status = "partial"

        if (last_layer <= 2) and enhanced:
            _log("══════ RESUMING LAYER 3 ══════")
            self.output.current_layer = 3
            try:
                video_script = self.storyboard_gen.generate_full_video_script(
                    story=enhanced,
                    characters=draft.characters if draft else [],
                    shots_per_chapter=kwargs.get("shots_per_chapter", 8),
                    progress_callback=lambda m: _log(f"[L3] {m}"),
                )
                self.output.video_script = video_script
                self.output.progress = 1.0
                if self.output.status != "partial":
                    self.output.status = "completed"
                self._save_checkpoint(3)
                _log("PIPELINE HOAN TAT (resumed)!")
            except Exception as e:
                _log(f"Layer 3 loi: {e}")
                self.output.status = "partial"

        return self.output
