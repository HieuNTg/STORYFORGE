"""Reading analytics for Vietnamese stories — readability, pacing, emotion arcs."""
import logging
import re
from typing import Union
from models.schemas import StoryDraft, EnhancedStory, Chapter

logger = logging.getLogger(__name__)


class StoryAnalytics:
    """Compute reading analytics: readability, pacing, dialogue ratio, emotion arcs."""

    VIETNAMESE_WPM = 200  # Vietnamese reading speed (slower than English 265)

    @staticmethod
    def analyze_story(story: Union[StoryDraft, EnhancedStory]) -> dict:
        """Full analytics for a story. Returns dict with all metrics."""
        chapters = story.chapters
        if not chapters:
            return {"error": "No chapters"}

        chapter_stats = [StoryAnalytics.analyze_chapter(ch) for ch in chapters]

        total_words = sum(s["word_count"] for s in chapter_stats)
        total_sentences = sum(s["sentence_count"] for s in chapter_stats)
        total_dialogues = sum(s["dialogue_count"] for s in chapter_stats)
        total_paragraphs = sum(s["paragraph_count"] for s in chapter_stats)

        return {
            "total_words": total_words,
            "total_chapters": len(chapters),
            "total_sentences": total_sentences,
            "total_paragraphs": total_paragraphs,
            "reading_time_minutes": max(1, total_words // StoryAnalytics.VIETNAMESE_WPM),
            "avg_words_per_chapter": total_words // max(1, len(chapters)),
            "avg_sentence_length": total_words / max(1, total_sentences),
            "dialogue_ratio": total_dialogues / max(1, total_sentences),
            "chapter_stats": chapter_stats,
            # Pacing data for visualization
            "pacing_data": {
                "chapter_numbers": [s["chapter_number"] for s in chapter_stats],
                "word_counts": [s["word_count"] for s in chapter_stats],
                "dialogue_ratios": [s["dialogue_ratio"] for s in chapter_stats],
                "avg_sentence_lengths": [s["avg_sentence_length"] for s in chapter_stats],
            },
        }

    @staticmethod
    def analyze_chapter(chapter: Chapter) -> dict:
        """Analyze a single chapter for readability metrics."""
        content = chapter.content
        words = content.split()
        word_count = len(words)

        # Sentence detection (Vietnamese uses same punctuation)
        sentences = [s.strip() for s in re.split(r'[.!?…]+', content) if s.strip()]
        sentence_count = max(1, len(sentences))

        # Paragraph count
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        paragraph_count = max(1, len(paragraphs))

        # Dialogue detection (Vietnamese uses — or "", supports many typography styles)
        dialogue_pattern = (
            r'(?:'
            r'[—–\-]\s*[^:\n]+?:\s*.+?'  # em-dash/en-dash/hyphen dialogue: — Name: text
            r'|"[^"]*"'                    # smart double quotes
            r'|"[^"]*"'                    # straight double quotes
            r"|'[^']*'"                    # smart single quotes
            r'|«[^»]*»'                   # guillemets
            r'|「[^」]*」'                 # CJK brackets
            r'|『[^』]*』'                 # CJK double brackets
            r')'
        )
        dialogues = re.findall(dialogue_pattern, content)
        dialogue_count = len(dialogues)

        # Dialogue word count
        dialogue_words = sum(len(d.split()) for d in dialogues)

        avg_sentence_length = word_count / sentence_count

        return {
            "chapter_number": chapter.chapter_number,
            "title": chapter.title,
            "word_count": word_count,
            "sentence_count": sentence_count,
            "paragraph_count": paragraph_count,
            "dialogue_count": dialogue_count,
            "dialogue_words": dialogue_words,
            "dialogue_ratio": dialogue_words / max(1, word_count),
            "avg_sentence_length": round(avg_sentence_length, 1),
            "reading_time_minutes": max(1, word_count // StoryAnalytics.VIETNAMESE_WPM),
        }

    @staticmethod
    def extract_emotion_arc(chapters: list[Chapter]) -> dict:
        """Extract simple emotion arc from chapter content using keyword matching.

        Uses Vietnamese emotion keywords to avoid LLM costs.
        Returns dict with chapter emotions for visualization.
        """
        # Vietnamese emotion keyword lexicon
        POSITIVE_KEYWORDS = {
            "vui", "hạnh phúc", "mỉm cười", "cười", "hân hoan", "phấn khởi",
            "yêu", "thương", "ấm áp", "hy vọng", "tự hào", "chiến thắng",
            "hào hứng", "rạng rỡ", "sung sướng", "mãn nguyện", "bình yên",
        }
        NEGATIVE_KEYWORDS = {
            "buồn", "khóc", "đau", "tức giận", "sợ", "lo lắng", "thất vọng",
            "tuyệt vọng", "chết", "máu", "chiến tranh", "hận", "thù",
            "đau khổ", "cô đơn", "bất lực", "tàn nhẫn", "phản bội",
        }
        TENSION_KEYWORDS = {
            "nguy hiểm", "chiến đấu", "đối đầu", "khẩn cấp", "bí mật",
            "âm mưu", "phát hiện", "bất ngờ", "sốc", "kinh hoàng",
            "trốn chạy", "tấn công", "phục kích", "đuổi theo", "bùng nổ",
        }

        arc_data = {
            "chapter_numbers": [],
            "positivity": [],
            "negativity": [],
            "tension": [],
            "emotional_valence": [],  # positive - negative (normalized)
        }

        for ch in chapters:
            content_lower = ch.content.lower()
            words = content_lower.split()
            total = max(1, len(words))

            pos_count = sum(1 for w in words if any(kw in w for kw in POSITIVE_KEYWORDS))
            neg_count = sum(1 for w in words if any(kw in w for kw in NEGATIVE_KEYWORDS))
            ten_count = sum(1 for w in words if any(kw in w for kw in TENSION_KEYWORDS))

            pos_ratio = pos_count / total * 100
            neg_ratio = neg_count / total * 100
            ten_ratio = ten_count / total * 100
            valence = (pos_count - neg_count) / max(1, pos_count + neg_count)

            arc_data["chapter_numbers"].append(ch.chapter_number)
            arc_data["positivity"].append(round(pos_ratio, 2))
            arc_data["negativity"].append(round(neg_ratio, 2))
            arc_data["tension"].append(round(ten_ratio, 2))
            arc_data["emotional_valence"].append(round(valence, 2))

        return arc_data

    @staticmethod
    def extract_emotion_arc_llm(chapters: list[Chapter], max_chapters: int = 50) -> dict:
        """Extract emotion arc using LLM for higher accuracy.

        Falls back to keyword method if LLM fails.
        Uses cheap model tier to minimize cost.
        """
        from services.llm_client import LLMClient
        from services import prompts

        llm = LLMClient()
        arc_data = {
            "chapter_numbers": [],
            "joy": [], "sadness": [], "anger": [],
            "fear": [], "surprise": [], "tension": [], "romance": [],
            "dominant_emotions": [],
            "summaries": [],
        }

        # Cap chapters to avoid excessive LLM costs
        chapters_to_analyze = chapters[:max_chapters]

        for ch in chapters_to_analyze:
            try:
                # Use excerpt for long chapters (save tokens)
                content = ch.content
                if len(content) > 3000:
                    content = content[:2000] + "\n...\n" + content[-1000:]

                result = llm.generate_json(
                    system_prompt="Bạn là chuyên gia phân tích cảm xúc văn học. Trả về JSON.",
                    user_prompt=prompts.EXTRACT_CHAPTER_EMOTIONS.format(
                        chapter_number=ch.chapter_number,
                        title=ch.title,
                        content=content,
                    ),
                    temperature=0.2,
                    max_tokens=300,
                    model_tier="cheap",
                )

                def _clamp(val, lo=0, hi=10):
                    try:
                        return max(lo, min(hi, float(val)))
                    except (TypeError, ValueError):
                        return 5.0

                arc_data["chapter_numbers"].append(ch.chapter_number)
                arc_data["joy"].append(_clamp(result.get("joy", 5)))
                arc_data["sadness"].append(_clamp(result.get("sadness", 5)))
                arc_data["anger"].append(_clamp(result.get("anger", 5)))
                arc_data["fear"].append(_clamp(result.get("fear", 5)))
                arc_data["surprise"].append(_clamp(result.get("surprise", 5)))
                arc_data["tension"].append(_clamp(result.get("tension", 5)))
                arc_data["romance"].append(_clamp(result.get("romance", 0)))
                arc_data["dominant_emotions"].append(str(result.get("dominant_emotion", "")))
                arc_data["summaries"].append(str(result.get("emotional_summary", "")))

            except Exception as e:
                logger.warning(f"LLM emotion extraction failed for ch {ch.chapter_number}: {e}")
                # Fallback: use keyword method for this chapter
                keyword_arc = StoryAnalytics.extract_emotion_arc([ch])
                arc_data["chapter_numbers"].append(ch.chapter_number)
                # Map keyword percentages to 0-10 scale
                pos = keyword_arc["positivity"][0] if keyword_arc["positivity"] else 0
                neg = keyword_arc["negativity"][0] if keyword_arc["negativity"] else 0
                ten = keyword_arc["tension"][0] if keyword_arc["tension"] else 0
                arc_data["joy"].append(min(10, pos * 5))
                arc_data["sadness"].append(min(10, neg * 5))
                arc_data["anger"].append(min(10, neg * 3))
                arc_data["fear"].append(min(10, ten * 4))
                arc_data["surprise"].append(5.0)
                arc_data["tension"].append(min(10, ten * 5))
                arc_data["romance"].append(0.0)
                arc_data["dominant_emotions"].append("unknown")
                arc_data["summaries"].append("")

        return arc_data
