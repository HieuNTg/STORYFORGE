"""Voice Fingerprint — duy trì giọng điệu riêng của từng nhân vật.

Extracts: sentence patterns, vocabulary level, speech quirks, formality.
Prevents: homogenized dialogue, character voice drift after enhancement.
"""

import logging
import re
import warnings
from pydantic import BaseModel, Field
from services.llm_client import LLMClient
from models.schemas import VoiceProfile  # unified schema (Sprint 2 Task 2)
from models.voice_schemas import (
    DialogueAnchor,
    DialogueAnchorDiff,
    VoicePreservationResult,
    resolve_speaker_id,
)

logger = logging.getLogger(__name__)


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

            # Unified VoiceProfile: emotional_expression is dict; coerce legacy str result
            _ee = result.get("emotional_expression", "moderate")
            ee_dict: dict[str, str] = _ee if isinstance(_ee, dict) else {"general": str(_ee or "")}
            _tics = result.get("speech_quirks", []) or []
            profile = VoiceProfile(
                name=character_name,
                avg_sentence_length=avg_len,
                vocabulary_level=result.get("vocabulary_level", "moderate"),
                formality=result.get("formality", "neutral"),
                speech_quirks=_tics,
                verbal_tics=list(_tics),
                emotional_expression=ee_dict,
                dialogue_samples=all_dialogues[:5],
                dialogue_examples=all_dialogues[:5],
                accent_markers=result.get("accent_markers", []) or [],
                typical_topics=result.get("typical_topics", []) or [],
                source="L2-extract",
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

    def build_from_draft(self, draft, progress_callback=None, dedup_l1: bool = True) -> "VoiceFingerprintEngine":
        """Build voice profiles. When dedup_l1 AND draft.voice_profiles present,
        skip per-character LLM extraction and reuse L1 profiles + zero-LLM observed supplement.
        """
        characters = getattr(draft, "characters", []) or []
        chapters = getattr(draft, "chapters", []) or []

        from pipeline.layer2_enhance import _envelope_access as _env
        l1_profiles = _env.voice_profiles(draft)
        l1_map = {p.get("name", ""): p for p in l1_profiles if isinstance(p, dict) and p.get("name")}

        self.llm_calls_saved = 0

        for char in characters:
            char_name = getattr(char, "name", "")
            if not char_name:
                continue
            if dedup_l1 and char_name in l1_map:
                # Reuse L1 prescriptive profile — no LLM call
                l1 = l1_map[char_name]
                ee = l1.get("emotional_expression", {})
                if not isinstance(ee, dict):
                    ee = {"general": str(ee or "")}
                tics = list(l1.get("verbal_tics") or l1.get("speech_quirks") or [])
                examples = list(l1.get("dialogue_examples") or l1.get("dialogue_example") or l1.get("dialogue_samples") or [])
                profile = VoiceProfile(
                    name=char_name,
                    vocabulary_level=l1.get("vocabulary_level", ""),
                    sentence_style=l1.get("sentence_style", ""),
                    verbal_tics=tics,
                    speech_quirks=tics,
                    emotional_expression=ee,
                    dialogue_examples=examples,
                    dialogue_samples=examples,
                    source="L1",
                )
                # Stats enrichment (zero LLM)
                samples = self._gather_samples(char_name, chapters)
                if samples:
                    supplement_observed(profile, samples)
                self.profiles[char_name] = profile
                self.llm_calls_saved += 1
                if progress_callback:
                    progress_callback(f"[VoiceFingerprint] Reused L1 profile for {char_name} (no LLM)")
            else:
                self.extract_profile(char_name, chapters)
                if progress_callback:
                    progress_callback(f"[VoiceFingerprint] Extracted profile for {char_name}")

        logger.info(
            f"VoiceFingerprintEngine: {len(self.profiles)} profiles, "
            f"{self.llm_calls_saved} LLM calls saved via L1 dedup"
        )
        return self

    def _gather_samples(self, char_name: str, chapters: list, max_per_chapter: int = 3, cap: int = 10) -> list[str]:
        """Collect dialogue samples across chapters for observed-stats supplement."""
        samples: list[str] = []
        for ch in chapters or []:
            content = getattr(ch, "content", "") or ""
            found = self._extract_dialogues(content, char_name)
            samples.extend(found[:max_per_chapter])
            if len(samples) >= cap:
                break
        return samples[:cap]

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

    def get_drift_summary(self, character_name: str) -> dict:
        """Get summary of voice drift for a character.

        Returns dict with avg_drift, issues_count, etc.
        """
        profile = self.profiles.get(character_name)
        if not profile:
            return {"avg_drift": 0.0, "issues_count": 0}

        # Check drift tracking if available
        drift_history = getattr(self, "_drift_history", {}).get(character_name, [])
        if not drift_history:
            return {"avg_drift": 0.0, "issues_count": 0, "character": character_name}

        avg_drift = sum(d.get("drift", 0) for d in drift_history) / len(drift_history)
        issues_count = sum(len(d.get("issues", [])) for d in drift_history)

        return {
            "character": character_name,
            "avg_drift": avg_drift,
            "issues_count": issues_count,
            "checks_count": len(drift_history),
            "status": "ok" if avg_drift < 0.3 else "warning" if avg_drift < 0.5 else "critical",
        }

    def record_drift_check(self, character_name: str, drift: float, issues: list) -> None:
        """Record a drift check result for tracking."""
        if not hasattr(self, "_drift_history"):
            self._drift_history = {}
        if character_name not in self._drift_history:
            self._drift_history[character_name] = []
        self._drift_history[character_name].append({
            "drift": drift,
            "issues": issues,
        })

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


# ══════════════════════════════════════════════════════════════════════════════
# Phase 6: Voice Preservation Enforcement
# ══════════════════════════════════════════════════════════════════════════════

# Re-export from voice_schemas so callers that imported from this module still work.
# VoicePreservationResult, DialogueAnchor, DialogueAnchorDiff are the canonical types.


def _extract_dialogue_anchors(content: str, characters: list) -> list[DialogueAnchor]:
    """Walk chapter prose and build speaker-anchored dialogue spans.

    Uses the same regex patterns as VoiceFingerprintEngine._extract_dialogues but
    returns positions (char_offset) and per-speaker ordinal counters.
    Only spans attributable to a known character are included.
    """
    anchors: list[DialogueAnchor] = []
    ordinal_counters: dict[str, int] = {}

    for char in characters:
        try:
            speaker_id = resolve_speaker_id(char)
        except ValueError:
            continue
        char_name = getattr(char, "name", "") or ""
        if not char_name:
            continue

        found: list[tuple[int, str]] = []  # (char_offset, text)

        # Pattern 1: "dialogue" - Name
        pat1 = rf'"([^"]+)"\s*[-–—]\s*{re.escape(char_name)}'
        for m in re.finditer(pat1, content, re.IGNORECASE):
            found.append((m.start(), m.group(1)))

        # Pattern 2: Name ...: "dialogue"
        pat2 = rf'{re.escape(char_name)}[^"]*[:"]\s*"([^"]+)"'
        for m in re.finditer(pat2, content, re.IGNORECASE):
            found.append((m.start(), m.group(1)))

        # Sort by position then assign ordinals in document order
        found.sort(key=lambda x: x[0])

        # Deduplicate by text (keep earliest offset) — mirrors _extract_dialogues logic
        seen_texts: set[str] = set()
        for offset, text in found:
            text_clean = text.strip()
            if not text_clean or len(text_clean) <= 5 or text_clean in seen_texts:
                continue
            seen_texts.add(text_clean)
            ordinal = ordinal_counters.get(speaker_id, 0)
            ordinal_counters[speaker_id] = ordinal + 1
            anchors.append(DialogueAnchor(
                speaker_id=speaker_id,
                ordinal=ordinal,
                text=text_clean,
                char_offset=offset,
            ))

    anchors.sort(key=lambda a: a.char_offset)
    return anchors


def _revert_dialogues_anchored(
    content: str,
    original_content: str,
    characters: list,
    drifted_characters: list[str],
) -> tuple[str, VoicePreservationResult]:
    """Speaker-anchored dialogue revert.

    For each (speaker_id, ordinal) key present in original anchors, look up the
    same key in the enhanced anchors. If found and speaker matches, revert the
    enhanced span to the original text. Mismatches and missing ordinals are
    recorded as diffs with appropriate skip actions.
    """
    result = VoicePreservationResult(drifted_characters=list(drifted_characters))

    original_anchors = _extract_dialogue_anchors(original_content, characters)
    enhanced_anchors = _extract_dialogue_anchors(content, characters)

    if not original_anchors:
        return content, result

    # Build lookup: (speaker_id, ordinal) -> anchor
    enhanced_by_key: dict[tuple[str, int], DialogueAnchor] = {
        (a.speaker_id, a.ordinal): a for a in enhanced_anchors
    }

    reverted = content

    # Filter to drifted characters only — only revert those speakers
    drifted_ids: set[str] = set()
    for char in characters:
        try:
            sid = resolve_speaker_id(char)
        except ValueError:
            continue
        char_name = getattr(char, "name", "") or ""
        if char_name in drifted_characters:
            drifted_ids.add(sid)

    # Collect revert operations sorted descending by enhanced offset to avoid
    # position shifts corrupting subsequent replacements.
    revert_ops: list[tuple[int, str, str, DialogueAnchorDiff]] = []

    for orig_anchor in original_anchors:
        if orig_anchor.speaker_id not in drifted_ids:
            continue

        key = (orig_anchor.speaker_id, orig_anchor.ordinal)
        enh_anchor = enhanced_by_key.get(key)

        if enh_anchor is None:
            diff = DialogueAnchorDiff(
                speaker_id=orig_anchor.speaker_id,
                ordinal=orig_anchor.ordinal,
                original_text=orig_anchor.text,
                enhanced_text="",
                action="skip_no_original",
                reason="enhanced anchor missing for this ordinal",
            )
            result.diffs.append(diff)
            continue

        if enh_anchor.speaker_id != orig_anchor.speaker_id:
            # Should not happen given the key lookup, but guard anyway
            diff = DialogueAnchorDiff(
                speaker_id=orig_anchor.speaker_id,
                ordinal=orig_anchor.ordinal,
                original_text=orig_anchor.text,
                enhanced_text=enh_anchor.text,
                action="skip_speaker_mismatch",
                reason=f"enhanced anchor speaker={enh_anchor.speaker_id!r} != expected={orig_anchor.speaker_id!r}",
            )
            result.diffs.append(diff)
            result.anchor_mismatch_count += 1
            logger.warning(
                "voice_revert_anchor_mismatch char=%s expected_ord=%d",
                orig_anchor.speaker_id, orig_anchor.ordinal,
            )
            continue

        if _similarity_ratio(orig_anchor.text, enh_anchor.text) >= 0.7:
            # Not drifted enough to warrant revert
            continue

        diff = DialogueAnchorDiff(
            speaker_id=orig_anchor.speaker_id,
            ordinal=orig_anchor.ordinal,
            original_text=orig_anchor.text,
            enhanced_text=enh_anchor.text,
            action="revert",
        )
        result.diffs.append(diff)
        revert_ops.append((enh_anchor.char_offset, enh_anchor.text, orig_anchor.text, diff))

    # Apply reverts right-to-left so earlier offsets stay valid
    revert_ops.sort(key=lambda x: x[0], reverse=True)
    for _, enh_text, orig_text, _ in revert_ops:
        # Use quoted form to match what's in the chapter prose
        enh_quoted = f'"{enh_text}"'
        orig_quoted = f'"{orig_text}"'
        if enh_quoted in reverted:
            reverted = reverted.replace(enh_quoted, orig_quoted, 1)
            result.reverted_count += 1
            logger.debug(
                "voice_revert_anchored: %s... → %s...",
                enh_text[:30], orig_text[:30],
            )
        elif enh_text in reverted:
            reverted = reverted.replace(enh_text, orig_text, 1)
            result.reverted_count += 1

    result.original_dialogues = [a.text for a in original_anchors]
    result.enhanced_dialogues = [a.text for a in enhanced_anchors]
    result.preserved_dialogues = _extract_all_dialogues(reverted)

    return reverted, result


def enforce_voice_preservation(
    engine: "VoiceFingerprintEngine",
    original_content: str,
    enhanced_content: str,
    characters: list,
    drift_threshold: float = 0.4,
    revert_threshold: float = 0.3,
    config=None,
) -> tuple[str, VoicePreservationResult]:
    """Enforce voice preservation by reverting drifted dialogues.

    When config.voice_revert_use_anchored is True (default), uses the
    speaker-anchored algorithm. Otherwise falls back to the legacy positional path.

    Returns:
        (preserved_content, result) — content with reverted dialogues + metrics
    """
    use_anchored = getattr(config, "voice_revert_use_anchored", True)

    if not use_anchored:
        return _enforce_voice_preservation_legacy(
            engine, original_content, enhanced_content, characters,
            drift_threshold, revert_threshold,
        )

    result = VoicePreservationResult()

    if not engine.profiles:
        return enhanced_content, result

    preserved_content = enhanced_content
    total_drift = 0.0
    char_count = 0
    drifted_chars: list[str] = []

    for char in characters:
        char_name = getattr(char, "name", "")
        if not char_name or char_name not in engine.profiles:
            continue

        original_dialogues = engine._extract_dialogues(original_content, char_name)
        enhanced_dialogues = engine._extract_dialogues(enhanced_content, char_name)

        if not original_dialogues or not enhanced_dialogues:
            continue

        result.original_dialogues.extend(original_dialogues)
        result.enhanced_dialogues.extend(enhanced_dialogues)

        validation = engine.validate_enhanced_dialogue(
            original_content, enhanced_content, char_name,
        )

        score = validation.get("score", 1.0)
        drift = 1.0 - score
        total_drift += drift
        char_count += 1

        if drift >= revert_threshold:
            drifted_chars.append(char_name)

    if drifted_chars:
        preserved_content, anchor_result = _revert_dialogues_anchored(
            enhanced_content, original_content, characters, drifted_chars,
        )
        result.reverted_count = anchor_result.reverted_count
        result.anchor_mismatch_count = anchor_result.anchor_mismatch_count
        result.diffs = anchor_result.diffs
        result.drifted_characters = anchor_result.drifted_characters
        if anchor_result.reverted_count > 0:
            logger.warning(
                "Voice drift anchored-revert: %d dialogue(s) reverted for: %s",
                anchor_result.reverted_count, ", ".join(drifted_chars),
            )

    result.drift_severity = total_drift / max(1, char_count)
    result.preserved_dialogues = _extract_all_dialogues(preserved_content)

    return preserved_content, result


def _revert_dialogues_legacy(
    content: str,
    original_dialogues: list[str],
    enhanced_dialogues: list[str],
    character_name: str,
) -> str:
    """Legacy positional dialogue revert (deprecated).

    Kept for one release behind voice_revert_use_anchored=False.
    Use the anchored path instead.
    """
    warnings.warn(
        "_revert_dialogues_legacy is deprecated; use anchored revert via voice_revert_use_anchored=True",
        DeprecationWarning,
        stacklevel=2,
    )
    return _revert_dialogues(content, original_dialogues, enhanced_dialogues, character_name)


def _revert_dialogues(
    content: str,
    original_dialogues: list[str],
    enhanced_dialogues: list[str],
    character_name: str,
) -> str:
    """Positional dialogue revert — internal implementation used by legacy path."""
    if not original_dialogues or not enhanced_dialogues:
        return content

    reverted = content

    for i, enh in enumerate(enhanced_dialogues):
        if i >= len(original_dialogues):
            break

        orig = original_dialogues[i]

        if _similarity_ratio(orig, enh) < 0.7:
            if enh in reverted:
                reverted = reverted.replace(enh, orig, 1)
                logger.debug(
                    "Reverted dialogue for %s: %s... → %s...",
                    character_name, enh[:30], orig[:30],
                )

    return reverted


def _enforce_voice_preservation_legacy(
    engine: "VoiceFingerprintEngine",
    original_content: str,
    enhanced_content: str,
    characters: list,
    drift_threshold: float,
    revert_threshold: float,
) -> tuple[str, VoicePreservationResult]:
    """Legacy enforce_voice_preservation — positional index revert."""
    result = VoicePreservationResult()

    if not engine.profiles:
        return enhanced_content, result

    preserved_content = enhanced_content
    total_drift = 0.0
    char_count = 0

    for char in characters:
        char_name = getattr(char, "name", "")
        if not char_name or char_name not in engine.profiles:
            continue

        original_dialogues = engine._extract_dialogues(original_content, char_name)
        enhanced_dialogues = engine._extract_dialogues(enhanced_content, char_name)

        if not original_dialogues or not enhanced_dialogues:
            continue

        result.original_dialogues.extend(original_dialogues)
        result.enhanced_dialogues.extend(enhanced_dialogues)

        validation = engine.validate_enhanced_dialogue(
            original_content, enhanced_content, char_name,
        )

        score = validation.get("score", 1.0)
        drift = 1.0 - score
        total_drift += drift
        char_count += 1

        if drift >= drift_threshold:
            if drift >= revert_threshold:
                warnings.warn(
                    "_revert_dialogues_legacy is deprecated; use anchored revert via voice_revert_use_anchored=True",
                    DeprecationWarning,
                    stacklevel=3,
                )
                preserved_content = _revert_dialogues(
                    preserved_content, original_dialogues, enhanced_dialogues, char_name,
                )
                result.reverted_count += 1
                logger.warning(
                    "Voice drift for %s: %.0f%% — reverting dialogues (legacy)",
                    char_name, drift * 100,
                )

    result.drift_severity = total_drift / max(1, char_count)
    result.preserved_dialogues = _extract_all_dialogues(preserved_content)

    return preserved_content, result


def _similarity_ratio(s1: str, s2: str) -> float:
    """Compute similarity ratio between two strings."""
    if not s1 or not s2:
        return 0.0

    # Simple word overlap ratio
    words1 = set(s1.lower().split())
    words2 = set(s2.lower().split())

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union)


def _extract_all_dialogues(content: str) -> list[str]:
    """Extract all dialogues from content."""
    dialogues = []

    # Pattern: "dialogue"
    pattern = r'"([^"]+)"'
    matches = re.findall(pattern, content)
    dialogues.extend([m for m in matches if len(m) > 5])

    return list(set(dialogues))[:30]


def build_voice_enforcement_prompt(
    engine: VoiceFingerprintEngine,
    characters: list,
    strict: bool = True,
) -> str:
    """Build strong voice enforcement prompt for enhancement.

    Args:
        engine: Voice fingerprint engine
        characters: Characters in the chapter
        strict: If True, use stronger enforcement language

    Returns:
        Prompt block with voice constraints
    """
    if not engine.profiles:
        return ""

    lines = ["## ⚠️ BẮT BUỘC: GIỮ NGUYÊN GIỌNG NÓI NHÂN VẬT"]
    if strict:
        lines.append("KHÔNG ĐƯỢC thay đổi phong cách nói của nhân vật. Chỉ tăng kịch tính, KHÔNG thay đổi giọng điệu.")
    lines.append("")

    for char in characters:
        char_name = getattr(char, "name", "")
        profile = engine.profiles.get(char_name)
        if not profile:
            continue

        guidance = engine.get_character_voice_guidance(char_name)
        if guidance:
            lines.append(f"**{char_name}**: {guidance}")

            # Add sample dialogue as reference
            if profile.dialogue_samples:
                sample = profile.dialogue_samples[0][:80]
                lines.append(f'  Mẫu: "{sample}"')

    if len(lines) <= 2:  # Only header
        return ""

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Sprint 2 Task 2 — Zero-LLM observed stats supplement
# ══════════════════════════════════════════════════════════════════════════════

_FORMAL_PARTICLES_VN = {"thưa", "kính", "xin phép", "ngài", "quý"}
_CASUAL_PARTICLES_VN = {"ừ", "ờ", "hả", "nhé", "nha", "vậy đó", "mày", "tao"}


def _infer_formality_vn(samples: list[str]) -> str:
    """Heuristic formality detector for Vietnamese dialogue samples.

    Pure regex/token counting — no LLM. Returns one of casual/neutral/formal/mixed.
    """
    if not samples:
        return ""
    formal_hits = 0
    casual_hits = 0
    for s in samples:
        low = (s or "").lower()
        formal_hits += sum(1 for p in _FORMAL_PARTICLES_VN if p in low)
        casual_hits += sum(1 for p in _CASUAL_PARTICLES_VN if p in low)
    if formal_hits and casual_hits:
        return "mixed"
    if formal_hits > casual_hits:
        return "formal"
    if casual_hits > formal_hits:
        return "casual"
    return "neutral"


def supplement_observed(
    profile: VoiceProfile,
    dialogue_samples: list[str],
    max_samples: int = 5,
) -> VoiceProfile:
    """Merge observed stats into L1-prescribed profile. No LLM call.

    Populates observed_avg_sentence_length, observed_formality, observed_samples.
    Flips source to 'L1+L2' when samples available.
    """
    if not dialogue_samples:
        return profile
    lens = [len(re.findall(r"\w+", s)) for s in dialogue_samples]
    profile.observed_avg_sentence_length = round(sum(lens) / len(lens), 2) if lens else 0.0
    profile.observed_samples = dialogue_samples[:max_samples]
    profile.observed_formality = _infer_formality_vn(dialogue_samples)
    if profile.source == "L1":
        profile.source = "L1+L2"
    return profile


def get_voice_drift_summary(result: VoicePreservationResult) -> dict:
    """Get summary of voice drift for reporting."""
    return {
        "drift_severity": result.drift_severity,
        "reverted_count": result.reverted_count,
        "violations": len(result.violations),
        "violation_chars": [v["character"] for v in result.violations],
        "status": (
            "ok" if result.drift_severity < 0.3
            else "warning" if result.drift_severity < 0.5
            else "critical"
        ),
    }
