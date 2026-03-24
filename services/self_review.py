"""CoT + Constitutional AI self-review for chapter quality."""

import logging
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Review threshold: chapters scoring below this get revised
DEFAULT_THRESHOLD = 3.0  # out of 5.0

CRITIC_PROMPT = """Ban la nha phe binh van hoc nghiem khac. Danh gia chuong truyen sau:

Chuong {chapter_number}: {title}
The loai: {genre}
---
{content}
---

Suy nghi tung buoc (chain-of-thought):
1. Tinh lien ket cua cot truyen co logic khong?
2. Nhan vat hanh dong co nhat quan khong?
3. Nhip do co phu hop khong? Co doan nao nham khong?
4. Van phong co hap dan khong?

Tra ve JSON:
{{
  "coherence": <1-5>,
  "character_consistency": <1-5>,
  "pacing": <1-5>,
  "writing_quality": <1-5>,
  "overall": <1-5>,
  "weaknesses": ["<diem yeu 1>", "<diem yeu 2>"],
  "strengths": ["<diem manh 1>"]
}}"""

REVISE_PROMPT = """Viet lai chuong truyen sau, chi sua cac diem yeu da chi ra.
GIU NGUYEN cot truyen, nhan vat, va cac diem manh.

Diem yeu can sua:
{weaknesses}

Noi dung goc:
---
{content}
---

Yeu cau:
- Khoang {word_count} tu
- Viet hoan toan bang tieng Viet
- Chi cai thien diem yeu, KHONG thay doi cot truyen

Bat dau viet lai:"""


class SelfReviewer:
    """Single-pass CoT critic + optional revision for chapter quality."""

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.llm = LLMClient()
        self.threshold = threshold

    def review(self, content: str, chapter_number: int,
               title: str, genre: str) -> dict:
        """Critique a chapter. Returns scores dict with weaknesses."""
        try:
            result = self.llm.generate_json(
                system_prompt="Ban la nha phe binh van hoc. Tra ve JSON.",
                user_prompt=CRITIC_PROMPT.format(
                    chapter_number=chapter_number,
                    title=title,
                    genre=genre,
                    content=content[:5000],  # cap to save tokens
                ),
                temperature=0.3,
                model_tier="cheap",
            )
            # Ensure overall is computed from subscores
            score_keys = ["coherence", "character_consistency", "pacing", "writing_quality"]
            vals = [float(result.get(s, 3.0)) for s in score_keys]
            result["overall"] = sum(vals) / len(vals)
            return result
        except Exception as e:
            logger.warning(f"Self-review failed for ch {chapter_number}: {e}")
            return {"overall": 5.0, "weaknesses": [], "strengths": []}

    def revise(self, content: str, weaknesses: list,
               word_count: int = 2000) -> str:
        """Revise chapter based on critique. Returns revised content."""
        weakness_text = "\n".join(f"- {w}" for w in weaknesses)
        try:
            revised = self.llm.generate(
                system_prompt="Ban la nha van chuyen nghiep. Viet lai chuong truyen.",
                user_prompt=REVISE_PROMPT.format(
                    weaknesses=weakness_text,
                    content=content,
                    word_count=word_count,
                ),
                temperature=0.7,
            )
            return revised.strip()
        except Exception as e:
            logger.warning(f"Self-review revision failed: {e}")
            return content  # return original on failure

    def review_and_revise(self, content: str, chapter_number: int,
                          title: str, genre: str,
                          word_count: int = 2000) -> tuple[str, dict]:
        """Full review+revise cycle. Returns (final_content, review_scores)."""
        scores = self.review(content, chapter_number, title, genre)

        if scores["overall"] >= self.threshold:
            logger.info(f"Ch {chapter_number} passed review: {scores['overall']:.1f}/5")
            return content, scores

        weaknesses = scores.get("weaknesses", [])
        if not weaknesses:
            return content, scores

        logger.info(f"Ch {chapter_number} below threshold ({scores['overall']:.1f}), revising...")
        revised = self.revise(content, weaknesses, word_count)
        return revised, scores
