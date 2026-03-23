"""Điều phối pipeline 3 lớp: Tạo truyện → Mô phỏng kịch tính → Video."""

import logging
import json
import os
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
    ) -> PipelineOutput:
        """Chạy toàn bộ pipeline 3 lớp."""

        def _log(msg):
            self.output.logs.append(msg)
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        self.output = PipelineOutput(status="running", current_layer=1)

        try:
            # ═══════════════════════════════════════
            # LAYER 1: TẠO TRUYỆN (create-story)
            # ═══════════════════════════════════════
            _log("══════ LAYER 1: TẠO TRUYỆN ══════")
            self.output.current_layer = 1

            draft = self.story_gen.generate_full_story(
                title=title,
                genre=genre,
                idea=idea,
                style=style,
                num_chapters=num_chapters,
                num_characters=num_characters,
                word_count=word_count,
                progress_callback=lambda m: _log(f"[L1] {m}"),
            )
            self.output.story_draft = draft
            self.output.progress = 0.33

            # ═══════════════════════════════════════
            # LAYER 2: MÔ PHỎNG KỊCH TÍNH (MiroFish)
            # ═══════════════════════════════════════
            _log("══════ LAYER 2: MÔ PHỎNG TĂNG KỊCH TÍNH ══════")
            self.output.current_layer = 2

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

            # ═══════════════════════════════════════
            # LAYER 3: VIDEO / STORYBOARD (waoowaoo)
            # ═══════════════════════════════════════
            _log("══════ LAYER 3: TẠO KỊCH BẢN VIDEO ══════")
            self.output.current_layer = 3

            video_script = self.storyboard_gen.generate_full_video_script(
                story=enhanced,
                characters=draft.characters,
                shots_per_chapter=shots_per_chapter,
                progress_callback=lambda m: _log(f"[L3] {m}"),
            )
            self.output.video_script = video_script
            self.output.progress = 1.0
            self.output.status = "completed"

            _log("🎉 PIPELINE HOÀN TẤT!")
            _log(f"📊 Tổng kết: {len(enhanced.chapters)} chương, "
                 f"{len(video_script.panels)} panels video, "
                 f"~{video_script.total_duration_seconds/60:.1f} phút")

        except Exception as e:
            self.output.status = "error"
            _log(f"❌ Lỗi ở Layer {self.output.current_layer}: {str(e)}")
            logger.exception("Pipeline error")

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

    def export_output(self, output_dir: str = "output"):
        """Xuất kết quả ra file."""
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

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

        return output_dir
