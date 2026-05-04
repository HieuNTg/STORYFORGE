"""Tăng cường kịch tính cho truyện dựa trên kết quả mô phỏng."""

import asyncio
import logging
import time
from typing import Optional
from models.schemas import (
    StoryDraft, SimulationResult, EnhancedStory, Chapter, count_words,
)
from services.llm_client import LLMClient
from services import prompts as prompt_templates
from pipeline.layer2_enhance.genre_drama_rules import get_genre_enhancement_hints
from config import ConfigManager

# Consistency Engine (A-E improvements)
try:
    from pipeline.layer2_enhance.consistency_engine import ConsistencyEngine
    _CONSISTENCY_AVAILABLE = True
except ImportError:
    _CONSISTENCY_AVAILABLE = False

# Structural issue detector (Sprint 2 P4 — NER + embedding replacement)
try:
    from pipeline.semantic.structural_detector import detect_structural_issues as _detect_structural_issues
    _STRUCTURAL_DETECTOR_AVAILABLE = True
except ImportError:
    _detect_structural_issues = None  # type: ignore[assignment]
    _STRUCTURAL_DETECTOR_AVAILABLE = False

logger = logging.getLogger(__name__)

MAX_REENHANCE_ROUNDS = 2
MIN_DRAMA_SCORE = 0.6


def _build_arc_context(draft, chapter_number: int) -> str:
    """Derive arc waypoint context per character for current chapter."""
    try:
        chars = getattr(draft, "characters", None) or []
        lines: list[str] = []
        for c in chars:
            waypoints = getattr(c, "arc_waypoints", None) or []
            for wp in waypoints:
                wp_dict = wp.model_dump() if hasattr(wp, "model_dump") else wp
                if not isinstance(wp_dict, dict):
                    continue
                ch_range = wp_dict.get("chapter_range") or wp_dict.get("range") or ""
                if ch_range:
                    try:
                        parts = str(ch_range).replace(" ", "").split("-")
                        start, end = int(parts[0]), int(parts[-1])
                        if not (start <= chapter_number <= end):
                            continue
                    except (ValueError, IndexError):
                        pass
                stage = wp_dict.get("stage_name") or wp_dict.get("stage") or ""
                pct = wp_dict.get("progress_pct", 0.0)
                if stage:
                    lines.append(f"- {c.name}: {stage} ({int(float(pct) * 100)}%)")
                    break
        return "\n".join(lines)[:400] if lines else ""
    except Exception:
        return ""


def _extract_pacing_directive(draft, chapter_number: int) -> str:
    if draft is None:
        return ""
    try:
        chapters = list(getattr(draft, "chapters", []) or [])
        for ch in chapters:
            if getattr(ch, "chapter_number", None) == chapter_number:
                return str(getattr(ch, "pacing_adjustment", "") or "")
        ctx = getattr(draft, "context", None)
        if ctx is not None:
            return str(getattr(ctx, "pacing_adjustment", "") or "")
    except Exception:
        pass
    return ""


def _extract_pacing_type(draft, chapter_number: int) -> str:
    """L2-E: Extract pacing_type from outline for per-chapter drama intensity."""
    if draft is None:
        return ""
    try:
        outlines = list(getattr(draft, "outlines", []) or [])
        for o in outlines:
            if getattr(o, "chapter_number", None) == chapter_number:
                return str(getattr(o, "pacing_type", "") or "")
    except Exception:
        pass
    return ""


def _precheck_coherence(llm, chapter, draft, prev_chapters: list) -> str:
    """L2-F: Quick coherence pre-check before enhancement.

    Returns constraint text to inject into enhancement prompt.
    Identifies potential timeline/character/setting violations in the original chapter.
    """
    if not prev_chapters:
        return ""
    try:
        prev_summary = "\n".join(
            f"Ch{c.chapter_number}: {getattr(c, 'summary', '') or c.content[:150]}"
            for c in prev_chapters[-3:]
        )
        char_names = [c.name for c in getattr(draft, "characters", []) or []][:8]

        prompt = f"""Kiểm tra nhanh chương {chapter.chapter_number} với context trước:
{prev_summary}

Nhân vật: {', '.join(char_names)}
Chương hiện tại: {chapter.content[:1500]}

Liệt kê TỐI ĐA 3 vấn đề nhất quán tiềm ẩn (timeline, vị trí, trạng thái nhân vật).
Trả về JSON: {{"issues": ["issue1", "issue2"]}} hoặc {{"issues": []}} nếu OK."""

        result = llm.generate_json(
            system_prompt="Biên tập viên kiểm tra nhất quán. Trả về JSON ngắn gọn.",
            user_prompt=prompt,
            temperature=0.1,
            model_tier="cheap",
            max_tokens=300,
        )
        issues = result.get("issues", [])
        if not issues:
            return ""
        lines = [f"- TRÁNH: {i}" for i in issues[:3]]
        return "## CẢNH BÁO NHẤT QUÁN (phải duy trì):\n" + "\n".join(lines)
    except Exception as e:
        logger.debug(f"Coherence pre-check failed (non-fatal): {e}")
        return ""


def _build_knowledge_constraints(sim_result, draft) -> str:
    """L2-B: Build knowledge constraints from sim_result.knowledge_state.

    Prevents L2 from hallucinating facts characters shouldn't know.
    """
    knowledge_state = getattr(sim_result, "knowledge_state", None) or {}
    if not knowledge_state:
        knowledge_state = getattr(draft, "_knowledge_state", None) or {}
    if not knowledge_state:
        return ""
    lines: list[str] = []
    for char_name, facts in knowledge_state.items():
        if not facts:
            continue
        facts_text = "; ".join(str(f)[:80] for f in facts[:5])
        lines.append(f"- {char_name} BIẾT: {facts_text}")
    if not lines:
        return ""
    return "## KIẾN THỨC NHÂN VẬT (KHÔNG được tiết lộ điều nhân vật chưa biết):\n" + "\n".join(lines[:10])


def _resolve_contract(chapter, ch_num: int):
    """Return a NegotiatedChapterContract for *chapter*.

    Priority:
    1. `chapter.negotiated_contract` if already a NegotiatedChapterContract.
    2. Deserialise from dict if `negotiated_contract` is a dict.
    3. Synthesise minimal contract from outline-level attributes on the chapter.
    """
    from models.handoff_schemas import NegotiatedChapterContract

    nc = getattr(chapter, "negotiated_contract", None)
    if isinstance(nc, NegotiatedChapterContract):
        return nc
    if isinstance(nc, dict) and nc:
        try:
            return NegotiatedChapterContract.model_validate(nc)
        except Exception:
            pass

    # Synthesise from outline attributes (graceful fallback for pre-contract chapters)
    outline = getattr(chapter, "outline", None)
    must_mention: list[str] = []
    threads: list[str] = []
    pacing = "rising"

    if outline is not None:
        chars_inv = getattr(outline, "characters_involved", None) or []
        must_mention = list(chars_inv)
        pacing = str(getattr(outline, "pacing_type", "rising") or "rising")

    return NegotiatedChapterContract(
        chapter_num=ch_num,
        pacing_type=pacing if pacing in ("setup", "rising", "climax", "twist", "cooldown") else "rising",
        must_mention_characters=must_mention,
        threads_advance=threads,
    )


class StoryEnhancer:
    """Viết lại truyện với tính kịch tích cao hơn."""

    LAYER = 2

    def __init__(self):
        self.llm = LLMClient()
        self._layer_model = self.llm.model_for_layer(self.LAYER)
        self.consistency_engine: Optional["ConsistencyEngine"] = None
        # Phase 5: track chapters already rewritten at L1 to prevent loops
        self._rewritten_chapters: set[int] = set()

    def detect_structural_issues(
        self,
        draft: StoryDraft,
        arc_waypoints: Optional[list] = None,
        threshold: float = 0.7,
    ) -> dict[int, list]:
        """Detect structural issues per chapter before enhancement.

        Uses `pipeline.semantic.structural_detector.detect_structural_issues`
        (NER + embedding, Sprint 2 P4).  Returns
        {chapter_number: [StructuralIssue, ...]} using the legacy adapter so
        that `orchestrator_layers.py` (consumer) continues to work unchanged.

        Only chapters NOT in _rewritten_chapters are checked (loop prevention).
        Non-fatal: returns empty dict on any error.
        """
        if not _STRUCTURAL_DETECTOR_AVAILABLE or _detect_structural_issues is None:
            return {}
        try:
            from models.handoff_schemas import NegotiatedChapterContract

            characters = list(getattr(draft, "characters", []) or [])
            # Build a per-chapter contract from negotiated_contract if present,
            # else synthesise a minimal one from the outline (graceful fallback).
            results: dict[int, list] = {}
            for chapter in draft.chapters:
                ch_num = chapter.chapter_number
                if ch_num in self._rewritten_chapters:
                    continue

                contract = _resolve_contract(chapter, ch_num)

                findings = _detect_structural_issues(
                    chapter=chapter,
                    contract=contract,
                    characters=characters,
                    thread_threshold=threshold,
                )
                # Filter by severity threshold (mirror old behaviour)
                findings = [f for f in findings if f.severity >= threshold]
                if findings:
                    # Adapt to legacy StructuralIssue for orchestrator_layers consumer
                    results[ch_num] = [f.to_legacy_issue() for f in findings]
            return results
        except Exception as e:
            logger.warning(f"Structural detection failed (non-fatal): {e}")
            return {}

    def enhance_chapter(
        self,
        chapter: Chapter,
        sim_result: SimulationResult,
        word_count: int = 2000,
        total_chapters: int = 1,
        genre: str = "",
        draft=None,
    ) -> Chapter:
        """Tăng cường kịch tính cho một chương.

        Args:
            total_chapters: Tổng số chương trong truyện (để phân bổ sự kiện đều).
        """
        try:
            from services.trace_context import set_chapter, set_module
            set_chapter(getattr(chapter, "chapter_number", None))
            set_module("l2_enhancer")
        except Exception:
            pass

        # --- Scene-level enhancement (Phase 4) ---
        try:
            from pipeline.layer2_enhance.scene_enhancer import SceneEnhancer
            from pipeline.layer2_enhance.dialogue_subtext import DialogueSubtextAnalyzer
            from pipeline.layer2_enhance.thematic_tracker import ThematicTracker

            _subtext_guidance = ""
            _thematic_guidance = ""

            # Build subtext guidance from psychology + knowledge if available
            if draft and hasattr(draft, "characters") and draft.characters:
                try:
                    _analyzer = DialogueSubtextAnalyzer()
                    _psych_map = getattr(draft, "_psychology_map", {})
                    _knowledge = getattr(draft, "_knowledge_state", {})
                    if _psych_map:
                        _subtext_guidance = _analyzer.generate_subtext_guidance(
                            _psych_map, _knowledge
                        )
                except Exception as _e:
                    logger.debug(f"Subtext guidance failed (non-fatal): {_e}")

            # Build thematic guidance if theme profile is attached to draft
            if draft:
                try:
                    _theme = getattr(draft, "_theme_profile", None)
                    if _theme is None:
                        _tracker = ThematicTracker()
                        _theme = _tracker.extract_theme(draft)
                        draft._theme_profile = _theme  # cache for subsequent chapters
                    if _theme and _theme.central_theme:
                        _tracker = ThematicTracker()
                        _ch_score = _tracker.score_chapter_theme(chapter, _theme)
                        _thematic_guidance = _tracker.generate_thematic_guidance(
                            _theme, _ch_score
                        )
                except Exception as _e:
                    logger.debug(f"Thematic guidance failed (non-fatal): {_e}")

            scene_enhancer = SceneEnhancer()
            _signals_on = True
            try:
                _signals_on = bool(getattr(ConfigManager().load().pipeline, "l2_use_l1_signals", True))
            except Exception:
                pass
            _chapter_summary = None
            _thread_state = None
            _arc_context = ""
            _pacing_directive = ""
            if _signals_on:
                _chapter_summary = getattr(chapter, "structured_summary", None)
                if draft is not None:
                    from pipeline.layer2_enhance import _envelope_access as _env
                    _thread_state = _env.threads(draft)
                    _arc_context = _build_arc_context(draft, chapter.chapter_number)
                _pacing_directive = _extract_pacing_directive(draft, chapter.chapter_number)
            # L2-E: Use pacing_type from outline as fallback for per-chapter drama intensity
            if not _pacing_directive:
                _pacing_directive = _extract_pacing_type(draft, chapter.chapter_number)
            # Get consistency constraints if engine is available
            _consistency_constraints = ""
            if self.consistency_engine:
                try:
                    _consistency_constraints = self.consistency_engine.get_constraints_for_chapter(
                        chapter.chapter_number
                    )
                except Exception as _ce:
                    logger.debug(f"Consistency constraints failed: {_ce}")
            # L2-B: Append knowledge constraints to prevent hallucinating facts
            _knowledge_enabled = True
            try:
                _knowledge_enabled = bool(ConfigManager().load().pipeline.l2_knowledge_constraints)
            except Exception:
                pass
            if _knowledge_enabled:
                try:
                    _knowledge_block = _build_knowledge_constraints(sim_result, draft)
                    if _knowledge_block:
                        _consistency_constraints = (_consistency_constraints + "\n\n" + _knowledge_block).strip()
                except Exception as _ke:
                    logger.debug(f"Knowledge constraints failed: {_ke}")
            # L2-F: Coherence pre-check — inject constraints for potential violations
            try:
                _prev_chapters = []
                if draft and hasattr(draft, "chapters"):
                    _prev_chapters = [c for c in draft.chapters if c.chapter_number < chapter.chapter_number]
                _coherence_block = _precheck_coherence(self.llm, chapter, draft, _prev_chapters)
                if _coherence_block:
                    _consistency_constraints = (_consistency_constraints + "\n\n" + _coherence_block).strip()
            except Exception as _coh_e:
                logger.debug(f"Coherence pre-check failed: {_coh_e}")

            enhanced_chapter = scene_enhancer.enhance_chapter_by_scenes(
                chapter, sim_result, genre, draft,
                subtext_guidance=_subtext_guidance,
                thematic_guidance=_thematic_guidance,
                chapter_summary=_chapter_summary,
                thread_state=_thread_state,
                arc_context=_arc_context,
                pacing_directive=_pacing_directive,
                consistency_constraints=_consistency_constraints,
            )
        except Exception as e:
            # Graceful degradation: return original chapter on enhancement failure
            logger.warning(
                f"Scene-level enhancement failed for chapter {chapter.chapter_number}: {e}. "
                "Returning original chapter."
            )
            return chapter

        # Sprint 1 Task 3: drama contract validation + optional retry
        enhanced_chapter = self._apply_contract_validation(
            enhanced_chapter=enhanced_chapter,
            original=chapter,
            sim_result=sim_result,
            genre=genre,
            draft=draft,
            subtext_guidance=_subtext_guidance,
            thematic_guidance=_thematic_guidance,
            chapter_summary=_chapter_summary,
            thread_state=_thread_state,
            arc_context=_arc_context,
            pacing_directive=_pacing_directive,
            consistency_constraints=_consistency_constraints,
        )
        # Sprint 2 Task 2: voice contract validation + refine-with-hint (graduated revert)
        enhanced_chapter = self._apply_voice_validation(
            enhanced_chapter=enhanced_chapter,
            original=chapter,
            sim_result=sim_result,
            genre=genre,
            draft=draft,
            subtext_guidance=_subtext_guidance,
            thematic_guidance=_thematic_guidance,
            chapter_summary=_chapter_summary,
            thread_state=_thread_state,
            arc_context=_arc_context,
            pacing_directive=_pacing_directive,
            consistency_constraints=_consistency_constraints,
        )
        return enhanced_chapter

    def _apply_contract_validation(
        self,
        *,
        enhanced_chapter,
        original,
        sim_result,
        genre,
        draft,
        subtext_guidance,
        thematic_guidance,
        chapter_summary,
        thread_state,
        arc_context,
        pacing_directive,
        consistency_constraints,
    ):
        """Validate enhanced chapter against DramaContract; retry once on miss."""
        contracts_raw = getattr(sim_result, "chapter_contracts", None) or {}
        ch_num = enhanced_chapter.chapter_number
        raw = contracts_raw.get(ch_num) or contracts_raw.get(str(ch_num))
        if not raw:
            return enhanced_chapter

        try:
            from models.handoff_schemas import NegotiatedChapterContract
            from pipeline.layer2_enhance.chapter_contract import (
                validate_chapter_against_contract, build_retry_hint,
            )
            from pipeline.layer2_enhance.scene_enhancer import SceneEnhancer
            contract = NegotiatedChapterContract.model_validate(raw) if isinstance(raw, dict) else raw

            try:
                cfg = ConfigManager().load().pipeline
            except Exception:
                cfg = None

            tolerance = float(getattr(cfg, "contract_drama_tolerance", 0.15)) if cfg else 0.15
            contract = contract.model_copy(update={"drama_tolerance": tolerance})
            cheap = bool(getattr(cfg, "contract_cheap_validation", True)) if cfg else True
            retry_enabled = bool(getattr(cfg, "enable_contract_retry", True)) if cfg else True
            retry_max = int(getattr(cfg, "contract_retry_max", 1)) if cfg else 1

            validation = validate_chapter_against_contract(
                self.llm, enhanced_chapter.content, contract,
                model_tier="cheap" if cheap else "default",
            )
            logger.info(
                "[CONTRACT] ch%d pass=%s compliance=%.2f drama=%.2f/%.2f",
                ch_num, validation.passed, validation.compliance_score,
                validation.drama_actual, contract.drama_target,
            )

            if not validation.passed and retry_enabled and retry_max > 0:
                hint = build_retry_hint(validation)
                logger.info("[CONTRACT] ch%d retry with hint: %s", ch_num, hint.replace("\n", " | "))
                try:
                    scene_enhancer = SceneEnhancer()
                    injected_guidance = (subtext_guidance or "") + "\n\n[RETRY HINT]\n" + hint
                    retried = scene_enhancer.enhance_chapter_by_scenes(
                        original, sim_result, genre, draft,
                        subtext_guidance=injected_guidance,
                        thematic_guidance=thematic_guidance,
                        chapter_summary=chapter_summary,
                        thread_state=thread_state,
                        arc_context=arc_context,
                        pacing_directive=pacing_directive,
                        consistency_constraints=consistency_constraints,
                    )
                    retry_validation = validate_chapter_against_contract(
                        self.llm, retried.content, contract,
                        model_tier="cheap" if cheap else "default",
                    )
                    retry_validation.retry_attempted = True
                    if retry_validation.compliance_score >= validation.compliance_score:
                        enhanced_chapter = retried
                        validation = retry_validation
                    logger.info(
                        "[CONTRACT] ch%d retry pass=%s compliance=%.2f",
                        ch_num, validation.passed, validation.compliance_score,
                    )
                except Exception as _re:
                    logger.warning(f"Contract retry ch{ch_num} failed: {_re}")

            try:
                enhanced_chapter.contract_validation = validation.model_dump()
            except Exception:
                pass
        except Exception as _ve:
            logger.warning(f"Contract validation ch{ch_num} failed (non-fatal): {_ve}")

        return enhanced_chapter

    def _apply_voice_validation(
        self,
        *,
        enhanced_chapter,
        original,
        sim_result,
        genre,
        draft,
        subtext_guidance,
        thematic_guidance,
        chapter_summary,
        thread_state,
        arc_context,
        pacing_directive,
        consistency_constraints,
    ):
        """Sprint 2 Task 2: validate voice → refine-with-hint; binary revert last-resort (<floor)."""
        contracts_raw = getattr(sim_result, "voice_contracts", None) or {}
        ch_num = enhanced_chapter.chapter_number
        raw = contracts_raw.get(ch_num) or contracts_raw.get(str(ch_num))
        if not raw:
            return enhanced_chapter

        try:
            from pipeline.layer2_enhance.chapter_contract import (
                VoiceContract, validate_chapter_voice, build_voice_retry_hint,
            )
            from pipeline.layer2_enhance.scene_enhancer import SceneEnhancer
            contract = VoiceContract(**raw) if isinstance(raw, dict) else raw

            try:
                cfg = ConfigManager().load().pipeline
            except Exception:
                cfg = None

            if cfg is not None and not bool(getattr(cfg, "enable_voice_contract", True)):
                return enhanced_chapter

            min_comp = float(getattr(cfg, "voice_min_compliance", 0.75)) if cfg else 0.75
            contract.min_compliance = min_comp
            retry_enabled = bool(getattr(cfg, "enable_voice_contract_retry", True)) if cfg else True
            retry_max = int(getattr(cfg, "voice_contract_retry_max", 1)) if cfg else 1
            revert_floor = float(getattr(cfg, "voice_binary_revert_floor", 0.5)) if cfg else 0.5

            validation = validate_chapter_voice(self.llm, enhanced_chapter.content, contract)
            logger.info(
                "[VOICE] ch%d pass=%s compliance=%.2f drifted=%s",
                ch_num, validation.passed, validation.overall_compliance,
                validation.drifted_characters,
            )

            if not validation.passed and retry_enabled and retry_max > 0:
                hint = build_voice_retry_hint(validation)
                logger.info("[VOICE] ch%d refine with hint: %s", ch_num, hint.replace("\n", " | "))
                try:
                    scene_enhancer = SceneEnhancer()
                    injected = (subtext_guidance or "") + "\n\n[VOICE HINT]\n" + hint
                    refined = scene_enhancer.enhance_chapter_by_scenes(
                        original, sim_result, genre, draft,
                        subtext_guidance=injected,
                        thematic_guidance=thematic_guidance,
                        chapter_summary=chapter_summary,
                        thread_state=thread_state,
                        arc_context=arc_context,
                        pacing_directive=pacing_directive,
                        consistency_constraints=consistency_constraints,
                    )
                    retry_val = validate_chapter_voice(self.llm, refined.content, contract)
                    retry_val.retry_attempted = True
                    if retry_val.overall_compliance >= validation.overall_compliance:
                        enhanced_chapter = refined
                        validation = retry_val
                    logger.info(
                        "[VOICE] ch%d refine pass=%s compliance=%.2f",
                        ch_num, validation.passed, validation.overall_compliance,
                    )
                except Exception as _re:
                    logger.warning(f"Voice refine ch{ch_num} failed: {_re}")

            # Last-resort binary revert — only catastrophic drift
            if not validation.passed and validation.overall_compliance < revert_floor:
                try:
                    from pipeline.layer2_enhance.voice_fingerprint import (
                        VoiceFingerprintEngine, enforce_voice_preservation,
                    )
                    engine = VoiceFingerprintEngine()
                    engine.build_from_draft(draft, dedup_l1=True)
                    characters = [c for c in (getattr(draft, "characters", []) or [])
                                  if getattr(c, "name", "") in validation.drifted_characters]
                    if characters:
                        preserved, vp_res = enforce_voice_preservation(
                            engine,
                            original.content or "",
                            enhanced_chapter.content or "",
                            characters,
                            drift_threshold=0.4,
                            revert_threshold=0.3,
                        )
                        if vp_res.reverted_count > 0:
                            enhanced_chapter.content = preserved
                            validation.binary_reverted = True
                            logger.warning(
                                "[VOICE] ch%d catastrophic (%.2f<%.2f) → binary reverted %d dialogue(s)",
                                ch_num, validation.overall_compliance, revert_floor, vp_res.reverted_count,
                            )
                except Exception as _be:
                    logger.warning(f"Voice binary revert ch{ch_num} failed: {_be}")

            try:
                enhanced_chapter.voice_validation = validation.model_dump()
            except Exception:
                pass
        except Exception as _ve:
            logger.warning(f"Voice validation ch{ch_num} failed (non-fatal): {_ve}")

        return enhanced_chapter

    def enhance_story(
        self,
        draft: StoryDraft,
        sim_result: SimulationResult,
        word_count: int = 2000,
        progress_callback=None,
        theme_profile=None,
        chapter_done_callback=None,
    ) -> EnhancedStory:
        """Tăng cường kịch tính cho toàn bộ truyện.

        Args:
            chapter_done_callback: Optional callback(Chapter) called when each chapter is done.
                                   P-C: enables incremental streaming to client.
        """

        # Cache theme profile on draft so enhance_chapter can access it
        if theme_profile is not None:
            draft._theme_profile = theme_profile

        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        # Build consistency engine (A-E improvements)
        _consistency_enabled = True
        try:
            _consistency_enabled = bool(ConfigManager().load().pipeline.l2_consistency_engine)
        except Exception:
            pass
        if _CONSISTENCY_AVAILABLE and _consistency_enabled and self.consistency_engine is None:
            try:
                _log("🔧 Building consistency engine...")
                self.consistency_engine = ConsistencyEngine()
                self.consistency_engine.build_from_draft(draft, progress_callback=_log)
            except Exception as e:
                logger.warning(f"ConsistencyEngine build failed (non-fatal): {e}")
                self.consistency_engine = None

        enhanced = EnhancedStory(
            title=draft.title,
            genre=draft.genre,
            enhancement_notes=[],
        )

        # Sprint 1 Task 3: build per-chapter drama contracts from sim_result
        try:
            _cfg = ConfigManager().load().pipeline
            _contracts_on = bool(getattr(_cfg, "enable_simulator_contracts", True))
        except Exception:
            _contracts_on = True
        if _contracts_on and not getattr(sim_result, "chapter_contracts", None):
            try:
                from pipeline.layer2_enhance.chapter_contract import build_chapter_contracts
                _ch_nums = [c.chapter_number for c in draft.chapters]
                _contracts = build_chapter_contracts(sim_result, _ch_nums)
                sim_result.chapter_contracts = {
                    k: v.model_dump() for k, v in _contracts.items()
                }
                _log(f"[CONTRACT] Built {len(_contracts)} drama contracts")
            except Exception as _ce:
                logger.warning(f"build_chapter_contracts failed (non-fatal): {_ce}")

        # Sprint 2 Task 2: build per-chapter voice contracts from L1 voice_profiles
        try:
            _voice_on = bool(getattr(_cfg, "enable_voice_contract", True))
        except Exception:
            _voice_on = True
        if _voice_on and not getattr(sim_result, "voice_contracts", None):
            try:
                from pipeline.layer2_enhance.chapter_contract import build_voice_contracts
                from pipeline.layer2_enhance import _envelope_access as _env
                _vp = _env.voice_profiles(draft)
                if _vp:
                    _min_comp = float(getattr(_cfg, "voice_min_compliance", 0.75))
                    _outlines = getattr(draft, "outlines", []) or []
                    _vcs = build_voice_contracts(
                        _vp,
                        _outlines,
                        characters=getattr(draft, "characters", []) or [],
                        min_compliance=_min_comp,
                    )
                    sim_result.voice_contracts = {k: v.model_dump() for k, v in _vcs.items()}
                    _log(f"[VOICE] Built {len(_vcs)} voice contracts")
            except Exception as _ve:
                logger.warning(f"build_voice_contracts failed (non-fatal): {_ve}")

        total_chapters = len(draft.chapters)
        max_workers = ConfigManager().llm.max_parallel_workers

        _log(f"✨ Đang tăng cường kịch tính {total_chapters} chương (parallel, {max_workers} workers)...")

        # Migrate from ThreadPoolExecutor + as_completed to asyncio.gather + run_in_executor.
        # enhance_chapter() wraps a blocking LLM call; run_in_executor offloads each to the
        # default thread pool while asyncio.gather dispatches all coroutines concurrently,
        # freeing the event loop between submissions.
        async def _enhance_all() -> dict[int, Chapter]:
            loop = asyncio.get_running_loop()
            chapters_list = list(draft.chapters)

            async def _one(chapter: Chapter) -> tuple[int, Chapter]:
                ch_num = chapter.chapter_number
                try:
                    result = await loop.run_in_executor(
                        None, self.enhance_chapter,
                        chapter, sim_result, word_count, total_chapters, draft.genre, draft,
                    )
                    _log(f"✨ Chương {ch_num} đã tăng cường xong")
                    # P-C: Incremental publish — notify when chapter is done
                    if chapter_done_callback:
                        try:
                            chapter_done_callback(result)
                        except Exception as _cb_e:
                            logger.debug(f"Chapter done callback failed: {_cb_e}")
                    return ch_num, result
                except Exception as e:
                    logger.warning(f"Lỗi enhance chương {ch_num}: {e}")
                    # Fallback: keep original
                    orig = next(c for c in chapters_list if c.chapter_number == ch_num)
                    return ch_num, orig

            pairs = await asyncio.gather(*[_one(ch) for ch in chapters_list])
            return dict(pairs)

        # Handle nested event loop safely
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already in async context - use nest_asyncio or run in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _enhance_all())
                results = future.result()
        else:
            results = asyncio.run(_enhance_all())

        # Maintain order
        enhanced.chapters = [results[ch.chapter_number] for ch in draft.chapters]

        # Cross-chapter drama curve balancing (#3 improvement)
        _curve_enabled = True
        _curve_type = "rising"
        try:
            cfg = ConfigManager().load().pipeline
            _curve_enabled = bool(getattr(cfg, "l2_drama_curve_balancing", True))
            _curve_type = str(getattr(cfg, "l2_drama_curve_target", "rising"))
        except Exception:
            pass

        if _curve_enabled:
            try:
                from pipeline.layer2_enhance.scene_enhancer import DramaCurveBalancer, SceneEnhancer
                _log("📈 Analyzing drama curve...")

                # Score all chapters to build curve
                scene_enhancer = SceneEnhancer()
                chapter_scores: dict[int, float] = {}
                for ch in enhanced.chapters:
                    try:
                        # Quick drama score using cheap model
                        result = self.llm.generate_json(
                            system_prompt="Đánh giá kịch tính nhanh. Trả về JSON.",
                            user_prompt=f"Đánh giá kịch tính nội dung sau (0-1):\n{ch.content[:2000]}\n\n"
                                        '{"drama_score": 0.6}',
                            temperature=0.2,
                            max_tokens=100,
                            model_tier="cheap",
                        )
                        chapter_scores[ch.chapter_number] = float(result.get("drama_score", 0.5))
                    except Exception:
                        chapter_scores[ch.chapter_number] = 0.5

                # Build curve balancer
                balancer = DramaCurveBalancer(curve_type=_curve_type)
                balancer.set_scores(chapter_scores, total_chapters)
                summary = balancer.get_summary()

                _log(
                    f"📈 Drama curve ({_curve_type}): avg={summary['avg_actual']:.2f} "
                    f"(target={summary['avg_target']:.2f}), {summary['total_adjustments']} adjustments needed"
                )

                # Re-enhance chapters that need curve adjustment
                if summary["total_adjustments"] > 0:
                    _log(f"🔄 Re-enhancing {summary['total_adjustments']} chapters for curve balance...")
                    chapters_to_reenhance = (
                        summary.get("chapters_need_boost", []) +
                        summary.get("chapters_need_reduction", [])
                    )

                    for ch_num in chapters_to_reenhance:
                        try:
                            ch = next(c for c in enhanced.chapters if c.chapter_number == ch_num)
                            orig = next(c for c in draft.chapters if c.chapter_number == ch_num)

                            # Re-enhance with curve directive
                            reenhanced = scene_enhancer.enhance_chapter_by_scenes(
                                chapter=orig,
                                sim_result=sim_result,
                                genre=draft.genre,
                                draft=draft,
                                curve_balancer=balancer,
                            )

                            # Update in enhanced list
                            idx = ch_num - 1
                            if 0 <= idx < len(enhanced.chapters):
                                enhanced.chapters[idx] = reenhanced
                                _log(f"  ✓ Chương {ch_num} curve-adjusted")
                        except Exception as e:
                            logger.warning(f"Curve re-enhance ch{ch_num} failed: {e}")

            except Exception as e:
                logger.warning(f"Drama curve balancing failed (non-fatal): {e}")

        # Enhancement diff tracking (non-fatal)
        try:
            from pipeline.layer2_enhance.enhancement_diff_tracker import track_enhancement_diffs
            track_enhancement_diffs(list(draft.chapters), enhanced.chapters)
        except Exception as e:
            logger.warning(f"Enhancement diff tracking failed (non-fatal): {e}")

        # Consistency validation (A-E improvements)
        if self.consistency_engine:
            _log("🔍 Validating consistency...")
            total_violations = 0
            for orig_ch, enh_ch in zip(draft.chapters, enhanced.chapters):
                try:
                    violations = self.consistency_engine.validate_enhanced_chapter(
                        orig_ch.content or "",
                        enh_ch.content or "",
                        enh_ch.chapter_number,
                    )
                    if violations:
                        total_violations += len(violations)
                        # Attach violations to chapter changelog
                        try:
                            enh_ch.enhancement_changelog = list(
                                getattr(enh_ch, "enhancement_changelog", []) or []
                            )
                            for v in violations:
                                enh_ch.enhancement_changelog.append(
                                    f"[{v.type}:{v.severity}] {v.description}"
                                )
                        except Exception:
                            pass
                except Exception as ve:
                    logger.debug(f"Consistency validation ch{enh_ch.chapter_number} error: {ve}")
            if total_violations > 0:
                _log(f"⚠️ Phát hiện {total_violations} vi phạm nhất quán")
            else:
                _log("✅ Không phát hiện vi phạm nhất quán")

        # Voice preservation enforcement (Phase 6)
        _voice_enabled = True
        try:
            _voice_enabled = bool(ConfigManager().load().pipeline.l2_voice_preservation)
        except Exception:
            pass
        if _voice_enabled:
            try:
                from pipeline.layer2_enhance.voice_fingerprint import (
                    VoiceFingerprintEngine, enforce_voice_preservation,
                )
                _log("🎤 Checking voice preservation...")
                voice_engine = VoiceFingerprintEngine()
                voice_engine.build_from_draft(draft)

                total_reverted = 0
                total_drift = 0.0
                characters = getattr(draft, "characters", []) or []

                for orig_ch, enh_ch in zip(draft.chapters, enhanced.chapters):
                    preserved_content, vp_result = enforce_voice_preservation(
                        voice_engine,
                        orig_ch.content or "",
                        enh_ch.content or "",
                        characters,
                        drift_threshold=0.4,
                        revert_threshold=0.3,
                    )
                    if vp_result.reverted_count > 0:
                        enh_ch.content = preserved_content
                        total_reverted += vp_result.reverted_count
                        # Log to changelog
                        try:
                            enh_ch.enhancement_changelog = list(
                                getattr(enh_ch, "enhancement_changelog", []) or []
                            )
                            enh_ch.enhancement_changelog.append(
                                f"[voice:reverted] {vp_result.reverted_count} dialogue(s)"
                            )
                        except Exception:
                            pass
                    total_drift += vp_result.drift_severity

                avg_drift = total_drift / max(1, len(enhanced.chapters))
                if total_reverted > 0:
                    _log(f"🎤 Voice: {total_reverted} dialogues reverted (avg drift: {avg_drift:.0%})")
                else:
                    _log(f"✅ Voice preserved (avg drift: {avg_drift:.0%})")
            except Exception as e:
                logger.warning(f"Voice preservation failed (non-fatal): {e}")

        # Thread resolution enforcement (Phase 6)
        _thread_enforce_enabled = True
        try:
            _thread_enforce_enabled = bool(ConfigManager().load().pipeline.l2_consistency_threads)
        except Exception:
            pass
        if _thread_enforce_enabled:
            try:
                from pipeline.layer2_enhance.thread_watchdog import (
                    ThreadWatchdog, ThreadResolutionEnforcer, should_enforce_resolution,
                )
                total_chapters = len(enhanced.chapters)
                if should_enforce_resolution(total_chapters, total_chapters):
                    _log("🔗 Checking thread resolution...")
                    watchdog = ThreadWatchdog().load_from_draft(draft)
                    enforcer = ThreadResolutionEnforcer(watchdog)

                    total_forced = 0
                    for ch in enhanced.chapters:
                        if should_enforce_resolution(ch.chapter_number, total_chapters):
                            modified_content, resolutions = enforcer.force_resolution(
                                ch.content or "",
                                ch.chapter_number,
                                total_chapters,
                            )
                            if resolutions:
                                ch.content = modified_content
                                total_forced += len(resolutions)
                                try:
                                    ch.enhancement_changelog = list(
                                        getattr(ch, "enhancement_changelog", []) or []
                                    )
                                    for res in resolutions:
                                        ch.enhancement_changelog.append(
                                            f"[thread:resolved] {res.get('thread', '')[:40]}"
                                        )
                                except Exception:
                                    pass

                    summary = enforcer.get_enforcement_summary()
                    if total_forced > 0:
                        _log(
                            f"🔗 Threads: force-resolved {total_forced}, "
                            f"total {summary['resolved']}/{summary['total_threads']} resolved"
                        )
                    elif summary["unresolved"] > 0:
                        _log(f"⚠️ Threads: {summary['unresolved']} unresolved at story end")
                    else:
                        _log("✅ All threads resolved")
            except Exception as e:
                logger.warning(f"Thread resolution enforcement failed (non-fatal): {e}")

        # Tính điểm kịch tính tổng thể (chuyển từ 0-1 sang 1-5)
        if sim_result.events:
            raw = sum(
                e.drama_score for e in sim_result.events
            ) / len(sim_result.events)
            enhanced.drama_score = round(1.0 + raw * 4.0, 2)  # Map 0-1 → 1-5
        enhanced.enhancement_notes = sim_result.drama_suggestions

        _log(
            f"✅ Layer 2 hoàn tất! Điểm kịch tính: {enhanced.drama_score:.2f}"
        )
        return enhanced

    def _find_weak_chapters(self, enhanced: EnhancedStory) -> list[dict]:
        """Analyze chapters and return detailed weakness info for targeted rewriting."""
        weak = []
        for ch in enhanced.chapters:
            try:
                result = self.llm.generate_json(
                    system_prompt="Đánh giá kịch tính chi tiết. Trả về JSON.",
                    user_prompt=prompt_templates.QUICK_DRAMA_CHECK.format(
                        content=ch.content[:3000],
                    ),
                    temperature=0.2,
                    max_tokens=300,
                    model_tier="cheap",
                )
                score = result.get("drama_score", 0.5)
                if score < MIN_DRAMA_SCORE:
                    weak.append({
                        "chapter_number": ch.chapter_number,
                        "score": score,
                        "weak_points": result.get("weak_points", []),
                        "strong_points": result.get("strong_points", []),
                    })
            except Exception as e:
                logger.debug(f"Drama check failed for ch {ch.chapter_number}: {e}")
        return weak

    def enhance_with_feedback(
        self,
        draft: StoryDraft,
        sim_result: SimulationResult,
        word_count: int = 2000,
        progress_callback=None,
        theme_profile=None,
    ) -> EnhancedStory:
        """Enhance story with iterative feedback — re-enhance weak chapters."""
        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        # Bug #10: Ensure knowledge registry exists (mandatory for state tracking)
        if getattr(draft, "_knowledge_registry", None) is None:
            try:
                from pipeline.layer2_enhance.knowledge_system import KnowledgeRegistry
                draft._knowledge_registry = KnowledgeRegistry()
                # Seed with initial character states if available
                for ch in (draft.characters or []):
                    draft._knowledge_registry.register_fact(
                        character=ch.name,
                        fact_type="initial_state",
                        content=f"{ch.role}: {ch.personality}",
                        chapter=0,
                    )
                _log("[KR] Đã khởi tạo knowledge registry")
            except Exception as e:
                logger.warning(f"Knowledge registry init failed (non-fatal): {e}")

        # Reset consistency engine for fresh build
        self.consistency_engine = None

        enhanced = self.enhance_story(draft, sim_result, word_count, progress_callback, theme_profile)

        genre = draft.genre if hasattr(draft, 'genre') else ""

        # Log drama_multiplier influence: event scores already incorporate agent multipliers
        # from simulator._apply_escalation. Report average event drama_score as proxy.
        if sim_result.events:
            avg_event_score = sum(e.drama_score for e in sim_result.events) / len(sim_result.events)
            logger.info(
                f"Drama multiplier influence: avg event drama_score={avg_event_score:.3f} "
                f"across {len(sim_result.events)} events (agent multipliers embedded)"
            )

        for round_num in range(1, MAX_REENHANCE_ROUNDS + 1):
            weak_analyses = self._find_weak_chapters(enhanced)
            if not weak_analyses:
                _log(f"✅ Feedback round {round_num}: all chapters pass drama threshold")
                break
            _log(f"🔄 Feedback round {round_num}: re-enhancing {len(weak_analyses)} weak chapters (parallel)")

            # L2-A: Parallel feedback rewrite — process all weak chapters concurrently.
            async def _rewrite_weak_parallel() -> dict[int, Chapter]:
                loop = asyncio.get_running_loop()

                def _rewrite_one(analysis: dict) -> tuple[int, Chapter | None]:
                    ch_num = analysis["chapter_number"]
                    idx = ch_num - 1
                    if idx < 0 or idx >= len(enhanced.chapters):
                        return ch_num, None
                    # P-F: Per-chapter L2 retry with backoff
                    _retry_max = 2
                    _backoff = 1.5
                    try:
                        cfg = ConfigManager().load().pipeline
                        _retry_max = int(getattr(cfg, "l2_chapter_retry_max", 2))
                        _backoff = float(getattr(cfg, "l2_chapter_retry_backoff", 1.5))
                    except Exception:
                        pass
                    _delay = 1.0
                    for attempt in range(_retry_max + 1):
                        try:
                            genre_hints = get_genre_enhancement_hints(genre, ch_num, len(enhanced.chapters))
                            weak_text = "\n".join(f"- {wp}" for wp in analysis.get("weak_points", []))
                            strong_text = "\n".join(f"- {sp}" for sp in analysis.get("strong_points", []))
                            rewrite_prompt = prompt_templates.REENHANCE_CHAPTER.format(
                                chapter_content=enhanced.chapters[idx].content[:6000],
                                weak_points=weak_text or "Kịch tính chung còn yếu",
                                strong_points=strong_text or "Không có điểm mạnh nổi bật",
                                genre_hints=genre_hints,
                                suggestions="\n".join(sim_result.drama_suggestions[:3]),
                                word_count=word_count,
                            )
                            rewrite_prompt += "\n\n[NHẮC LẠI: Viết hoàn toàn bằng tiếng Việt. Không dùng tiếng Anh hay ngôn ngữ khác.]"
                            rewritten = self.llm.generate(
                                system_prompt=(
                                    "Bạn là nhà văn tài năng chuyên viết truyện bằng tiếng Việt. "
                                    "BẮT BUỘC: Toàn bộ output phải viết bằng tiếng Việt, không được dùng ngôn ngữ khác."
                                ),
                                user_prompt=rewrite_prompt,
                                max_tokens=8192,
                                model=self._layer_model,
                            )
                            return ch_num, Chapter(
                                chapter_number=ch_num,
                                title=enhanced.chapters[idx].title,
                                content=rewritten,
                                word_count=count_words(rewritten),
                                summary=enhanced.chapters[idx].summary,
                            )
                        except Exception as e:
                            if attempt < _retry_max:
                                logger.warning(f"Feedback rewrite ch{ch_num} attempt {attempt+1} failed: {e}, retrying in {_delay:.1f}s")
                                time.sleep(_delay)
                                _delay *= _backoff
                            else:
                                logger.warning(f"Feedback rewrite ch{ch_num} failed after {_retry_max+1} attempts: {e}")
                                return ch_num, None
                    return ch_num, None

                async def _one(analysis: dict) -> tuple[int, Chapter | None]:
                    return await loop.run_in_executor(None, _rewrite_one, analysis)

                pairs = await asyncio.gather(*[_one(a) for a in weak_analyses])
                return {ch_num: ch for ch_num, ch in pairs if ch is not None}

            try:
                try:
                    _loop = asyncio.get_running_loop()
                except RuntimeError:
                    _loop = None
                if _loop and _loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, _rewrite_weak_parallel())
                        rewritten_map = future.result()
                else:
                    rewritten_map = asyncio.run(_rewrite_weak_parallel())
            except Exception as e:
                logger.warning(f"Parallel feedback rewrite failed: {e}")
                rewritten_map = {}

            for analysis in weak_analyses:
                ch_num = analysis["chapter_number"]
                idx = ch_num - 1
                if ch_num in rewritten_map:
                    rewritten_ch = rewritten_map[ch_num]
                    # L2-C: Inline contract + voice validation after feedback rewrite
                    try:
                        contracts_raw = getattr(sim_result, "chapter_contracts", None) or {}
                        raw_contract = contracts_raw.get(ch_num) or contracts_raw.get(str(ch_num))
                        if raw_contract:
                            from models.handoff_schemas import NegotiatedChapterContract
                            from pipeline.layer2_enhance.chapter_contract import (
                                validate_chapter_against_contract,
                            )
                            contract = NegotiatedChapterContract.model_validate(raw_contract) if isinstance(raw_contract, dict) else raw_contract
                            val = validate_chapter_against_contract(
                                self.llm, rewritten_ch.content, contract, model_tier="cheap",
                            )
                            try:
                                rewritten_ch.contract_validation = val.model_dump()
                            except Exception:
                                pass
                            if not val.passed:
                                logger.info(f"[L2-C] ch{ch_num} feedback-rewrite contract: {val.compliance_score:.2f}")
                    except Exception as _cv:
                        logger.debug(f"Inline contract validation ch{ch_num}: {_cv}")
                    try:
                        voice_raw = getattr(sim_result, "voice_contracts", None) or {}
                        raw_voice = voice_raw.get(ch_num) or voice_raw.get(str(ch_num))
                        if raw_voice:
                            from pipeline.layer2_enhance.chapter_contract import (
                                VoiceContract, validate_chapter_voice,
                            )
                            vc = VoiceContract(**raw_voice) if isinstance(raw_voice, dict) else raw_voice
                            vv = validate_chapter_voice(self.llm, rewritten_ch.content, vc)
                            try:
                                rewritten_ch.voice_validation = vv.model_dump()
                            except Exception:
                                pass
                            if not vv.passed:
                                logger.info(f"[L2-C] ch{ch_num} feedback-rewrite voice: {vv.overall_compliance:.2f}")
                    except Exception as _vv:
                        logger.debug(f"Inline voice validation ch{ch_num}: {_vv}")
                    enhanced.chapters[idx] = rewritten_ch
                    _log(f"  ✓ Chương {ch_num}: score {analysis['score']:.2f} → re-enhanced")

        # Coherence validation (non-fatal)
        try:
            from pipeline.layer2_enhance.coherence_validator import validate_coherence, fix_coherence_issues
            _log("🔍 Đang kiểm tra tính nhất quán...")
            issues = validate_coherence(self.llm, enhanced, draft)
            if issues:
                critical_count = sum(1 for i in issues if i.get("severity") == "critical")
                _log(f"⚠️ Phát hiện {len(issues)} vấn đề nhất quán ({critical_count} critical)")
                if critical_count > 0:
                    fixed = fix_coherence_issues(self.llm, enhanced, issues, word_count)
                    _log(f"✅ Đã sửa {fixed} chương có vấn đề critical")
            else:
                _log("✅ Không phát hiện vấn đề nhất quán")
        except Exception as e:
            logger.warning(f"Coherence validation failed (non-fatal): {e}")

        # Causal audit (Phase B, non-fatal, feature-flagged)
        try:
            _audit_on = bool(getattr(ConfigManager().load().pipeline, "l2_causal_audit", True))
        except Exception:
            _audit_on = True
        if _audit_on:
            try:
                _kr = getattr(draft, "_knowledge_registry", None)
                _cg = getattr(draft, "_causal_graph", None)
                if _kr is not None:
                    from pipeline.layer2_enhance.causal_chain import audit_revelation_causality
                    _log("🔎 Đang kiểm tra nhân quả tiết lộ...")
                    violations = audit_revelation_causality(
                        self.llm, _cg, _kr, enhanced.chapters, enabled=True,
                    )
                    if violations:
                        by_ch: dict[int, list[dict]] = {}
                        for v in violations:
                            by_ch.setdefault(v["chapter_number"], []).append(v)
                        for ch in enhanced.chapters:
                            flags = by_ch.get(ch.chapter_number, [])
                            if not flags:
                                continue
                            try:
                                ch.enhancement_changelog = list(getattr(ch, "enhancement_changelog", []) or [])
                                for v in flags:
                                    ch.enhancement_changelog.append(f"[causality:{v['severity']}] {v['msg']}")
                            except Exception:
                                pass
                        try:
                            object.__setattr__(enhanced, "_causality_flags", violations)
                        except Exception:
                            pass
                        _log(f"⚠️ Nhân quả: {len(violations)} vi phạm trên {len(by_ch)} chương")
                    else:
                        _log("✅ Nhân quả tiết lộ hợp lệ")
            except Exception as e:
                logger.warning(f"Causal audit failed (non-fatal): {e}")

        # Contract gate (Phase E, non-fatal, feature-flagged)
        try:
            _gate_on = bool(getattr(ConfigManager().load().pipeline, "l2_contract_gate", True))
        except Exception:
            _gate_on = True
        if _gate_on:
            try:
                from pipeline.layer2_enhance.contract_gate import apply_contract_gate
                from pipeline.layer2_enhance import _envelope_access as _env
                _draft_threads = _env.threads(draft)
                _log("📋 Đang kiểm tra hợp đồng chương...")
                stats = apply_contract_gate(self.llm, enhanced, _draft_threads, enabled=True)
                if stats.get("rewrites", 0) > 0:
                    _log(
                        f"🔧 Contract gate: {stats['rewrites']} chương viết lại "
                        f"(tổng {stats.get('total_failures', 0)} vi phạm)"
                    )
                else:
                    _log(f"✅ Contract gate: {stats.get('total_failures', 0)} vi phạm, không cần viết lại")
            except Exception as e:
                logger.warning(f"Contract gate failed (non-fatal): {e}")

        # Final consistency report (unresolved threads)
        if self.consistency_engine:
            try:
                report = self.consistency_engine.get_final_report()
                if report.unresolved_threads:
                    _log(f"⚠️ Còn {len(report.unresolved_threads)} tuyến truyện chưa giải quyết")
                    try:
                        enhanced.enhancement_notes = list(enhanced.enhancement_notes or [])
                        for ut in report.unresolved_threads[:5]:
                            enhanced.enhancement_notes.append(
                                f"[UNRESOLVED] {ut.get('description', '')[:80]}"
                            )
                    except Exception:
                        pass
                else:
                    _log("✅ Tất cả tuyến truyện đã được giải quyết")
            except Exception as e:
                logger.debug(f"Final consistency report failed: {e}")

        return enhanced
