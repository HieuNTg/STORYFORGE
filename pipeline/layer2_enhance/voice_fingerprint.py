"""Voice Fingerprint — duy trì giọng điệu riêng của từng nhân vật.

Extracts: sentence patterns, vocabulary level, speech quirks, formality.
Prevents: homogenized dialogue, character voice drift after enhancement.
"""

import logging
import re
from pydantic import BaseModel, Field
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class VoiceProfile(BaseModel):
    """Hồ sơ giọng nói của nhân vật."""
    name: str
    avg_sentence_length: float = 0.0  # words per sentence
    vocabulary_level: str = ""  # simple | moderate | sophisticated | archaic
    formality: str = ""  # casual | neutral | formal | mixed
    speech_quirks: list[str] = Field(default_factory=list)  # catchphrases, patterns
    emotional_expression: str = ""  # reserved | moderate | expressive
    dialogue_samples: list[str] = Field(default_factory=list)  # representative quotes
    accent_markers: list[str] = Field(default_factory=list)  # dialect, accent indicators
    typical_topics: list[str] = Field(default_factory=list)  # what they talk about


class VoiceFingerprintEngine:
    """Trích xuất và duy trì fingerprint giọng nói nhân vật."""

    EXTRACT_VOICE_PROMPT = """Phân tích giọng nói và phong cách đối thoại của nhân vật "{name}" từ các mẫu sau:

{dialogue_samples}

Trả về JSON:
{{
  "vocabulary_level": "simple | moderate | sophisticated | archaic",
  "formality": "casual | neutral | formal | mixed",
  "speech_quirks": ["các cụm từ hay dùng, cách nói đặc trưng"],
  "emotional_expression": "reserved | moderate | expressive",
  "accent_markers": ["dấu hiệu giọng địa phương, phương ngữ"],
  "typical_topics": ["chủ đề thường nói đến"],
  "style_summary": "tóm tắt ngắn 1-2 câu về phong cách nói"
}}"""

    CHECK_VOICE_CONSISTENCY_PROMPT = """So sánh lời thoại gốc và lời thoại đã enhance của nhân vật "{name}".

Hồ sơ giọng nói:
{voice_profile}

Lời thoại gốc:
{original_dialogues}

Lời thoại sau enhance:
{enhanced_dialogues}

Đánh giá và trả về JSON:
{{
  "consistency_score": 0.0-1.0,
  "issues": ["vấn đề cụ thể"],
  "drift_examples": [
    {{"original": "câu gốc", "enhanced": "câu enhance", "issue": "vấn đề"}}
  ],
  "suggestions": ["gợi ý sửa"]
}}"""

    def __init__(self):
        self.profiles: dict[str, VoiceProfile] = {}
        self.llm = LLMClient()

    def _extract_dialogues(self, content: str, character_name: str) -> list[str]:
        """Trích xuất lời thoại của nhân vật từ nội dung."""
        dialogues = []

        # Pattern 1: "dialogue" - Name said
        pattern1 = rf'"([^"]+)"\s*[-–—]\s*{re.escape(character_name)}'
        dialogues.extend(re.findall(pattern1, content, re.IGNORECASE))

        # Pattern 2: Name said: "dialogue" or Name: "dialogue"
        pattern2 = rf'{re.escape(character_name)}[^"]*[:"]\s*"([^"]+)"'
        dialogues.extend(re.findall(pattern2, content, re.IGNORECASE))

        # Pattern 3: Direct speech with name mention nearby
        pattern3 = rf'{re.escape(character_name)}[^.]*:\s*[-–—]?\s*([^.!?]+[.!?])'
        matches = re.findall(pattern3, content, re.IGNORECASE)
        dialogues.extend([m.strip() for m in matches if len(m) > 10])

        # Deduplicate and clean
        seen = set()
        cleaned = []
        for d in dialogues:
            d_clean = d.strip()
            if d_clean and d_clean not in seen and len(d_clean) > 5:
                seen.add(d_clean)
                cleaned.append(d_clean)

        return cleaned[:15]  # Limit samples

    def _compute_avg_sentence_length(self, dialogues: list[str]) -> float:
        """Tính độ dài câu trung bình."""
        if not dialogues:
            return 0.0

        total_words = 0
        total_sentences = 0

        for d in dialogues:
            sentences = re.split(r'[.!?]+', d)
            for s in sentences:
                words = s.split()
                if words:
                    total_words += len(words)
                    total_sentences += 1

        return total_words / max(1, total_sentences)

    def extract_profile(
        self,
        character_name: str,
        chapters: list,
    ) -> VoiceProfile:
        """Trích xuất voice profile từ các chương."""
        all_dialogues = []

        for ch in chapters:
            content = getattr(ch, "content", "") or ""
            dialogues = self._extract_dialogues(content, character_name)
            all_dialogues.extend(dialogues)

        if not all_dialogues:
            logger.debug(f"No dialogues found for {character_name}")
            return VoiceProfile(name=character_name)

        # Compute statistical features
        avg_len = self._compute_avg_sentence_length(all_dialogues)

        # LLM analysis for qualitative features
        samples_text = "\n".join(f'- "{d}"' for d in all_dialogues[:10])

        try:
            result = self.llm.generate_json(
                system_prompt="Phân tích phong cách nói của nhân vật. Trả về JSON.",
                user_prompt=self.EXTRACT_VOICE_PROMPT.format(
                    name=character_name,
                    dialogue_samples=samples_text,
                ),
                temperature=0.2,
                max_tokens=500,
                model_tier="cheap",
            )

            profile = VoiceProfile(
                name=character_name,
                avg_sentence_length=avg_len,
                vocabulary_level=result.get("vocabulary_level", "moderate"),
                formality=result.get("formality", "neutral"),
                speech_quirks=result.get("speech_quirks", []) or [],
                emotional_expression=result.get("emotional_expression", "moderate"),
                dialogue_samples=all_dialogues[:5],
                accent_markers=result.get("accent_markers", []) or [],
                typical_topics=result.get("typical_topics", []) or [],
            )

            self.profiles[character_name] = profile
            logger.debug(
                f"Voice profile for {character_name}: "
                f"vocab={profile.vocabulary_level}, formality={profile.formality}"
            )
            return profile

        except Exception as e:
            logger.warning(f"Voice profile extraction failed for {character_name}: {e}")
            profile = VoiceProfile(
                name=character_name,
                avg_sentence_length=avg_len,
                dialogue_samples=all_dialogues[:5],
            )
            self.profiles[character_name] = profile
            return profile

    def build_from_draft(self, draft, progress_callback=None) -> "VoiceFingerprintEngine":
        """Xây dựng voice profiles cho tất cả nhân vật."""
        characters = getattr(draft, "characters", []) or []
        chapters = getattr(draft, "chapters", []) or []

        for char in characters:
            char_name = getattr(char, "name", "")
            if char_name:
                self.extract_profile(char_name, chapters)
                if progress_callback:
                    progress_callback(f"[VoiceFingerprint] Extracted profile for {char_name}")

        logger.info(f"VoiceFingerprintEngine: {len(self.profiles)} profiles created")
        return self

    def format_constraints_for_chapter(self) -> str:
        """Tạo text ràng buộc giọng nói cho enhance prompt."""
        if not self.profiles:
            return ""

        lines = ["## Phong cách đối thoại nhân vật"]

        for name, profile in self.profiles.items():
            parts = [f"**{name}:**"]

            style_parts = []
            if profile.vocabulary_level:
                style_parts.append(f"từ vựng {profile.vocabulary_level}")
            if profile.formality:
                style_parts.append(f"phong cách {profile.formality}")
            if profile.emotional_expression:
                style_parts.append(f"biểu cảm {profile.emotional_expression}")

            if style_parts:
                parts.append(f"  - Phong cách: {', '.join(style_parts)}")

            if profile.speech_quirks:
                quirks = ", ".join(profile.speech_quirks[:3])
                parts.append(f"  - Đặc trưng: {quirks}")

            if profile.dialogue_samples:
                sample = profile.dialogue_samples[0][:60]
                parts.append(f'  - Ví dụ: "{sample}..."')

            lines.append("\n".join(parts))

        return "\n".join(lines)

    def validate_enhanced_dialogue(
        self,
        original_content: str,
        enhanced_content: str,
        character_name: str,
    ) -> dict:
        """Kiểm tra consistency của dialogue sau enhance."""
        profile = self.profiles.get(character_name)
        if not profile:
            return {"consistent": True, "issues": []}

        original_dialogues = self._extract_dialogues(original_content, character_name)
        enhanced_dialogues = self._extract_dialogues(enhanced_content, character_name)

        if not original_dialogues or not enhanced_dialogues:
            return {"consistent": True, "issues": []}

        # Quick statistical check
        orig_avg_len = self._compute_avg_sentence_length(original_dialogues)
        enh_avg_len = self._compute_avg_sentence_length(enhanced_dialogues)

        issues = []
        if abs(orig_avg_len - enh_avg_len) > orig_avg_len * 0.5:  # >50% change
            issues.append(f"Độ dài câu thay đổi đáng kể: {orig_avg_len:.1f} → {enh_avg_len:.1f}")

        # LLM consistency check if significant dialogues
        if len(original_dialogues) >= 2 and len(enhanced_dialogues) >= 2:
            try:
                profile_text = (
                    f"Vocabulary: {profile.vocabulary_level}\n"
                    f"Formality: {profile.formality}\n"
                    f"Expression: {profile.emotional_expression}\n"
                    f"Quirks: {', '.join(profile.speech_quirks[:3])}"
                )

                result = self.llm.generate_json(
                    system_prompt="Đánh giá consistency giọng nói. Trả về JSON.",
                    user_prompt=self.CHECK_VOICE_CONSISTENCY_PROMPT.format(
                        name=character_name,
                        voice_profile=profile_text,
                        original_dialogues="\n".join(f'- "{d}"' for d in original_dialogues[:5]),
                        enhanced_dialogues="\n".join(f'- "{d}"' for d in enhanced_dialogues[:5]),
                    ),
                    temperature=0.1,
                    max_tokens=400,
                    model_tier="cheap",
                )

                score = result.get("consistency_score", 1.0)
                if score < 0.7:
                    issues.extend(result.get("issues", []))

                return {
                    "consistent": score >= 0.7,
                    "score": score,
                    "issues": issues,
                    "drift_examples": result.get("drift_examples", []),
                    "suggestions": result.get("suggestions", []),
                }

            except Exception as e:
                logger.debug(f"Voice consistency check failed for {character_name}: {e}")

        return {
            "consistent": len(issues) == 0,
            "issues": issues,
        }

    def get_character_voice_guidance(self, character_name: str) -> str:
        """Lấy hướng dẫn giọng nói cụ thể cho một nhân vật."""
        profile = self.profiles.get(character_name)
        if not profile:
            return ""

        parts = []
        if profile.vocabulary_level:
            vocab_guidance = {
                "simple": "dùng từ đơn giản, dễ hiểu",
                "moderate": "từ vựng bình thường",
                "sophisticated": "từ vựng phong phú, câu phức",
                "archaic": "dùng từ cổ, trang trọng",
            }
            parts.append(vocab_guidance.get(profile.vocabulary_level, ""))

        if profile.formality:
            form_guidance = {
                "casual": "nói thoải mái, thân mật",
                "formal": "nói lịch sự, trang trọng",
                "neutral": "nói bình thường",
                "mixed": "linh hoạt tùy ngữ cảnh",
            }
            parts.append(form_guidance.get(profile.formality, ""))

        if profile.speech_quirks:
            parts.append(f"hay dùng: {', '.join(profile.speech_quirks[:2])}")

        if profile.emotional_expression:
            expr_guidance = {
                "reserved": "ít bộc lộ cảm xúc",
                "moderate": "bộc lộ vừa phải",
                "expressive": "biểu cảm mạnh mẽ",
            }
            parts.append(expr_guidance.get(profile.emotional_expression, ""))

        return "; ".join(p for p in parts if p)
