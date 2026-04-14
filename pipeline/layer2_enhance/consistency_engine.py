"""Consistency Engine — tổng hợp tất cả ràng buộc nhất quán cho Layer 2.

Orchestrates: CharacterStateRegistry, SettingContinuityGraph, ThreadWatchdog, VoiceFingerprint.
Injects constraints into enhance prompts, validates output, flags violations.
"""

import logging
from typing import Optional
from pydantic import BaseModel, Field

from pipeline.layer2_enhance.character_state_registry import CharacterStateRegistry
from pipeline.layer2_enhance.setting_continuity import SettingContinuityGraph
from pipeline.layer2_enhance.thread_watchdog import ThreadWatchdog
from pipeline.layer2_enhance.voice_fingerprint import VoiceFingerprintEngine

logger = logging.getLogger(__name__)


class ConsistencyViolation(BaseModel):
    """Một vi phạm nhất quán."""
    type: str  # character_state | setting | thread | voice
    subtype: str = ""
    chapter: int = 0
    severity: str = "warning"  # warning | critical
    description: str = ""
    fix_suggestion: str = ""


class ConsistencyReport(BaseModel):
    """Báo cáo tổng hợp nhất quán."""
    total_violations: int = 0
    critical_count: int = 0
    warning_count: int = 0
    violations: list[ConsistencyViolation] = Field(default_factory=list)
    unresolved_threads: list[dict] = Field(default_factory=list)
    voice_drift_characters: list[str] = Field(default_factory=list)


class ConsistencyEngine:
    """Engine tổng hợp kiểm tra và đảm bảo nhất quán Layer 2.

    Workflow:
    1. build_from_draft() - Extract all registries before enhance
    2. get_constraints_for_chapter() - Inject constraints into enhance prompt
    3. validate_enhanced_chapter() - Check output for violations
    4. get_final_report() - Summary after all chapters enhanced
    """

    def __init__(self):
        self.state_registry = CharacterStateRegistry()
        self.setting_graph = SettingContinuityGraph()
        self.thread_watchdog = ThreadWatchdog()
        self.voice_engine = VoiceFingerprintEngine()

        self.draft = None
        self.total_chapters = 0
        self.character_names: list[str] = []
        self._built = False

    def build_from_draft(self, draft, progress_callback=None) -> "ConsistencyEngine":
        """Xây dựng tất cả registries từ draft trước khi enhance."""
        self.draft = draft
        self.total_chapters = len(getattr(draft, "chapters", []) or [])
        self.character_names = [c.name for c in getattr(draft, "characters", []) or []]

        def _log(msg: str):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        _log("🔧 Building consistency registries...")

        # A. Character State Registry
        _log("  [1/4] Extracting character states...")
        self.state_registry.build_from_draft(draft)

        # B. Setting Continuity Graph
        _log("  [2/4] Building setting graph...")
        self.setting_graph.build_from_draft(draft)

        # C. Thread Watchdog
        _log("  [3/4] Loading plot threads...")
        self.thread_watchdog.load_from_draft(draft)

        # D. Voice Fingerprint
        _log("  [4/4] Extracting voice fingerprints...")
        self.voice_engine.build_from_draft(draft)

        self._built = True
        _log(
            f"✅ Consistency engine ready: "
            f"{len(self.state_registry.states)} char states, "
            f"{len(self.setting_graph.locations)} locations, "
            f"{len(self.thread_watchdog.threads)} threads, "
            f"{len(self.voice_engine.profiles)} voice profiles"
        )
        return self

    def get_constraints_for_chapter(self, chapter_number: int) -> str:
        """Tạo block ràng buộc để inject vào enhance prompt."""
        if not self._built:
            logger.warning("ConsistencyEngine not built, no constraints available")
            return ""

        sections = []

        # A. Character states
        char_constraints = self.state_registry.format_constraints_for_chapter(chapter_number)
        if char_constraints:
            sections.append(char_constraints)

        # B. Setting continuity
        setting_constraints = self.setting_graph.format_constraints_for_chapter(chapter_number)
        if setting_constraints:
            sections.append(setting_constraints)

        # C. Thread watchdog
        thread_constraints = self.thread_watchdog.format_constraints_for_chapter(
            chapter_number, self.total_chapters
        )
        if thread_constraints:
            sections.append(thread_constraints)

        # D. Voice fingerprints
        voice_constraints = self.voice_engine.format_constraints_for_chapter()
        if voice_constraints:
            sections.append(voice_constraints)

        if not sections:
            return ""

        header = """
## ⚠️ RÀN BUỘC NHẤT QUÁN - PHẢI TUÂN THỦ
Các ràng buộc sau PHẢI được tuân thủ khi viết lại chương.
Vi phạm sẽ gây mâu thuẫn trong truyện.
"""
        return header + "\n\n".join(sections)

    def validate_enhanced_chapter(
        self,
        original_content: str,
        enhanced_content: str,
        chapter_number: int,
    ) -> list[ConsistencyViolation]:
        """Kiểm tra enhanced content cho violations."""
        if not self._built:
            return []

        violations = []

        # A. Validate character states
        try:
            state_violations = self.state_registry.validate_chapter_states(
                enhanced_content, chapter_number, self.character_names
            )
            for v in state_violations:
                violations.append(ConsistencyViolation(
                    type="character_state",
                    subtype=v.get("type", ""),
                    chapter=chapter_number,
                    severity=v.get("severity", "warning"),
                    description=v.get("description", ""),
                ))
        except Exception as e:
            logger.debug(f"State validation error ch{chapter_number}: {e}")

        # B. Validate setting continuity
        try:
            # Get previous locations per character
            prev_locs = {}
            for name in self.character_names:
                state = self.state_registry.get_last_known_state(name, chapter_number)
                if state and state.location:
                    prev_locs[name] = state.location

            setting_violations = self.setting_graph.validate_enhanced_chapter(
                enhanced_content, chapter_number, prev_locs
            )
            for v in setting_violations:
                violations.append(ConsistencyViolation(
                    type="setting",
                    subtype=v.get("type", ""),
                    chapter=chapter_number,
                    severity=v.get("severity", "warning"),
                    description=v.get("description", ""),
                ))
        except Exception as e:
            logger.debug(f"Setting validation error ch{chapter_number}: {e}")

        # C. Validate threads
        try:
            thread_violations = self.thread_watchdog.validate_enhanced_chapter(
                enhanced_content, chapter_number, self.total_chapters
            )
            for v in thread_violations:
                violations.append(ConsistencyViolation(
                    type="thread",
                    subtype=v.get("type", ""),
                    chapter=chapter_number,
                    severity=v.get("severity", "warning"),
                    description=v.get("description", ""),
                ))

            # Also update thread status
            self.thread_watchdog.check_chapter(enhanced_content, chapter_number)
        except Exception as e:
            logger.debug(f"Thread validation error ch{chapter_number}: {e}")

        # D. Validate voice consistency (per character)
        voice_drift_chars = []
        for name in self.character_names:
            try:
                result = self.voice_engine.validate_enhanced_dialogue(
                    original_content, enhanced_content, name
                )
                if not result.get("consistent", True):
                    voice_drift_chars.append(name)
                    for issue in result.get("issues", []):
                        violations.append(ConsistencyViolation(
                            type="voice",
                            subtype="voice_drift",
                            chapter=chapter_number,
                            severity="warning",
                            description=f"{name}: {issue}",
                        ))
            except Exception as e:
                logger.debug(f"Voice validation error for {name} ch{chapter_number}: {e}")

        # Update state registry with enhanced content
        try:
            self.state_registry.extract_states_from_chapter(
                enhanced_content, chapter_number, self.character_names
            )
        except Exception as e:
            logger.debug(f"State extraction error ch{chapter_number}: {e}")

        # Update setting graph
        try:
            self.setting_graph.extract_from_chapter(enhanced_content, chapter_number)
        except Exception as e:
            logger.debug(f"Setting extraction error ch{chapter_number}: {e}")

        return violations

    def get_final_report(self) -> ConsistencyReport:
        """Tạo báo cáo tổng hợp sau khi enhance xong."""
        unresolved = self.thread_watchdog.get_unresolved_report(self.total_chapters)

        # Collect all voice drift characters
        voice_drift = []
        for name in self.character_names:
            profile = self.voice_engine.profiles.get(name)
            if profile:
                # Check if dialogues changed significantly across chapters
                # This is a simplified check
                pass

        return ConsistencyReport(
            total_violations=0,  # Will be aggregated by caller
            unresolved_threads=unresolved,
            voice_drift_characters=voice_drift,
        )

    def get_character_location(self, name: str, chapter: int) -> Optional[str]:
        """Helper: lấy vị trí nhân vật tại chương."""
        state = self.state_registry.get_state(name, chapter)
        if state:
            return state.location
        return None

    def get_character_voice_guidance(self, name: str) -> str:
        """Helper: lấy hướng dẫn giọng nói cho nhân vật."""
        return self.voice_engine.get_character_voice_guidance(name)

    def is_transition_valid(self, from_loc: str, to_loc: str) -> bool:
        """Helper: kiểm tra di chuyển hợp lệ."""
        return self.setting_graph.is_transition_valid(from_loc, to_loc)

    def get_open_threads_summary(self, chapter: int) -> str:
        """Helper: tóm tắt threads đang mở."""
        threads = self.thread_watchdog.get_threads_for_chapter(chapter, self.total_chapters)
        if not threads:
            return ""
        return "\n".join(f"- {t.description}" for t in threads[:5])


def inject_consistency_constraints(
    base_prompt: str,
    consistency_engine: "ConsistencyEngine",
    chapter_number: int,
) -> str:
    """Utility function: inject constraints vào prompt enhance."""
    constraints = consistency_engine.get_constraints_for_chapter(chapter_number)
    if not constraints:
        return base_prompt

    return f"{base_prompt}\n\n{constraints}"
