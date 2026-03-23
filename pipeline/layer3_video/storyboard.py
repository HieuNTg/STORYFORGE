"""Layer 3: Tạo storyboard và kịch bản video - Lấy cảm hứng từ waoowaoo."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from models.schemas import (
    EnhancedStory, Chapter, StoryboardPanel, VoiceLine,
    VideoScript, ShotType, Character,
)
from services.llm_client import LLMClient
from services import prompts
from pipeline.layer3_video._locations import generate_location_prompts
from config import ConfigManager

logger = logging.getLogger(__name__)


class StoryboardGenerator:
    """Chuyển truyện thành storyboard và kịch bản video."""

    def __init__(self):
        self.llm = LLMClient()

    def generate_chapter_storyboard(
        self,
        chapter: Chapter,
        characters: list[Character],
        num_shots: int = 8,
    ) -> list[StoryboardPanel]:
        """Tạo storyboard cho một chương."""
        chars_text = "\n".join(
            f"- {c.name}: {c.appearance or c.personality}" for c in characters
        )

        result = self.llm.generate_json(
            system_prompt=(
                "Bạn là đạo diễn phim chuyên chuyển thể truyện thành phim ngắn. "
                "Trả về JSON."
            ),
            user_prompt=prompts.GENERATE_STORYBOARD.format(
                chapter_content=chapter.content[:4000],
                characters=chars_text,
                locations="Dựa trên nội dung chương",
                num_shots=num_shots,
            ),
        )

        panels = []
        for p in result.get("panels", []):
            try:
                shot_type_str = p.get("shot_type", "trung_cảnh")
                try:
                    shot_type = ShotType(shot_type_str)
                except ValueError:
                    shot_type = ShotType.MEDIUM

                panel = StoryboardPanel(
                    panel_number=p.get("panel_number", len(panels) + 1),
                    chapter_number=chapter.chapter_number,
                    shot_type=shot_type,
                    description=p.get("description", ""),
                    camera_movement=p.get("camera_movement", "tĩnh"),
                    dialogue=p.get("dialogue", ""),
                    narration=p.get("narration", ""),
                    mood=p.get("mood", ""),
                    characters_in_frame=p.get("characters_in_frame", []),
                    duration_seconds=p.get("duration_seconds", 5.0),
                    image_prompt=p.get("image_prompt", ""),
                    sound_effect=p.get("sound_effect", ""),
                )
                panels.append(panel)
            except Exception as e:
                logger.warning(f"Lỗi parse panel: {e}")
                continue

        return panels

    def generate_voice_script(
        self,
        panels: list[StoryboardPanel],
        characters: list[Character],
    ) -> tuple[list[VoiceLine], dict[str, str]]:
        """Tạo kịch bản lồng tiếng. Trả về (voice_lines, voice_descriptions)."""
        storyboard_text = "\n".join(
            f"Panel {p.panel_number}: [{p.shot_type.value}] {p.description}"
            + (f"\n  Thoại: {p.dialogue}" if p.dialogue else "")
            + (f"\n  Kể: {p.narration}" if p.narration else "")
            for p in panels
        )
        chars_text = "\n".join(
            f"- {c.name} ({c.role}): {c.personality}" for c in characters
        )

        result = self.llm.generate_json(
            system_prompt="Bạn là đạo diễn lồng tiếng. Trả về JSON.",
            user_prompt=prompts.GENERATE_VOICE_SCRIPT.format(
                storyboard=storyboard_text,
                characters=chars_text,
            ),
        )

        voice_lines = []
        for vl in result.get("voice_lines", []):
            try:
                voice_lines.append(VoiceLine(
                    character=vl.get("character", "người_kể_chuyện"),
                    text=vl.get("text", ""),
                    emotion=vl.get("emotion", "bình thường"),
                    panel_number=vl.get("panel_number", 0),
                ))
            except Exception:
                continue

        voice_descs = result.get("character_voice_descriptions", {})
        return voice_lines, voice_descs

    def generate_character_prompts(
        self, characters: list[Character], genre: str,
    ) -> dict[str, dict]:
        """Tạo image prompt cho từng nhân vật (parallel)."""
        max_workers = ConfigManager().llm.max_parallel_workers
        char_prompts = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for c in characters:
                future = executor.submit(
                    self.llm.generate_json,
                    system_prompt="Bạn là artist director. Trả về JSON.",
                    user_prompt=prompts.CHARACTER_IMAGE_PROMPT.format(
                        name=c.name,
                        appearance=c.appearance or c.personality,
                        personality=c.personality,
                        genre=genre,
                    ),
                )
                futures[future] = c.name
            for future in as_completed(futures):
                name = futures[future]
                try:
                    char_prompts[name] = future.result()
                except Exception as e:
                    logger.warning(f"Lỗi tạo prompt cho {name}: {e}")
        return char_prompts

    def generate_full_video_script(
        self,
        story: EnhancedStory,
        characters: list[Character],
        shots_per_chapter: int = 8,
        progress_callback=None,
    ) -> VideoScript:
        """Tạo kịch bản video hoàn chỉnh cho toàn bộ truyện."""

        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        script = VideoScript(title=story.title)

        # Tạo image prompt cho nhân vật
        _log("🎨 Đang tạo mô tả hình ảnh nhân vật...")
        char_prompts = self.generate_character_prompts(characters, story.genre)
        script.character_descriptions = {
            name: data.get("image_prompt", "")
            for name, data in char_prompts.items()
        }

        # Tạo storyboard cho từng chương (parallel)
        _log(f"🎬 Đang tạo storyboard {len(story.chapters)} chương (parallel)...")
        max_workers = ConfigManager().llm.max_parallel_workers
        all_panels_map = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self.generate_chapter_storyboard, chapter, characters, shots_per_chapter
                ): chapter.chapter_number
                for chapter in story.chapters
            }
            for future in as_completed(futures):
                ch_num = futures[future]
                try:
                    all_panels_map[ch_num] = future.result()
                    _log(f"🎬 Storyboard chương {ch_num} xong")
                except Exception as e:
                    logger.warning(f"Lỗi storyboard chương {ch_num}: {e}")
                    all_panels_map[ch_num] = []

        # Maintain chapter order
        all_panels = []
        for chapter in story.chapters:
            all_panels.extend(all_panels_map.get(chapter.chapter_number, []))

        script.panels = all_panels

        # Tạo location prompts + voice script song song (cả hai cần panels, độc lập nhau)
        _log("🗺️🎙️ Đang tạo địa điểm + lồng tiếng (parallel)...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            loc_future = executor.submit(
                generate_location_prompts, self.llm, all_panels, [], story.genre,
            )
            voice_future = executor.submit(
                self.generate_voice_script, all_panels, characters,
            )
            script.location_descriptions = loc_future.result()
            voice_lines, voice_descs = voice_future.result()
        script.voice_lines = voice_lines

        # Tính tổng thời lượng
        script.total_duration_seconds = sum(p.duration_seconds for p in all_panels)

        _log(
            f"✅ Layer 3 hoàn tất! {len(all_panels)} panels, "
            f"{len(voice_lines)} dòng thoại, "
            f"{len(script.location_descriptions)} địa điểm, "
            f"~{script.total_duration_seconds/60:.1f} phút"
        )
        return script
