"""Generate AI image prompts from story content."""

import logging
from models.schemas import ImagePrompt, Chapter
from services.llm_client import LLMClient
from services.media._util import COLOR_CLAUSE, MONOCHROME_NEGATIVES
from services.media.shot_list import CONTENT_WINDOW
from config import ConfigManager

logger = logging.getLogger(__name__)

# Prompt tự chứa — không đặt trong prompts.py
_SCENE_EXTRACT_PROMPT = """Trích xuất {num_images} cảnh quan trọng nhất từ chương truyện sau.
Với mỗi cảnh, tạo prompt tiếng Anh cho MỘT KHUNG TRUYỆN TRANH (one comic panel).

LUẬT KHUNG TRUYỆN TRANH:
- Each panel MUST specify a distinct shot type (establishing/wide/medium/close-up/over-the-shoulder/reaction) and vary across the sequence — no two adjacent panels share the same shot type.
- Render NO text inside the image: no speech bubbles, no captions, no signs, no letters, no watermark.
- Style: comic panel, cel shading, bold ink lines (per STYLE below).
- Every prompt MUST be FULL COLOUR: end each prompt with "full color, rich vibrant color palette". Never ask for monochrome, grayscale, black-and-white or uncolored lineart.

NỘI DUNG:
{content}

NHÂN VẬT:
{characters}

STYLE: {style}

Trả về JSON:
{{"scenes": [{{"scene_description": "mô tả cảnh", "shot_type": "establishing|wide|medium|close-up|over-the-shoulder|reaction", "dalle_prompt": "English comic-panel prompt for DALL-E, NO TEXT in image", "sd_prompt": "English comic-panel prompt for Stable Diffusion, NO TEXT in image", "negative_prompt": "things to avoid (always include: text, letters, watermark, caption, speech bubble, monochrome, grayscale, black and white)", "characters_in_scene": ["char names"]}}]}}"""


# Shot-list panel → polished English image prompt (one per panel, 1:1 aligned).
# Used when the Phase-2 shot-list succeeded: prompts derive from the SAME beats
# the compositor letters, so the picture matches the dialogue on it (the legacy
# _SCENE_EXTRACT_PROMPT extracts scenes independently and only index-aligns).
_PANEL_PROMPT_GEN = """Bạn là đạo diễn hình ảnh truyện tranh. Viết prompt tạo ảnh TIẾNG ANH cho TỪNG panel trong danh sách dưới đây — một prompt mỗi panel, đúng thứ tự, đủ {num_panels} prompt.

LUẬT:
- Cấu trúc mỗi prompt: [shot type + góc máy] + [nhân vật: lặp lại NGUYÊN VĂN mô tả ngoại hình trong mục NHÂN VẬT, không diễn đạt lại] + [MỘT hành động cụ thể, thì hiện tại] + [bối cảnh] + [ánh sáng / mood] + [STYLE] + [màu sắc].
- Ảnh phải CÓ MÀU: mỗi prompt nêu rõ bảng màu của cảnh (ví dụ "warm amber lantern light against deep blue night") và kết thúc bằng "full color, rich vibrant color palette". Không bao giờ yêu cầu monochrome / grayscale / black-and-white / uncolored lineart.
- Khái niệm trừu tượng trong beat (khế ước, sợi chỉ sinh mệnh, thiên đạo, linh hồn...) phải hiện ra như hình ảnh cụ thể đúng theo mô tả trong action/setting của panel — dùng lại cùng một ẩn dụ thị giác ở mọi panel có cùng khái niệm.
- Composition: single focal point; leave empty space near the top of the frame for speech balloons.
- Diễn đạt mọi ràng buộc theo hướng KHẲNG ĐỊNH (positive phrasing); prompt đủ chi tiết để AI vẽ được ngay.
- Ảnh KHÔNG chứa chữ: kết thúc mỗi prompt bằng "no text in image, no speech bubbles, no captions, no watermark".

PANELS:
{panels}

NHÂN VẬT:
{characters}

STYLE: {style}

Trả về JSON:
{{"prompts": [{{"n": 1, "dalle_prompt": "English comic-panel prompt", "sd_prompt": "English comic-panel prompt"}}]}}"""

# Shot code → English shot phrase, for the deterministic fallback prompt.
_SHOT_PHRASE = {
    "EWS": "extreme wide establishing shot",
    "WS": "wide shot",
    "MS": "medium shot",
    "CU": "close-up",
    "ECU": "extreme close-up",
    "OTS": "over-the-shoulder shot",
    "INSERT": "insert detail shot",
    "REACTION": "reaction close-up",
}


class ImagePromptGenerator:
    """Generate AI image prompts from story content."""

    def __init__(self, style: str = ""):
        self.llm = LLMClient()
        self.style = style or ConfigManager().pipeline.image_prompt_style

    def generate_scene_prompt(self, chapter: Chapter) -> str:
        """Generate a single image prompt string for a chapter scene."""
        summary = (
            chapter.summary or chapter.title or f"Chapter {chapter.chapter_number}"
        )
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
                    # Same window as the shot-list extractor: the old 3000-char
                    # cut truncated a typical chapter in half, so half its
                    # scenes could never be picked.
                    content=(chapter.content or "")[:CONTENT_WINDOW],
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
            logger.warning(
                f"Image prompt generation failed for ch {chapter.chapter_number}: {e}"
            )
            return []

    def generate_from_shot_list(
        self,
        shot_list,
        chapter: Chapter,
        characters: list = None,
        visual_profiles: dict = None,
    ) -> list[ImagePrompt]:
        """Generate one ImagePrompt per shot-list panel, 1:1 in reading order.

        Unlike ``generate_from_chapter`` (which extracts scenes from prose
        independently of the shot-list and is only index-aligned afterwards),
        this derives every image prompt from the SAME panel beats the Phase-3
        compositor letters — so the picture on a panel matches the dialogue
        drawn over it, and panels inserted by the coverage check get images.

        Best-effort: any LLM failure (or a panel the LLM skipped) falls back to
        a deterministic prompt assembled from the panel's own fields, so this
        never returns fewer prompts than panels (and never blocks image gen).
        Returns [] only when the shot-list has no panels.
        """
        panels = shot_list.all_panels()
        if not panels:
            return []

        chars_text = ""
        if characters:
            parts = []
            for c in characters:
                desc = c.appearance or c.personality
                if visual_profiles and c.name in visual_profiles:
                    desc = visual_profiles[c.name]
                parts.append(f"- {c.name}: {desc}")
            chars_text = "\n".join(parts)

        panel_lines = []
        for i, p in enumerate(panels, 1):
            panel_lines.append(
                f"{i}. [{p.shot}] {p.beat} | camera: {p.camera} | action: {p.action}"
                f" | setting: {p.setting} | mood: {p.mood} | subject: {p.subject}"
            )

        by_n: dict[int, dict] = {}
        try:
            result = self.llm.generate_json(
                system_prompt="Bạn là đạo diễn hình ảnh truyện tranh. Trả về JSON.",
                user_prompt=_PANEL_PROMPT_GEN.format(
                    num_panels=len(panels),
                    panels="\n".join(panel_lines),
                    characters=chars_text or "Không có thông tin",
                    style=self.style,
                ),
                temperature=0.6,
                max_tokens=min(8000, 300 * len(panels) + 500),
                expect="dict",
                list_key="prompts",
            )
            for item in (result or {}).get("prompts", []) or []:
                if isinstance(item, dict):
                    try:
                        by_n[int(item.get("n", 0) or 0)] = item
                    except (TypeError, ValueError):
                        continue
        except Exception as e:
            logger.warning(
                "Panel prompt generation failed for ch %s, using fallback prompts: %s",
                chapter.chapter_number,
                e,
            )

        descriptors = visual_profiles or {}
        prompts_list = []
        for i, p in enumerate(panels, 1):
            item = by_n.get(i, {})
            dalle = str(item.get("dalle_prompt", "") or "").strip()
            sd = str(item.get("sd_prompt", "") or "").strip()
            if not dalle and not sd:
                dalle = sd = self._fallback_panel_prompt(
                    p, descriptors.get(p.subject, "")
                )
            prompts_list.append(
                ImagePrompt(
                    panel_number=i,
                    chapter_number=chapter.chapter_number,
                    scene_description=p.beat or p.action,
                    style=self.style,
                    dalle_prompt=dalle or sd,
                    sd_prompt=sd or dalle,
                    negative_prompt=(
                        "text, letters, watermark, caption, speech bubble, "
                        + MONOCHROME_NEGATIVES
                    ),
                    characters_in_scene=[p.subject] if p.subject else [],
                )
            )
        return prompts_list

    def _fallback_panel_prompt(self, panel, descriptor: str = "") -> str:
        """Deterministic panel prompt from the panel's own fields (no LLM)."""
        bits = [_SHOT_PHRASE.get((panel.shot or "").upper(), "medium shot")]
        if descriptor:
            bits.append(descriptor)
        elif panel.subject:
            bits.append(panel.subject)
        for field in (panel.action, panel.setting):
            if field:
                bits.append(field)
        if panel.mood:
            bits.append(f"{panel.mood} mood")
        if self.style:
            bits.append(self.style)
        bits.append(
            "comic panel, single focal point, empty space near the top for "
            "speech balloons, " + COLOR_CLAUSE + ", no text in image, "
            "no speech bubbles, no captions, no watermark"
        )
        return ", ".join(b for b in bits if b)
