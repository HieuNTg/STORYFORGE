"""Default values, dataclass configs, and preset constants for StoryForge."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class VoiceConfig:
    """Nested voice-handling config (RFC voice-handling-consolidation Phase A).

    Mirrors the flat voice_* / l2_voice_* fields on PipelineConfig. Both shapes
    are synced via PipelineConfig.__post_init__ — flat fields remain
    authoritative until Phase B flips ownership.

    New call sites should read this nested shape; legacy call sites can keep
    using flat fields without breaking.
    """

    # Validation (L2)
    enabled: bool = True
    min_compliance: float = 0.75
    drift_warn_threshold: float = 0.4
    drift_revert_threshold: float = 0.3
    binary_revert_floor: float = 0.5

    # Contract gate
    contract_enabled: bool = True
    contract_retry_enabled: bool = True
    contract_retry_max: int = 1


@dataclass
class LLMConfig:
    """Cấu hình kết nối LLM API.

    Free Z.AI models (base_url: https://api.z.ai/api/paas/v4):
      glm-4.7-flash   - text, 200K context, 128K output
      glm-4.5-flash   - text, 200K context
      glm-4.6v-flash  - vision, 200K context
    """

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.8
    max_tokens: int = 4096
    # Model routing: cheap model for summaries/analysis
    # How long one request may take before the client gives up. Long-form
    # chapter writing through a local browser bridge measured ~4 minutes for a
    # 2000-word chapter (~13 tok/s), and the old hard-coded 300s ceiling
    # abandoned exactly those calls — while the upstream kept generating,
    # holding its slot, and the pipeline walked the fallback chain for nothing.
    request_timeout: float = 900.0
    cheap_model: str = ""  # empty = use primary model
    cheap_base_url: str = ""  # empty = use primary base_url
    # Multiple API keys for the same provider — auto-rotate on rate limit (429)
    api_keys: list = field(default_factory=list)
    # Each entry: "sk-..." or {"key": "sk-...", "base_url": "https://..."}
    cache_enabled: bool = True
    cache_ttl_days: int = 7
    max_parallel_workers: int = 3
    fallback_models: list = field(default_factory=list)
    # Each entry: {"base_url": "...", "model": "...", "api_key": "..."}
    # Fallback thresholds — used by ModelFallbackManager
    # Switch model if average latency exceeds this. Kept above request_timeout
    # (900s) on purpose: a long-form chapter through a slow local bridge
    # legitimately takes minutes, and the old 2-minute ceiling would blacklist
    # exactly the models request_timeout was raised to accommodate.
    fallback_max_latency_ms: int = 960_000
    fallback_max_cost_per_1k: float = (
        0.01  # Skip fallback models above this cost/1k tokens
    )
    # Chain-level retry when all providers fail (rate-limit storms, outages)
    # Discovered (round-robin) models tried per key before moving on. Providers
    # like OpenRouter expose dozens of free models; adding all of them per key
    # built chains of 50-300 entries, and every one is retried up to MAX_RETRIES
    # times, for every chain pass. Explicitly configured fallback_models are
    # never capped by this — only auto-discovered ones.
    max_discovered_models_per_key: int = 3
    # Hard ceiling on the wall-clock one generate() may spend across its whole
    # fallback chain, including retries and backoff. 0 disables it. Without a
    # ceiling, 3 retries x a long chain x 3 chain passes x a 900s timeout has no
    # finite bound worth the name.
    max_total_call_seconds: float = 1800.0
    chain_retry_max: int = 2  # Max times to retry entire fallback chain
    chain_retry_base_delay: float = 30.0  # Initial delay (seconds) before chain retry
    # Global LLM budget wallet — abort runs that exceed the cap (P0-7).
    # 0.0 disables the cap. Counts cost across all providers/fallbacks within a single pipeline run.
    max_cost_per_run_usd: float = 0.0
    max_total_tokens_per_run: int = 0
    max_calls_per_run: int = 0

    # Per-layer model routing (optional, falls back to primary model)
    # Each layer can use a different provider/model combination
    layer1_model: str = ""  # Story generation
    layer1_base_url: str = ""  # Empty = use primary base_url
    layer1_api_key: str = ""  # Empty = use primary api_key
    layer2_model: str = ""  # Drama analysis
    layer2_base_url: str = ""  # Empty = use primary base_url
    layer2_api_key: str = ""  # Empty = use primary api_key


@dataclass
class PipelineConfig:
    """Cấu hình pipeline tổng thể."""

    # Layer 1 - Tạo truyện
    num_chapters: int = 100
    words_per_chapter: int = 3000
    genre: str = "Tiên Hiệp"
    sub_genres: list = field(default_factory=list)
    writing_style: str = "Miêu tả chi tiết"

    # Idea fidelity (P0 fix): "literal" = enforce proper-noun coverage in outline + verbatim idea injection;
    # "thematic" = idea used loosely, no fidelity guard.
    idea_fidelity_mode: Literal["literal", "thematic"] = "literal"

    # Layer 2 - Mô phỏng tăng kịch tính
    num_simulation_rounds: int = 5
    num_agents: int = 10
    drama_intensity: str = "cao"  # thấp, trung bình, cao

    # Context tracking
    context_window_chapters: int = 5

    # Story Bible — bộ nhớ dài hạn cho truyện 100+ chương
    arc_size: int = 30
    story_bible_enabled: bool = True

    # Ngôn ngữ
    language: str = "vi"

    # Features: user system, image gen, share, PDF
    user_storage_path: str = "data/users"
    image_prompt_style: str = "manhwa comic panel, clean cel shading, bold ink lines"
    share_base_url: str = ""
    pdf_font: str = "NotoSansVN"

    # Image generation provider
    image_provider: str = (
        # none / dalle / sd-api / seedream / huggingface / flowkit / codex /
        # qwen-local
        "none"
    )
    image_api_key: str = ""
    image_api_url: str = ""
    # Codex provider: generate images through the user's own logged-in ChatGPT
    # Plus session (the official "Sign in with ChatGPT" credentials that Codex CLI
    # stores in ~/.codex/auth.json). Leave codex_model empty to auto-detect from
    # ~/.codex/config.toml (falls back to gpt-5.5). No API key needed — it reuses
    # the Codex login and supports reference images for character consistency.
    codex_model: str = ""
    # Qwen local proxy: an OpenAI-compatible server (run separately) that drives
    # chat.qwen.ai. Unlike the other providers it takes an ASPECT RATIO rather
    # than a pixel size, and it can edit an existing image — which is what gives
    # reference-conditioned panels real character consistency instead of the
    # text-only fallback. Leave qwen_local_model empty to use whatever the proxy
    # has as QWEN_IMAGE_MODEL, and qwen_local_size empty for its default (1:1).
    qwen_local_base_url: str = "http://localhost:8000/v1"
    qwen_local_api_key: str = ""
    qwen_local_model: str = ""
    qwen_local_size: str = ""
    # When a panel has character reference images, send the first one to the
    # proxy's edit endpoint. Off = always text-only, which is faster but loses
    # the character likeness the references exist for.
    qwen_local_use_edit_for_refs: bool = True
    qwen_local_timeout: float = 300.0
    # Comic panels generated per chapter (truyện tranh). Each chapter gets this
    # many distinct scene images. Used by both the pipeline media stage and the
    # on-demand reader regen. Acts as the FIXED count when panels_auto is False,
    # and as the fallback when a chapter's content length can't be measured.
    panels_per_chapter: int = 8
    # Dynamic panel count: when True, each chapter's panel count is sized to its
    # own content length (longer / denser chapter → more panels) instead of a
    # rigid number, so pacing stays flexible per chapter. Bounded by panels_min..
    # panels_max; ~1 panel per ``words_per_panel`` words of prose.
    panels_auto: bool = True
    panels_min: int = 4
    panels_max: int = 24
    words_per_panel: int = 200
    # Reliability: a panel whose provider returns no image (e.g. Codex
    # occasionally drops one) is retried up to this many extra times before it is
    # given up and skipped. 0 = no retry (legacy behavior).
    panel_retry_attempts: int = 2
    # How many panels of one chapter are generated at a time. Panels are fully
    # independent — each is one provider call producing one file — but they used
    # to run strictly one after another, so a 20-panel chapter cost 20 serial
    # image round-trips. Kept modest: image endpoints rate-limit far harder than
    # text ones, and the retry above already absorbs the odd transient failure.
    # 1 = fully serial (previous behaviour).
    comic_panel_workers: int = 3

    # Comic Beat→Shot-list stage (Phase 2). When enabled, an LLM beat extractor
    # runs between chapter prose and image generation, splitting each chapter
    # into ordered beats/panels with shot_type, layout/page, dialogue+speaker and
    # screen_side — the foundation Phase 3's page compositor consumes. Image
    # prompts still carry NO dialogue text. Now ON by default — with it off the
    # product generates loose illustrations, not a comic; turn it off to A/B or
    # roll back, image generation is unchanged when off.
    comic_shot_list_enabled: bool = True
    # Coverage verification for the shot-list stage. When on (and the shot-list
    # stage itself is on), a second cheap-tier LLM pass re-reads the full chapter
    # against the extracted beats and inserts panels for important details the
    # extractor dropped (events, reveals, key dialogue, worldbuilding) — the
    # anti-over-summarization guard. Costs one extra cheap LLM call per chapter;
    # verifier failure degrades silently to the unverified shot-list. Defaults
    # ON because it only activates inside the already-gated comic path.
    comic_coverage_check_enabled: bool = True

    # Comic Page Compositor (Phase 3). When enabled (AND comic_shot_list_enabled
    # is also on), the clean dialogue-free panels produced by image generation are
    # composited into finished COMIC PAGE PNGs: panels placed in a layout grid with
    # borders + gutters, vector speech bubbles with tails pointing at the speaker's
    # screen_side, Vietnamese lettering, and caption boxes. Composed pages replace
    # the loose panels in what the chapter exposes to the frontend (chapter.images),
    # while the loose panels are kept on disk alongside. ON by default — this is
    # what turns generated panels into an actual comic page; any failure degrades
    # gracefully to loose panels, and turning it off restores that behaviour.
    comic_compositor_enabled: bool = True
    # Page canvas geometry (spec §2.1): "<width>x<height>" in px. ISO 1:√2 by
    # default (1600×2263), suitable for both webtoon scroll and print.
    comic_page_canvas: str = "1600x2263"
    # Path to the Vietnamese-capable comic lettering font (.ttf). MUST cover the
    # full VN diacritic battery (ề ữ ạ ọ ậ ỹ). Defaults to vendored Be Vietnam Pro;
    # the compositor refuses to silently fall back to a non-VN font.
    comic_font: str = "assets/fonts/BeVietnamPro-Bold.ttf"
    # Layout selection mode: "shot_list" honours each Page.layout from the Phase 2
    # shot-list; "auto" re-derives a layout from the panel count. "shot_list" is the
    # default so authored pacing (SPLASH for big beats, etc.) is preserved.
    comic_layout_mode: str = "shot_list"

    # Library cover image. When a story is saved to the Library the frontend
    # requests ONE cover illustration (POST /api/images/library/generate-cover)
    # so the bookshelf card shows art instead of the gradient placeholder.
    # Runs through FlowKit and is therefore ALSO gated by flowkit_enabled +
    # flowkit_project_id; failures degrade silently to the placeholder.
    # Defaults ON because it is inert while FlowKit is off.
    cover_image_enabled: bool = True

    # HuggingFace Inference API (free tier)
    hf_token: str = ""
    hf_image_model: str = "black-forest-labs/FLUX.1-schnell"

    # Seedream (ByteDance) image generation
    seedream_api_key: str = ""
    seedream_api_url: str = ""

    # Flowkit (Chrome Extension + Google Labs proxy) — local-only, account-ban risk
    flowkit_enabled: bool = True
    flowkit_port: int = 7860
    flowkit_style_reference_path: str = ""
    flowkit_concurrent_workers: int = (
        1  # runtime initial value; adaptive ramp managed by FlowService
    )
    flowkit_concurrent_workers_max: int = 4  # ceiling for adaptive ramp
    flowkit_workers_ramp_threshold: int = (
        10  # consecutive successes before incrementing
    )
    flowkit_veo_poll_interval: float = 5.0
    flowkit_account_warning_shown: bool = False
    flowkit_risk_acknowledged: bool = (
        True  # hard gate; backend rejects flowkit_enabled=True without this
    )
    flowkit_image_input_type_split: bool = (
        False  # split REFERENCE → CHARACTER/STYLE (requires live enum sniff)
    )
    # Verify X-Callback-Signature (HMAC-SHA256 of body) on the HTTP
    # /api/ext/callback fallback; the live WS path relies on 127.0.0.1 trust.
    # On by default: that route is exempt from CSRF (the extension holds no
    # cookie), so the signature is the only thing authenticating it. The shipped
    # extension talks over the WebSocket and never posts here, so requiring a
    # signature costs nothing today.
    flowkit_callback_hmac_required: bool = True
    flowkit_use_refiner: bool = True  # ACTIVE: ImageGenerator._flowkit_refine runs the comic-panel refiner on every prompt before flowMedia:batchGenerateImages
    flowkit_request_timeout: float = 180.0  # seconds; sync-bridge wait when ImageGenerator dispatches to FlowService loop
    flowkit_aspect_ratio: str = (
        "4:5"  # webtoon comic panel; mapped to IMAGE_ASPECT_RATIO_* enum at send time
    )
    # Google Labs Flow project UUID. Find in URL at labs.google/fx/tools/flow/project/<UUID>.
    # Required when flowkit_enabled=True — request_image raises if empty.
    flowkit_project_id: str = ""

    # Self-review (CoT quality check)
    enable_self_review: bool = True  # CoT self-review for quality
    self_review_threshold: float = 3.0  # Score threshold (1.0-5.0)

    # RAG world-building
    rag_enabled: bool = False
    rag_persist_dir: str = "data/rag"
    # RAG — semantic retrieval over generated chapters (Sprint 2 Task 1).
    # Gated behind rag_enabled master switch; no effect when rag_enabled=False.
    rag_index_chapters: bool = True  # auto-index each chapter after write
    rag_multi_query: bool = True  # fan-out per char + per thread + summary
    rag_per_char_queries: int = 3  # top-N focus characters to query
    rag_per_thread_queries: int = 3  # top-N open threads to query
    rag_n_results_per_query: int = 2  # hits per sub-query
    rag_merge_cap: int = 8  # max merged chunks injected into prompt
    rag_max_tokens: int = 1000  # soft cap for RAG block in prompt

    # Character-consistent images
    enable_character_consistency: bool = False
    replicate_api_key: str = ""
    character_consistency_provider: str = "seedream"  # seedream | replicate

    # Long-context mode (e.g. Gemini 1.5 Pro, Claude 3, GPT-4o-128k)
    use_long_context: bool = False
    long_context_provider: str = ""
    long_context_model: str = ""
    long_context_api_key: str = ""
    long_context_base_url: str = ""
    long_context_max_tokens: int = 1000000

    # Prompt injection defense mode: False = log-only, True = block and raise error
    block_on_injection: bool = False

    # Multi-agent debate
    enable_agent_debate: bool = True
    max_debate_rounds: int = 3
    # "full" = every active agent debates; "lite" = editor/drama/continuity only,
    # and round 3 is skipped. agent_registry reads this on every layer-2 review
    # cycle; without the field the read raised AttributeError and the whole
    # craft-critique lane was discarded.
    debate_mode: str = "full"

    # Smart chapter revision (auto-fix weak chapters using agent reviews)
    enable_smart_revision: bool = True
    smart_revision_threshold: float = 3.5  # 1.0-5.0 scale

    # Parallel chapter generation (batch mode)
    parallel_chapters_enabled: bool = (
        True  # Feature flag — parallel chapter generation enabled
    )
    chapter_batch_size: int = 5  # Chapters per batch
    parallel_use_asyncio: bool = (
        True  # Use asyncio.gather() instead of ThreadPoolExecutor
    )
    # When True, chapters within a batch run sequentially so each chapter's
    # continuity anchor = its immediate predecessor's tail (not just the prior
    # batch's last chapter). Costs ~chapter_batch_size× throughput within L1.
    l1_strict_chapter_continuity: bool = False
    chapter_retry_max: int = 2  # Max retries for failed contract validation
    chapter_retry_threshold: float = (
        0.6  # Contract compliance score below this triggers retry
    )
    parallel_causal_sync: bool = (
        True  # Sync causal events between parallel chapters post-write
    )

    # Sprint 2 P5: semantic outline metrics thresholds
    enable_llm_outline_critic: bool = (
        True  # Secondary LLM signal alongside deterministic metrics
    )
    outline_metric_floor: float = (
        0.40  # composite_score floor; below this → log WARN + optional revise
    )

    # Layer 1 enhancements (all opt-in, non-fatal)
    enable_theme_premise: bool = True  # Generate thematic anchor before story
    enable_voice_profiles: bool = True  # Generate character voice profiles
    enable_outline_critique: bool = True  # Critique-revise loop on outlines
    outline_critique_max_rounds: int = 1  # Max critique-revise iterations
    enable_scene_decomposition: bool = True  # Break chapters into scenes before writing
    enable_show_dont_tell: bool = True  # Inject show-don't-tell guidance into prompts
    enable_chapter_critique: bool = (
        True  # Post-write selective self-critique (climax, arc boundaries, first/last)
    )
    # L1-B: Critique frequency + rollback-on-regression
    chapter_critique_every_n_chapters: int = (
        5  # Force critique every N chapters (0 disables this trigger)
    )
    chapter_critique_rollback: bool = (
        True  # Re-score after rewrite; revert if aggregate drops
    )
    chapter_critique_rollback_threshold: float = (
        0.3  # Revert if avg_after < avg_before - threshold
    )
    # L1-F: Pacing as hard contract constraint (was advisory)
    enable_pacing_enforcement: bool = (
        True  # Post-write pacing classification + rewrite on mismatch
    )
    pacing_enforcement_confidence: float = (
        0.7  # Min classifier confidence before triggering rewrite
    )
    pacing_mismatch_rewrite: bool = (
        True  # If confidence ≥ threshold AND mismatch, trigger rewrite
    )

    # Phase 1 quality improvements
    enable_arc_waypoints: bool = True  # Structured character arc tracking per chapter
    enable_outline_arc_validation: bool = (
        True  # Validate outline-to-macro_arc coherence
    )

    # Phase 2 chapter contracts
    enable_chapter_contracts: bool = True  # Per-chapter requirement contracts
    enable_contract_validation: bool = True  # Post-write contract compliance check

    # Phase 3 narrative linking
    enable_semantic_foreshadowing: bool = (
        True  # LLM-based foreshadowing verification (replaces keyword)
    )
    semantic_foreshadowing_threshold: float = (
        0.7  # Confidence threshold for seed/payoff verification
    )

    # Phase 4 context management
    enable_tiered_context: bool = True  # Tiered summary system for long stories
    tiered_context_max_tokens: int = 3000  # Token budget for tiered context
    bible_max_world_rules: int = 10  # was hardcoded 5
    bible_max_active_threads: int = 30  # was hardcoded 20
    bible_max_character_states: int = 15  # was hardcoded 8
    bible_max_milestones: int = 50  # was hardcoded 30
    bible_max_relationships_per_char: int = 8  # was hardcoded 5
    tiered_max_promotions: int = 5  # max chapters promoted from low tier to high tier

    # Phase 6: Arc execution validation
    enable_arc_execution_validation: bool = (
        True  # Validate arc waypoints in chapter content
    )
    arc_validation_use_llm: bool = True  # Use LLM for critical/ambiguous cases

    # Phase 6: Foreshadowing payoff enforcement
    enable_foreshadowing_enforcement: bool = (
        True  # Enforce payoff of planted foreshadowing
    )
    foreshadowing_grace_chapters: int = (
        2  # Chapters past deadline before flagging as overdue
    )
    enable_foreshadowing_payoff_verify: bool = (
        True  # Post-write semantic verification + targeted rewrite if payoff missing
    )
    foreshadowing_payoff_rewrite_on_miss: bool = (
        True  # Trigger targeted rewrite when due payoff not detected
    )

    # L1-D: Consistency block-and-rewrite (was warn-only)
    enable_consistency_rewrite: bool = (
        True  # Rewrite chapter when consistency violations exceed thresholds
    )
    consistency_name_warning_threshold: int = 3  # Rewrite if >= N name warnings
    consistency_location_warning_threshold: int = (
        2  # Rewrite if >= N location transition warnings
    )
    consistency_arc_drift_threshold: int = 2  # Rewrite if >= N arc drift warnings

    # Length gate: expand a chapter that came back materially under word_count.
    # Nothing used to compare the produced chapter against the requested length —
    # `count_words()` only recorded it — so a 2000-word target routinely shipped
    # at 900-1500 words. See pipeline/layer1_story/chapter_length_gate.py.
    enable_length_gate: bool = True
    length_gate_min_ratio: float = 0.85  # Expand below this fraction of target

    # Streaming stall detection. `first_chunk` covers time-to-first-token, which
    # a reasoning model spends thinking before it emits anything: measured
    # median 51.6s and max 106.3s for qwen3.8-max-thinking through the local
    # bridge, so the previous hard-coded 60s discarded a large share of calls
    # mid-thought and retried them from scratch — burning the wait twice and
    # silently demoting the request to the next model in the chain.
    # `chunk` stays short: once tokens are flowing, a long gap is a real stall.
    # Raised alongside llm.request_timeout: at 180s this killed the very case
    # the 900s request timeout exists for — a reasoning model whose time to
    # first token exceeds three minutes.
    stream_first_chunk_timeout: int = 300
    stream_chunk_timeout: int = 30

    # Phase 5: L1 consistency improvements
    enable_emotional_memory: bool = (
        True  # Per-character emotion tracking across chapters
    )
    enable_proactive_constraints: bool = (
        True  # forbidden_actions, must_maintain in contracts
    )
    enable_thread_enforcement: bool = (
        True  # Hard requirement for stale threads (gap >= 8)
    )
    enable_emotional_bridge: bool = True  # Inter-chapter emotional continuity
    enable_scene_beat_writing: bool = (
        True  # Per-beat chapter writing (extends enable_scene_decomposition)
    )
    enable_l1_causal_graph: bool = True  # Causal event tracking and validation

    # New L1 validators (Feature #12-16)
    enable_dialogue_voice_check: bool = True  # Bug #6: Voice profile enforcement
    enable_pov_drift_check: bool = True  # Feature #12: POV consistency within chapters
    enable_timeline_validation: bool = True  # Feature #13: Temporal consistency
    enable_secret_tracking: bool = True  # Feature #14: Character secret reveal tracking
    enable_thematic_resonance: bool = True  # Feature #15: Theme presence tracking
    enable_dialogue_attribution_check: bool = (
        True  # Feature #16: Clear dialogue attribution
    )

    # L2 enhancement quality signals
    l2_use_l1_signals: bool = (
        True  # wire L1 waypoints/summary/pacing/thread.status into L2
    )
    l2_causal_audit: bool = True  # post-L2 causality verification (Phase B)
    l2_thread_pressure: bool = True  # thread.urgency → psychology pressure (Phase C)
    l2_contract_gate: bool = (
        True  # post-L2 contract validation + optional rewrite (Phase E)
    )

    # Sprint 1 Task 3 — Simulator → Enhancer drama contract enforcement
    enable_simulator_contracts: bool = True
    enable_contract_retry: bool = True
    contract_retry_max: int = 1
    contract_drama_tolerance: float = 0.15
    contract_cheap_validation: bool = True

    # Sprint 2 Task 2 — Voice contract + L1↔L2 dedup
    enable_voice_contract: bool = (
        True  # Build per-chapter voice contracts from L1 profiles
    )
    enable_voice_contract_retry: bool = (
        True  # Refine-with-hint on drift (vs. binary revert)
    )
    voice_contract_retry_max: int = 1
    voice_min_compliance: float = 0.75  # Pass threshold per chapter
    voice_binary_revert_floor: float = 0.5  # Below this compliance → last-resort revert

    # L2 Consistency Engine (master switch + thread watchdog sub-gate)
    l2_consistency_engine: bool = True  # Enable A-E consistency improvements
    l2_consistency_threads: bool = True  # Thread watchdog for plot resolution

    # Phase 6: Voice preservation (reverts drifted dialogues)
    l2_voice_preservation: bool = True  # Enforce voice preservation post-enhancement
    l2_knowledge_constraints: bool = (
        True  # L2-B: inject character knowledge facts to prevent hallucination
    )
    l2_voice_drift_threshold: float = 0.4  # Drift level for warning
    l2_voice_revert_threshold: float = 0.3  # Drift level for automatic revert
    voice_revert_use_anchored: bool = (
        True  # Use speaker-anchored revert (Sprint 3 P3); False → legacy positional
    )

    # Phase 6: Drama ceiling (prevents melodrama)
    l2_drama_ceiling: bool = True  # Apply genre-specific drama ceilings
    l2_melodrama_detection: bool = True  # Detect and flag melodramatic writing

    # Phase 7: L2 scene enhancement improvements
    l2_parallel_scenes: bool = True  # Parallel scene enhancement within chapter
    l2_scene_retry_max: int = 2  # Max retries for weak scenes after enhancement
    l2_scene_retry_threshold: float = 0.5  # Drama threshold for scene retry
    l2_chapter_retry_max: int = 2  # Max retries for failed chapter enhancement (P-F)
    l2_chapter_retry_backoff: float = (
        1.5  # Exponential backoff multiplier for chapter retry
    )
    l2_drama_curve_balancing: bool = True  # Cross-chapter drama curve optimization
    l2_drama_curve_target: str = "rising"  # rising | climax_at_end | wave

    # Adaptive simulation rounds (Phase 4 - dynamic round calculation)
    adaptive_simulation_rounds: bool = (
        True  # Dynamic round calculation based on complexity
    )
    l2_drama_threshold: float = 0.5  # Below = weak round, trigger escalation
    l2_drama_target: float = 0.65  # Stop when avg drama reaches this
    l2_min_rounds: int = 3  # Minimum simulation rounds
    l2_max_rounds: int = 10  # Maximum simulation rounds (hard cap)
    l2_stall_threshold: int = 3  # Rounds with no improvement before force-stop
    # Route the simulator's low-stakes calls to the cheap model. The whole
    # simulator ran on the premium tier — about 100 calls a run — including two
    # whose output barely reaches the reader: drama evaluation, consumed as a
    # single score, and reaction posts, which only ever appear truncated in the
    # recent-posts filler. Agent turns and escalation events stay on the primary
    # model: those are the dramatic content itself. Set False to put everything
    # back on the primary model.
    l2_cheap_low_stakes_calls: bool = True
    # Route the 8-agent craft panel to the cheap model too. Off by default:
    # unlike the simulator's filler, the panel's critique is what
    # SmartRevisionService rewrites from, so its judgement quality reaches the
    # reader. Its responses are capped by l2_agent_review_max_tokens either way.
    l2_cheap_agent_panel: bool = False
    # Panel replies are a small {score, issues[], suggestions[]} object; without
    # a cap they were billed against the model's full output budget.
    l2_agent_review_max_tokens: int = 1200

    # Batch generation config
    batch_max_workers: int = 3  # Max parallel workers for batch chapter generation
    chapter_max_tokens: int = 8192  # Max tokens for chapter writing
    min_beat_words: int = 200  # Minimum words per beat in beat writing
    continuity_anchor_chars: int = 200  # Chars from previous chapter for continuity
    summarize_excerpt_chars: int = 3000  # Chars to use for chapter summary
    excerpt_max_chars: int = 4000  # Max chars for chapter excerpts
    tiered_chapter_cap: int = 2000  # Max chars per chapter in tiered context

    # Thread tracking
    thread_stale_threshold: int = 3  # Chapters without mention before thread is stale

    # Genre-specific drama ceilings (overrides defaults in drama_patterns.py)
    genre_drama_ceiling_override: dict = field(default_factory=dict)  # genre -> ceiling

    # L2→L1 structural rewrite (Phase 5)
    enable_structural_rewrite: bool = True  # L2 can trigger L1 chapter rewrites
    structural_rewrite_threshold: float = 0.7  # Severity threshold for rewrite
    max_structural_rewrites: int = 1  # Per chapter limit

    # Quality gate (inline scoring between layers)
    # Recommended thresholds by genre: romance/comedy=2.3, mystery/thriller=2.5,
    # fantasy/sci-fi=2.5, literary/historical=2.8, action=2.2
    enable_quality_gate: bool = True
    quality_gate_threshold: float = 2.5  # 1.0-5.0 scale, P50 across genres
    quality_gate_chapter_threshold: float = 2.0  # Per-chapter floor
    quality_gate_max_retries: int = 1

    # Sprint 3 Task 1: Unified knowledge graph (merges conflict_web + threads + foreshadowing + arcs)
    enable_unified_kg: bool = (
        False  # Opt-in — replaces legacy build_from_story_draft when True
    )

    # Sprint 3 Task 2: Per-chapter checkpoint (resume from last completed chapter)
    enable_chapter_checkpoint: bool = (
        False  # Opt-in — writes per_chapter/{slug}_ch{N}_layer{L}.json
    )
    chapter_checkpoint_keep_last: int = (
        5  # Auto-prune older per-chapter files beyond this count
    )
    chapter_checkpoint_every_n_batches: int = 1  # Checkpoint cadence (1 = every batch)

    # Sprint 3 Task 3: Cross-chapter ArcMilestone contract
    enable_arc_milestones: bool = False  # Opt-in — generates + tracks arc-level beats

    # L3 Sensory Polish (P-A) — optional post-L2 prose enhancement
    enable_sensory_polish: bool = (
        True  # On by default — adds sensory details to prose (L3)
    )
    sensory_polish_model: str = ""  # Empty = use primary model

    # Reader Simulator (P-B) — simulates reader experience for quality feedback
    enable_reader_simulation: bool = False  # Opt-in — runs after L2 enhancement
    reader_engagement_threshold: float = 0.5  # Flag chapters below this score

    # Incremental L2 Publish (P-C) — stream chapters as they're enhanced
    enable_incremental_publish: bool = False  # Opt-in — emits chapter_enhanced events

    # Forge-from-Sentence (Phase 1) — fast synchronous BFF over cheap_model.
    enable_sentence_forge: bool = True
    forge_cheap_model_override: str = ""  # empty = use LLMConfig.cheap_model

    # Character Traits (Phase 2) — 4-axis (strength/wisdom/agility/scheme) generation endpoint.
    enable_character_traits: bool = False
    character_traits_cheap_model_override: str = ""  # empty = use LLMConfig.cheap_model

    # Simulation Transcript (Phase 3) — structured TranscriptTurn[] + /api/simulation/* endpoints.
    enable_simulation_transcript: bool = True
    enable_drama_climax: bool = False  # extends drama_level to {low,medium,high,climax}
    simulation_continue_cheap_model_override: str = (
        ""  # empty = use LLMConfig.cheap_model
    )

    # Reader + Branching + Pipeline overlay (Phase 4) — cinematic reader chrome,
    # per-chapter illustration trigger, SSE-driven overlay during branch generation.
    enable_pipeline_overlay: bool = True
    enable_chapter_illustration: bool = True

    # RFC voice-handling-consolidation Phase A: nested view of voice flags.
    # Defaults match flat voice_* / l2_voice_* fields. Synced in __post_init__.
    voice: VoiceConfig = field(default_factory=VoiceConfig)

    def __post_init__(self):
        """Phase A sync: copy flat voice_* / l2_voice_* fields into self.voice
        when the nested shape is at defaults, so consumers reading either
        shape see identical values. Flat fields stay authoritative.
        """
        if self.voice == VoiceConfig():
            self.voice = VoiceConfig(
                enabled=self.l2_voice_preservation,
                min_compliance=self.voice_min_compliance,
                drift_warn_threshold=self.l2_voice_drift_threshold,
                drift_revert_threshold=self.l2_voice_revert_threshold,
                binary_revert_floor=self.voice_binary_revert_floor,
                contract_enabled=self.enable_voice_contract,
                contract_retry_enabled=self.enable_voice_contract_retry,
                contract_retry_max=self.voice_contract_retry_max,
            )


# Presets live in config/presets.py — imported here for convenience.
from .presets import PIPELINE_PRESETS, PROVIDER_PRESETS  # noqa: E402

__all__ = [
    "LLMConfig",
    "PipelineConfig",
    "PIPELINE_PRESETS",
    "PROVIDER_PRESETS",
]
