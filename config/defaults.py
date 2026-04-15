"""Default values, dataclass configs, and preset constants for StoryForge."""

from dataclasses import dataclass, field


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
    fallback_max_latency_ms: int = 5000   # Switch model if avg latency exceeds this
    fallback_max_cost_per_1k: float = 0.01  # Skip fallback models above this cost/1k tokens
    # Chain-level retry when all providers fail (rate-limit storms, outages)
    chain_retry_max: int = 2  # Max times to retry entire fallback chain
    chain_retry_base_delay: float = 30.0  # Initial delay (seconds) before chain retry
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
    image_prompt_style: str = "cinematic"
    share_base_url: str = ""
    pdf_font: str = "NotoSansVN"

    # Image generation provider
    image_provider: str = "none"  # none / dalle / sd-api / seedream / huggingface
    image_api_key: str = ""
    image_api_url: str = ""

    # HuggingFace Inference API (free tier)
    hf_token: str = ""
    hf_image_model: str = "black-forest-labs/FLUX.1-schnell"

    # Seedream (ByteDance) image generation
    seedream_api_key: str = ""
    seedream_api_url: str = ""

    # Self-review (CoT quality check)
    enable_self_review: bool = True  # CoT self-review for quality
    self_review_threshold: float = 3.0  # Score threshold (1.0-5.0)

    # RAG world-building
    rag_enabled: bool = False
    rag_persist_dir: str = "data/rag"

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

    # Smart chapter revision (auto-fix weak chapters using agent reviews)
    enable_smart_revision: bool = True
    smart_revision_threshold: float = 3.5  # 1.0-5.0 scale

    # Parallel chapter generation (batch mode)
    parallel_chapters_enabled: bool = True  # Feature flag — parallel chapter generation enabled
    chapter_batch_size: int = 5  # Chapters per batch
    parallel_use_asyncio: bool = True  # Use asyncio.gather() instead of ThreadPoolExecutor
    chapter_retry_max: int = 2  # Max retries for failed contract validation
    chapter_retry_threshold: float = 0.6  # Contract compliance score below this triggers retry
    parallel_causal_sync: bool = True  # Sync causal events between parallel chapters post-write

    # Layer 1 enhancements (all opt-in, non-fatal)
    enable_theme_premise: bool = True  # Generate thematic anchor before story
    enable_voice_profiles: bool = True  # Generate character voice profiles
    enable_outline_critique: bool = True  # Critique-revise loop on outlines
    outline_critique_max_rounds: int = 1  # Max critique-revise iterations
    enable_scene_decomposition: bool = True  # Break chapters into scenes before writing
    enable_show_dont_tell: bool = True  # Inject show-don't-tell guidance into prompts
    enable_chapter_critique: bool = True  # Post-write selective self-critique (climax, arc boundaries, first/last)

    # Phase 1 quality improvements
    enable_arc_waypoints: bool = True  # Structured character arc tracking per chapter
    enable_outline_arc_validation: bool = True  # Validate outline-to-macro_arc coherence

    # Phase 2 chapter contracts
    enable_chapter_contracts: bool = True  # Per-chapter requirement contracts
    enable_contract_validation: bool = True  # Post-write contract compliance check

    # Phase 3 narrative linking
    enable_semantic_foreshadowing: bool = True  # LLM-based foreshadowing verification (replaces keyword)
    semantic_foreshadowing_threshold: float = 0.7  # Confidence threshold for seed/payoff verification

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
    enable_arc_execution_validation: bool = True  # Validate arc waypoints in chapter content
    arc_validation_use_llm: bool = True  # Use LLM for critical/ambiguous cases

    # Phase 6: Foreshadowing payoff enforcement
    enable_foreshadowing_enforcement: bool = True  # Enforce payoff of planted foreshadowing
    foreshadowing_grace_chapters: int = 2  # Chapters past deadline before flagging as overdue

    # Phase 5: L1 consistency improvements
    enable_emotional_memory: bool = True  # Per-character emotion tracking across chapters
    enable_proactive_constraints: bool = True  # forbidden_actions, must_maintain in contracts
    enable_thread_enforcement: bool = True  # Hard requirement for stale threads (gap >= 8)
    enable_emotional_bridge: bool = True  # Inter-chapter emotional continuity
    enable_scene_beat_writing: bool = True  # Per-beat chapter writing (extends enable_scene_decomposition)
    enable_l1_causal_graph: bool = True  # Causal event tracking and validation

    # L2 enhancement quality signals
    l2_use_l1_signals: bool = True  # wire L1 waypoints/summary/pacing/thread.status into L2
    l2_causal_audit: bool = True  # post-L2 causality verification (Phase B)
    l2_thread_pressure: bool = True  # thread.urgency → psychology pressure (Phase C)
    l2_contract_gate: bool = True  # post-L2 contract validation + optional rewrite (Phase E)

    # L2 Consistency Engine (character state, setting, threads, voice)
    l2_consistency_engine: bool = True  # Enable A-E consistency improvements
    l2_consistency_character_state: bool = True  # Track character location/physical/emotional state
    l2_consistency_setting: bool = True  # Track locations, objects, timeline
    l2_consistency_threads: bool = True  # Thread watchdog for plot resolution
    l2_consistency_voice: bool = True  # Voice fingerprint for dialogue consistency

    # Phase 6: Voice preservation (reverts drifted dialogues)
    l2_voice_preservation: bool = True  # Enforce voice preservation post-enhancement
    l2_voice_drift_threshold: float = 0.4  # Drift level for warning
    l2_voice_revert_threshold: float = 0.3  # Drift level for automatic revert

    # Phase 6: Drama ceiling (prevents melodrama)
    l2_drama_ceiling: bool = True  # Apply genre-specific drama ceilings
    l2_melodrama_detection: bool = True  # Detect and flag melodramatic writing

    # Phase 7: L2 scene enhancement improvements
    l2_parallel_scenes: bool = True  # Parallel scene enhancement within chapter
    l2_scene_retry_max: int = 2  # Max retries for weak scenes after enhancement
    l2_scene_retry_threshold: float = 0.5  # Drama threshold for scene retry
    l2_drama_curve_balancing: bool = True  # Cross-chapter drama curve optimization
    l2_drama_curve_target: str = "rising"  # rising | climax_at_end | wave

    # Adaptive simulation rounds (Phase 4 - dynamic round calculation)
    adaptive_simulation_rounds: bool = True  # Dynamic round calculation based on complexity
    l2_drama_threshold: float = 0.5  # Below = weak round, trigger escalation
    l2_drama_target: float = 0.65  # Stop when avg drama reaches this
    l2_min_rounds: int = 3  # Minimum simulation rounds
    l2_max_rounds: int = 10  # Maximum simulation rounds (hard cap)
    l2_stall_threshold: int = 3  # Rounds with no improvement before force-stop

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


# Presets live in config/presets.py — imported here for convenience.
from .presets import PIPELINE_PRESETS, MODEL_PRESETS  # noqa: E402

__all__ = [
    "LLMConfig",
    "PipelineConfig",
    "PIPELINE_PRESETS",
    "MODEL_PRESETS",
]
