"""Generate AI image prompts from story content."""
import json
import logging
from models.schemas import ImagePrompt, Chapter
from services.llm_client import LLMClient
from config import ConfigManager

logger = logging.getLogger(__name__)

# Prompt tự chứa — không đặt trong prompts.py
_SCENE_EXTRACT_PROMPT = """Trích xuất {num_images} cảnh quan trọng nhất từ chương truyện sau.
Với mỗi cảnh, tạo prompt tiếng Anh cho MỘT KHUNG TRUYỆN TRANH (one comic panel).

LUẬT KHUNG TRUYỆN TRANH:
- Each panel MUST specify a distinct shot type (establishing/wide/medium/close-up/over-the-shoulder/reaction) and vary across the sequence — no two adjacent panels share the same shot type.
- Render NO text inside the image: no speech bubbles, no captions, no signs, no letters, no watermark.
- Style: comic panel, cel shading, bold ink lines (per STYLE below).

NỘI DUNG:
{content}

NHÂN VẬT:
{characters}

STYLE: {style}

Trả về JSON:
{{"scenes": [{{"scene_description": "mô tả cảnh", "shot_type": "establishing|wide|medium|close-up|over-the-shoulder|reaction", "dalle_prompt": "English comic-panel prompt for DALL-E, NO TEXT in image", "sd_prompt": "English comic-panel prompt for Stable Diffusion, NO TEXT in image", "negative_prompt": "things to avoid (always include: text, letters, watermark, caption, speech bubble)", "characters_in_scene": ["char names"]}}]}}"""


class ImagePromptGenerator:
    """Generate AI image prompts from story content."""

    def __init__(self, style: str = ""):
        self.llm = LLMClient()
        self.style = style or ConfigManager().pipeline.image_prompt_style

    def generate_scene_prompt(self, chapter: Chapter) -> str:
        """Generate a single image prompt string for a chapter scene."""
        summary = chapter.summary or chapter.title or f"Chapter {chapter.chapter_number}"
        return f"{self.style} style, {summary}"

    def refine_to_cinematic_prompt(self, text: str) -> str:
        """Rewrite a scene description into ONE comic-panel Imagen prompt.

        Structure: [shot type] + [character action/expression] + [comic art style],
        explicitly carrying a 'no text in image' instruction. (Method name kept as
        ``refine_to_cinematic_prompt`` for callsite/test back-compat — it now emits
        comic-panel prompts, not cinematic hero shots.)
        Returns the refined prompt; on refusal, empty, or error, returns the input
        verbatim — refinement is best-effort and must never block image generation.

        Uses plain-text output (not JSON) on the primary model. The cheap model
        tended to refuse ("can't generate images / are you logged in?") or wrap
        replies in markdown, yielding 0 usable prompts. Framing the task as pure
        text-rewriting and parsing leniently defeats both failure modes.
        """
        system = (
            "You are an image-prompt rewriter. Rewrite the user's scene description "
            "into ONE comic-panel image-generation prompt. You only rewrite text — you "
            "do NOT generate images, log in, or check availability, so never refuse "
            "and never ask questions. "
            "Structure: [shot type: establishing/wide/medium/close-up/"
            "over-the-shoulder/reaction] + [character action/expression] + "
            "[comic art style: cel shading, bold ink lines]. "
            "The image MUST contain NO text — explicitly add 'no text in image, "
            "no speech bubbles, no captions, no watermark'. Under 60 words. "
            "Output ONLY the rewritten prompt as plain text: no JSON, no quotes, no "
            "labels, no commentary."
        )
        try:
            raw = self.llm.generate(
                system_prompt=system,
                user_prompt=text,
                temperature=0.7,
                max_tokens=200,
                model_tier="default",
            )
            return self._clean_refined(raw) or text
        except Exception as e:
            logger.warning("Cinematic refiner failed: %s", e)
            return text

    @staticmethod
    def _clean_refined(raw: str) -> str:
        """Normalize a refiner reply into a usable prompt, or '' if unusable.

        Strips markdown fences / surrounding quotes, unwraps an accidental JSON
        object, and rejects refusals or prompt-echoes so the caller can fall back
        to the original description instead of feeding garbage to the renderer.
        """
        s = (raw or "").strip()
        if not s:
            return ""
        # Strip a ```...``` code fence (with optional language tag)
        if s.startswith("```"):
            s = s.strip("`").strip()
            if s[:4].lower() == "json":
                s = s[4:].strip()
        # Unwrap an accidental JSON object: prefer "prompt", else the longest string
        if s.startswith("{") and s.endswith("}"):
            try:
                obj = json.loads(s)
            except Exception:
                return ""
            if not isinstance(obj, dict):
                return ""
            cand = obj.get("prompt")
            if not isinstance(cand, str) or not cand.strip():
                strings = [v for v in obj.values() if isinstance(v, str)]
                cand = max(strings, key=len) if strings else ""
            s = (cand or "").strip()
        s = s.strip().strip('"').strip("'").strip()
        if not s:
            return ""
        low = s.lower()
        # Reject model refusals (e.g. Gemini "can't generate images / are you logged in?")
        refusal_markers = (
            "đăng nhập", "không thể tạo", "chưa khả dụng", "khả dụng ở vị trí",
            "i can't", "i cannot", "i'm unable", "unable to", "as an ai",
            "logged in", "not available in your",
        )
        if any(m in low for m in refusal_markers):
            return ""
        # Reject echoes of our own enforcement instruction
        if "bắt buộc" in low and "tiếng việt" in low:
            return ""
        return s

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
                expect="dict",
                list_key="scenes",
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
