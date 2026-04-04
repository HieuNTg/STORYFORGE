"""Generate AI image prompts from story content."""
import logging
from models.schemas import ImagePrompt, Chapter
from services.llm_client import LLMClient
from config import ConfigManager

logger = logging.getLogger(__name__)

# Prompt tự chứa — không đặt trong prompts.py
_SCENE_EXTRACT_PROMPT = """Trích xuất {num_images} cảnh quan trọng nhất từ chương truyện sau.
Với mỗi cảnh, tạo prompt tiếng Anh cho AI image generation.

NỘI DUNG:
{content}

NHÂN VẬT:
{characters}

STYLE: {style}

Trả về JSON:
{{"scenes": [{{"scene_description": "mô tả cảnh", "dalle_prompt": "English prompt for DALL-E", "sd_prompt": "English prompt for Stable Diffusion", "negative_prompt": "things to avoid", "characters_in_scene": ["char names"]}}]}}"""


class ImagePromptGenerator:
    """Generate AI image prompts from story content."""

    def __init__(self, style: str = ""):
        self.llm = LLMClient()
        self.style = style or ConfigManager().pipeline.image_prompt_style

    def generate_scene_prompt(self, chapter: Chapter) -> str:
        """Generate a single image prompt string for a chapter scene."""
        summary = chapter.summary or chapter.title or f"Chapter {chapter.chapter_number}"
        return f"{self.style} style, {summary}"

    def generate_from_chapter(
        self,
        chapter: Chapter,
        characters: list = None,
        num_images: int = 3,
        visual_profiles: dict = None,
    ) -> list[ImagePrompt]:
        """Extract key scenes from chapter and generate image prompts via LLM.

        Args:
            chapter: The chapter to extract scenes from
            characters: list of Character objects
            num_images: number of image prompts to generate
            visual_profiles: dict of {name: frozen_visual_description} for consistency
        """
        chars_text = ""
        if characters:
            parts = []
            for c in characters:
                desc = c.appearance or c.personality
                # Enhance with visual profile if available
                if visual_profiles and c.name in visual_profiles:
                    desc = visual_profiles[c.name]
                parts.append(f"- {c.name}: {desc}")
            chars_text = "\n".join(parts)

        try:
            result = self.llm.generate_json(
                system_prompt="Bạn là họa sĩ concept art. Trả về JSON.",
                user_prompt=_SCENE_EXTRACT_PROMPT.format(
                    num_images=num_images,
                    content=chapter.content[:3000],
                    characters=chars_text or "Không có thông tin",
                    style=self.style,
                ),
                temperature=0.7,
                max_tokens=1500,
            )
            prompts_list = []
            for i, scene in enumerate(result.get("scenes", [])[:num_images], 1):
                prompts_list.append(
                    ImagePrompt(
                        panel_number=i,
                        chapter_number=chapter.chapter_number,
                        scene_description=scene.get("scene_description", ""),
                        style=self.style,
                        dalle_prompt=scene.get("dalle_prompt", ""),
                        sd_prompt=scene.get("sd_prompt", ""),
                        negative_prompt=scene.get("negative_prompt", ""),
                        characters_in_scene=scene.get("characters_in_scene", []),
                    )
                )
            return prompts_list
        except Exception as e:
            logger.warning(f"Image prompt generation failed for ch {chapter.chapter_number}: {e}")
            return []
