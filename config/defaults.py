"""Default values, dataclass configs, and preset constants for StoryForge."""

from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    """Cấu hình kết nối LLM API."""
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
    # Per-layer model routing (optional, falls back to primary model)
    layer1_model: str = ""  # Story generation
    layer2_model: str = ""  # Drama analysis


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
    enable_self_review: bool = False  # Opt-in CoT self-review
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

    # Multi-agent debate prototype
    enable_agent_debate: bool = False
    max_debate_rounds: int = 3

    # Smart chapter revision (auto-fix weak chapters using agent reviews)
    enable_smart_revision: bool = False
    smart_revision_threshold: float = 3.5  # 1.0-5.0 scale

    # Parallel chapter generation (batch mode)
    parallel_chapters_enabled: bool = False  # Feature flag — sequential fallback when False
    chapter_batch_size: int = 5  # Chapters per batch

    # Layer 1 enhancements (all opt-in, non-fatal)
    enable_theme_premise: bool = True  # Generate thematic anchor before story
    enable_voice_profiles: bool = True  # Generate character voice profiles
    enable_outline_critique: bool = True  # Critique-revise loop on outlines
    outline_critique_max_rounds: int = 1  # Max critique-revise iterations
    enable_scene_decomposition: bool = True  # Break chapters into scenes before writing
    enable_show_dont_tell: bool = True  # Inject show-don't-tell guidance into prompts
    enable_chapter_critique: bool = False  # Post-write chapter self-critique (costs extra LLM calls)

    # Phase 1 quality improvements
    enable_arc_waypoints: bool = True  # Structured character arc tracking per chapter
    enable_outline_arc_validation: bool = True  # Validate outline-to-macro_arc coherence

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
