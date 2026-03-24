"""Generate narration scripts for text-to-speech."""
import logging
import os
from typing import Union
from models.schemas import Chapter, StoryDraft, EnhancedStory

logger = logging.getLogger(__name__)

# Prompt tạo kịch bản voice-over
_TTS_PROMPT = """Chuyen chuong truyen sau thanh kich ban doc voice-over.
Format:
[Nguoi ke] (giong binh thuong) "loi ke"
[Ten nhan vat] (cam xuc) "loi thoai"
[PAUSE 2s]

NOI DUNG CHUONG {chapter_number} - {title}:
{content}

Viet kich ban doc:"""


class TTSScriptGenerator:
    """Generate narration scripts for text-to-speech."""

    def __init__(self):
        from services.llm_client import LLMClient
        self.llm = LLMClient()

    def generate_narration(self, chapter: Chapter) -> str:
        """Generate narration script with emotion markers for a chapter."""
        try:
            result = self.llm.generate(
                system_prompt="Ban la dao dien long tieng chuyen nghiep. Viet kich ban doc.",
                user_prompt=_TTS_PROMPT.format(
                    chapter_number=chapter.chapter_number,
                    title=chapter.title,
                    content=chapter.content[:4000],
                ),
                temperature=0.6,
                max_tokens=3000,
            )
            return result
        except Exception as e:
            logger.warning(f"TTS generation failed for ch {chapter.chapter_number}: {e}")
            return ""

    def generate_full_script(self, story: Union[StoryDraft, EnhancedStory]) -> str:
        """Generate narration for entire story."""
        scripts = []
        for ch in story.chapters:
            script = self.generate_narration(ch)
            if script:
                scripts.append(f"=== CHUONG {ch.chapter_number}: {ch.title} ===\n\n{script}")
        return "\n\n".join(scripts)

    def export_script(self, script: str, output_path: str) -> str:
        """Save narration script to file."""
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(script)
            logger.info(f"TTS script exported: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"TTS export failed: {e}")
            return ""
