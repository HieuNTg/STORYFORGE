"""CoT + Constitutional AI self-review for chapter quality."""

import logging
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Review threshold: chapters scoring below this get revised
DEFAULT_THRESHOLD = 3.0  # out of 5.0


def get_genre_threshold(genre: str, fallback: float = DEFAULT_THRESHOLD) -> float:
    """Return genre-aware self-review threshold via ConfigManager.

    Delegates to ConfigManager.get_review_threshold() so the mapping stays
    in one place (config.py).  Falls back to `fallback` if config unavailable.
    """
    try:
        from config import ConfigManager
        return ConfigManager().get_review_threshold(genre)
    except Exception:
        return fallback

CRITIC_PROMPT = """Bạn là nhà phê bình văn học nghiêm khắc. Đánh giá chương truyện sau:

Chương {chapter_number}: {title}
Thể loại: {genre}
---
{content}
---

Suy nghĩ từng bước (chain-of-thought):
1. Tính liên kết của cốt truyện có logic không?
2. Nhân vật hành động có nhất quán không?
3. Nhịp độ có phù hợp không? Có đoạn nào nhạm không?
4. Văn phong có hấp dẫn không?

Trả về JSON:
{{
  "coherence": <1-5>,
  "character_consistency": <1-5>,
  "pacing": <1-5>,
  "writing_quality": <1-5>,
  "overall": <1-5>,
  "weaknesses": ["<điểm yếu 1>", "<điểm yếu 2>"],
  "strengths": ["<điểm mạnh 1>"]
}}"""

REVISE_PROMPT = """Viết lại chương truyện sau, chỉ sửa các điểm yếu đã chỉ ra.
GIỮ NGUYÊN cốt truyện, nhân vật, và các điểm mạnh.

Điểm yếu cần sửa:
{weaknesses}

Nội dung gốc:
---
{content}
---

Yêu cầu:
- Khoảng {word_count} từ
- Viết hoàn toàn bằng tiếng Việt
- Chỉ cải thiện điểm yếu, KHÔNG thay đổi cốt truyện

Bắt đầu viết lại:"""


class SelfReviewer:
    """Single-pass CoT critic + optional revision for chapter quality.

    The effective threshold is resolved per-call from the genre via
    get_genre_threshold(), so a single SelfReviewer instance handles
    mixed-genre pipelines correctly.  The constructor `threshold` acts
    as a global override (used in tests or when caller has its own value).
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.llm = LLMClient()
        self.threshold = threshold  # override; 0.0 means "use genre-aware lookup"

    def review(self, content: str, chapter_number: int,
               title: str, genre: str) -> dict:
        """Critique a chapter. Returns scores dict with weaknesses."""
        try:
            result = self.llm.generate_json(
                system_prompt="Bạn là nhà phê bình văn học. Trả về JSON.",
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
                system_prompt="Bạn là nhà văn chuyên nghiệp. Viết lại chương truyện.",
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
        """Full review+revise cycle. Returns (final_content, review_scores).

        The pass/fail threshold is resolved from the genre so action/thriller
        chapters use 2.8 and literary chapters use 3.5 automatically.
        """
        scores = self.review(content, chapter_number, title, genre)
        effective_threshold = get_genre_threshold(genre, fallback=self.threshold)

        if scores["overall"] >= effective_threshold:
            logger.info(f"Ch {chapter_number} passed review: {scores['overall']:.1f}/5")
            return content, scores

        weaknesses = scores.get("weaknesses", [])
        if not weaknesses:
            return content, scores

        logger.info(
            f"Ch {chapter_number} below threshold ({scores['overall']:.1f} < "
            f"{effective_threshold:.1f} for genre '{genre}'), revising..."
        )
        revised = self.revise(content, weaknesses, word_count)
        return revised, scores
