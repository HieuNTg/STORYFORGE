"""Quản lý cấu hình cho StoryForge."""

import os
import json
import threading
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    """Cấu hình kết nối LLM API."""
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.8
    max_tokens: int = 4096
    # Backend: "api" (OpenAI-compatible) hoặc "web" (browser auth, free)
    backend_type: str = "api"
    web_auth_provider: str = "deepseek-web"  # Provider cho web auth
    # Model routing: cheap model for summaries/analysis
    cheap_model: str = ""  # empty = use primary model
    cheap_base_url: str = ""  # empty = use primary base_url
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
    layer3_model: str = ""  # Video/storyboard


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

    # Layer 3 - Video
    shots_per_chapter: int = 8
    video_style: str = "Phim ngắn drama"

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
    image_provider: str = "none"  # none / dalle / sd-api / seedream
    image_api_key: str = ""
    image_api_url: str = ""

    # Seedream (ByteDance) image generation
    seedream_api_key: str = ""
    seedream_api_url: str = ""

    # Video quality
    video_quality: str = "draft"  # "draft" or "final"

    # Self-review (CoT quality check)
    enable_self_review: bool = False  # Opt-in CoT self-review
    self_review_threshold: float = 3.0  # Score threshold (1.0-5.0); genre override via get_review_threshold()
    # Genre-aware thresholds (keyed by genre display name, lowercase)
    # action/thriller = 2.8 (fast-paced — prose precision matters less than plot momentum)
    # literary/historical = 3.5 (prose quality paramount)
    # romance = 3.0 (default baseline)
    self_review_genre_thresholds: dict = field(default_factory=lambda: {
        "action": 2.8,
        "thriller": 2.8,
        "kiếm hiệp": 2.8,
        "literary": 3.5,
        "historical": 3.5,
        "romance": 3.0,
        "ngôn tình": 3.0,
    })

    # TTS provider
    tts_provider: str = "edge-tts"  # edge-tts / kling / none
    kling_tts_api_key: str = ""
    kling_tts_api_url: str = ""

    # RAG world-building
    rag_enabled: bool = False
    rag_persist_dir: str = "data/rag"

    # ChromaDB persistent storage (used by RAGKnowledgeBase)
    # CHROMA_PERSIST_DIR env var takes precedence; these fields are the config-file fallback.
    chroma_persist_dir: str = "data/chromadb"
    chroma_collection_name: str = "storyforge_world"

    # XTTS v2 voice cloning
    xtts_api_url: str = ""  # http://localhost:8020 or Replicate URL
    xtts_reference_audio: str = ""  # default reference audio path
    character_voice_map: dict = field(default_factory=dict)  # {"CharName": "data/voices/char.wav"}

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

    # Voice emotion synthesis
    enable_voice_emotion: bool = False

    # Prompt injection defense mode: False = log-only, True = block and raise error
    block_on_injection: bool = False

    # Multi-agent debate prototype
    enable_agent_debate: bool = False
    max_debate_rounds: int = 3
    # Debate mode: "full" = all agents, 3 rounds; "lite" = 3 key agents, 1 round (~85% cheaper)
    debate_mode: str = "full"  # "full" | "lite"

    # Smart chapter revision (auto-fix weak chapters using agent reviews)
    enable_smart_revision: bool = False
    smart_revision_threshold: float = 3.5  # 1.0-5.0 scale

    # Quality gate (inline scoring between layers)
    # Recommended thresholds by genre: romance/comedy=2.3, mystery/thriller=2.5,
    # fantasy/sci-fi=2.5, literary/historical=2.8, action=2.2
    enable_quality_gate: bool = True
    quality_gate_threshold: float = 2.5  # 1.0-5.0 scale, P50 across genres
    quality_gate_chapter_threshold: float = 2.0  # Per-chapter floor
    quality_gate_max_retries: int = 1


VIDEO_QUALITY_PRESETS = {
    "draft": {"resolution": "512x512", "fps": 24, "crf": "28", "preset": "fast"},
    "final": {"resolution": "1024x1024", "fps": 30, "crf": "23", "preset": "medium"},
}

PIPELINE_PRESETS = {
    "beginner": {
        "label": "Người mới — Cơ bản, dễ dùng",
        "enable_self_review": False,
        "enable_agent_debate": False,
        "enable_smart_revision": False,
        "use_long_context": False,
        "enable_voice_emotion": False,
        "enable_character_consistency": False,
        "rag_enabled": False,
        "context_window_chapters": 2,
        "num_simulation_rounds": 3,
        "drama_intensity": "trung bình",
    },
    "advanced": {
        "label": "Nâng cao — Chất lượng cao hơn",
        "enable_self_review": True,
        "self_review_threshold": 3.0,
        "enable_agent_debate": True,
        "max_debate_rounds": 3,
        "debate_mode": "lite",
        "enable_smart_revision": True,
        "smart_revision_threshold": 3.5,
        "enable_quality_gate": True,
        "quality_gate_threshold": 2.5,
        "quality_gate_max_retries": 1,
        "use_long_context": False,
        "enable_voice_emotion": False,
        "enable_character_consistency": False,
        "rag_enabled": False,
        "context_window_chapters": 5,
        "num_simulation_rounds": 5,
        "drama_intensity": "cao",
    },
    "pro": {
        "label": "Chuyên nghiệp — Tất cả tính năng",
        "enable_self_review": True,
        "self_review_threshold": 2.5,
        "enable_agent_debate": True,
        "max_debate_rounds": 3,
        "debate_mode": "full",
        "enable_smart_revision": True,
        "smart_revision_threshold": 3.0,
        "enable_quality_gate": True,
        "quality_gate_threshold": 2.5,
        "quality_gate_max_retries": 1,
        "use_long_context": True,
        "enable_voice_emotion": True,
        "enable_character_consistency": True,
        "rag_enabled": True,
        "context_window_chapters": 5,
        "num_simulation_rounds": 5,
        "drama_intensity": "cao",
    },
}


_OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# Vietnamese-capable models prioritized — models that produce poor Vietnamese
# (e.g. coder models, tiny models, English-only fine-tunes) cause language
# drift where summaries/context turn English and later chapters follow suit.
MODEL_PRESETS = {
    "openrouter-free-basic": {
        "label": "OpenRouter Free — Basic (Qwen 3.6 Plus)",
        "base_url": _OPENROUTER_BASE,
        "model": "qwen/qwen3.6-plus-preview:free",
        "cheap_model": "nvidia/nemotron-3-nano-30b-a3b:free",
        "cheap_base_url": _OPENROUTER_BASE,
        "layer1_model": "",
        "layer2_model": "",
        "layer3_model": "",
        "fallback_models": [
            {"model": "nvidia/nemotron-3-super-120b-a12b:free", "base_url": _OPENROUTER_BASE},
        ],
    },
    "openrouter-free-optimized": {
        "label": "OpenRouter Free — Optimized (per-layer routing)",
        "base_url": _OPENROUTER_BASE,
        "model": "qwen/qwen3.6-plus-preview:free",
        "cheap_model": "nvidia/nemotron-3-nano-30b-a3b:free",
        "cheap_base_url": _OPENROUTER_BASE,
        "layer1_model": "qwen/qwen3.6-plus-preview:free",
        "layer2_model": "nvidia/nemotron-3-super-120b-a12b:free",
        "layer3_model": "stepfun/step-3.5-flash:free",
        "fallback_models": [
            {"model": "nvidia/nemotron-3-super-120b-a12b:free", "base_url": _OPENROUTER_BASE},
            {"model": "stepfun/step-3.5-flash:free", "base_url": _OPENROUTER_BASE},
        ],
    },
    "openrouter-free-max": {
        "label": "OpenRouter Free — Max Context (1M tokens)",
        "base_url": _OPENROUTER_BASE,
        "model": "qwen/qwen3.6-plus-preview:free",
        "cheap_model": "nvidia/nemotron-3-nano-30b-a3b:free",
        "cheap_base_url": _OPENROUTER_BASE,
        "layer1_model": "qwen/qwen3.6-plus-preview:free",
        "layer2_model": "nvidia/nemotron-3-super-120b-a12b:free",
        "layer3_model": "stepfun/step-3.5-flash:free",
        "fallback_models": [
            {"model": "minimax/minimax-m2.5:free", "base_url": _OPENROUTER_BASE},
            {"model": "stepfun/step-3.5-flash:free", "base_url": _OPENROUTER_BASE},
        ],
    },
}


class ConfigManager:
    """Singleton quản lý cấu hình (thread-safe)."""

    _instance = None
    _lock = threading.Lock()
    CONFIG_FILE = "data/config.json"

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.llm = LLMConfig()
        self.pipeline = PipelineConfig()
        self._load()

    def _load(self):
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                # Decrypt sensitive fields transparently.
                # Migration: if plaintext keys exist they pass through unchanged;
                # on next save() they will be encrypted automatically.
                from services.secret_manager import decrypt_sensitive_fields
                data = decrypt_sensitive_fields(raw)
                for k, v in data.get("llm", {}).items():
                    if hasattr(self.llm, k):
                        setattr(self.llm, k, v)
                for k, v in data.get("pipeline", {}).items():
                    if hasattr(self.pipeline, k):
                        setattr(self.pipeline, k, v)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Config load error: {e}")

        # Environment variable overrides (for Docker/production)
        env_map = {
            "STORYFORGE_API_KEY": ("llm", "api_key"),
            "STORYFORGE_BASE_URL": ("llm", "base_url"),
            "STORYFORGE_MODEL": ("llm", "model"),
            "STORYFORGE_BACKEND": ("llm", "backend_type"),
            "STORYFORGE_TEMPERATURE": ("llm", "temperature"),
            "STORYFORGE_IMAGE_PROVIDER": ("pipeline", "image_provider"),
            "IMAGE_API_KEY": ("pipeline", "image_api_key"),
            "IMAGE_API_URL": ("pipeline", "image_api_url"),
            "SEEDREAM_API_KEY": ("pipeline", "seedream_api_key"),
            "SEEDREAM_API_URL": ("pipeline", "seedream_api_url"),
            "STORYFORGE_TTS_PROVIDER": ("pipeline", "tts_provider"),
            "KLING_TTS_API_KEY": ("pipeline", "kling_tts_api_key"),
            "KLING_TTS_API_URL": ("pipeline", "kling_tts_api_url"),
            "STORYFORGE_RAG_ENABLED": ("pipeline", "rag_enabled"),
            "STORYFORGE_RAG_DIR": ("pipeline", "rag_persist_dir"),
            "CHROMA_PERSIST_DIR": ("pipeline", "chroma_persist_dir"),
            "CHROMA_COLLECTION_NAME": ("pipeline", "chroma_collection_name"),
            "XTTS_API_URL": ("pipeline", "xtts_api_url"),
            "XTTS_REFERENCE_AUDIO": ("pipeline", "xtts_reference_audio"),
            "REPLICATE_API_KEY": ("pipeline", "replicate_api_key"),
            "STORYFORGE_CHAR_CONSISTENCY": ("pipeline", "enable_character_consistency"),
            "STORYFORGE_LONG_CONTEXT": ("pipeline", "use_long_context"),
            "LONG_CONTEXT_PROVIDER": ("pipeline", "long_context_provider"),
            "LONG_CONTEXT_MODEL": ("pipeline", "long_context_model"),
            "LONG_CONTEXT_API_KEY": ("pipeline", "long_context_api_key"),
            "LONG_CONTEXT_BASE_URL": ("pipeline", "long_context_base_url"),
            "STORYFORGE_AGENT_DEBATE": ("pipeline", "enable_agent_debate"),
            "STORYFORGE_SMART_REVISION": ("pipeline", "enable_smart_revision"),
            "STORYFORGE_QUALITY_GATE": ("pipeline", "enable_quality_gate"),
            "STORYFORGE_GATE_THRESHOLD": ("pipeline", "quality_gate_threshold"),
            "STORYFORGE_BLOCK_INJECTION": ("pipeline", "block_on_injection"),
        }
        for env_key, (section, field_name) in env_map.items():
            val = os.environ.get(env_key)
            if val:
                target = self.llm if section == "llm" else self.pipeline
                # Convert to float for float fields
                if field_name in ("temperature", "quality_gate_threshold"):
                    try:
                        val = float(val)
                    except ValueError:
                        continue
                # Convert to bool for boolean fields
                elif field_name in ("rag_enabled", "enable_character_consistency", "use_long_context", "enable_agent_debate", "enable_smart_revision", "enable_quality_gate", "block_on_injection"):
                    val = val.lower() in ("1", "true", "yes")
                setattr(target, field_name, val)

    def save(self) -> list[str]:
        """Save config. Returns warnings. Raises ValueError on critical errors."""
        os.makedirs(os.path.dirname(self.CONFIG_FILE), exist_ok=True)
        warnings = self.validate()
        critical = [w for w in warnings if "bắt buộc" in w or "phải" in w]
        if critical:
            raise ValueError(f"Config invalid: {'; '.join(critical)}")
        data = {
            "llm": {
                # api_key excluded — use STORYFORGE_API_KEY env var
                "base_url": self.llm.base_url,
                "model": self.llm.model,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
                "backend_type": self.llm.backend_type,
                "web_auth_provider": self.llm.web_auth_provider,
                "cheap_model": self.llm.cheap_model,
                "cheap_base_url": self.llm.cheap_base_url,
                "cache_enabled": self.llm.cache_enabled,
                "cache_ttl_days": self.llm.cache_ttl_days,
                "max_parallel_workers": self.llm.max_parallel_workers,
                "layer1_model": self.llm.layer1_model,
                "layer2_model": self.llm.layer2_model,
                "layer3_model": self.llm.layer3_model,
            },
            "pipeline": {
                "num_chapters": self.pipeline.num_chapters,
                "words_per_chapter": self.pipeline.words_per_chapter,
                "genre": self.pipeline.genre,
                "writing_style": self.pipeline.writing_style,
                "num_simulation_rounds": self.pipeline.num_simulation_rounds,
                "num_agents": self.pipeline.num_agents,
                "drama_intensity": self.pipeline.drama_intensity,
                "shots_per_chapter": self.pipeline.shots_per_chapter,
                "video_style": self.pipeline.video_style,
                "context_window_chapters": self.pipeline.context_window_chapters,
                "language": self.pipeline.language,
                "user_storage_path": self.pipeline.user_storage_path,
                "image_prompt_style": self.pipeline.image_prompt_style,
                "share_base_url": self.pipeline.share_base_url,
                "pdf_font": self.pipeline.pdf_font,
                "image_provider": self.pipeline.image_provider,
                # image_api_key excluded — use IMAGE_API_KEY env var
                "image_api_url": self.pipeline.image_api_url,
                # seedream_api_key excluded — use SEEDREAM_API_KEY env var
                "seedream_api_url": self.pipeline.seedream_api_url,
                "arc_size": self.pipeline.arc_size,
                "story_bible_enabled": self.pipeline.story_bible_enabled,
                "enable_self_review": self.pipeline.enable_self_review,
                "self_review_threshold": self.pipeline.self_review_threshold,
                "tts_provider": self.pipeline.tts_provider,
                # kling_tts_api_key excluded — use KLING_TTS_API_KEY env var
                "kling_tts_api_url": self.pipeline.kling_tts_api_url,
                "rag_enabled": self.pipeline.rag_enabled,
                "rag_persist_dir": self.pipeline.rag_persist_dir,
                "chroma_persist_dir": self.pipeline.chroma_persist_dir,
                "chroma_collection_name": self.pipeline.chroma_collection_name,
                "xtts_api_url": self.pipeline.xtts_api_url,
                "xtts_reference_audio": self.pipeline.xtts_reference_audio,
                "character_voice_map": self.pipeline.character_voice_map,
                "enable_character_consistency": self.pipeline.enable_character_consistency,
                # replicate_api_key excluded — use REPLICATE_API_KEY env var
                "character_consistency_provider": self.pipeline.character_consistency_provider,
                "enable_agent_debate": self.pipeline.enable_agent_debate,
                "max_debate_rounds": self.pipeline.max_debate_rounds,
                "debate_mode": self.pipeline.debate_mode,
                "enable_smart_revision": self.pipeline.enable_smart_revision,
                "smart_revision_threshold": self.pipeline.smart_revision_threshold,
                "enable_quality_gate": self.pipeline.enable_quality_gate,
                "quality_gate_threshold": self.pipeline.quality_gate_threshold,
                "quality_gate_chapter_threshold": self.pipeline.quality_gate_chapter_threshold,
                "quality_gate_max_retries": self.pipeline.quality_gate_max_retries,
                # long_context_api_key excluded — use LONG_CONTEXT_API_KEY env var
            },
        }
        if warnings:
            import logging
            for w in warnings:
                logging.getLogger(__name__).warning(f"Config: {w}")
        # Encrypt sensitive fields before persisting (no-op when no secret key set)
        from services.secret_manager import encrypt_sensitive_fields
        data = encrypt_sensitive_fields(data)
        with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return warnings

    def validate(self) -> list[str]:
        """Validate config, return list of warning messages."""
        errors = []
        if not self.llm.api_key and self.llm.backend_type == "api":
            errors.append("API key bắt buộc cho backend API")
        if self.pipeline.num_chapters < 1:
            errors.append("Số chương phải >= 1")
        if self.pipeline.words_per_chapter < 100:
            errors.append("Số từ/chương phải >= 100")
        if self.pipeline.video_quality not in ("draft", "final"):
            errors.append("video_quality phải là 'draft' hoặc 'final'")
        if not (1.0 <= self.pipeline.self_review_threshold <= 5.0):
            errors.append("self_review_threshold phải từ 1.0 đến 5.0")
        if self.pipeline.debate_mode not in ("full", "lite"):
            errors.append("debate_mode phải là 'full' hoặc 'lite'")
        if not (1.0 <= self.pipeline.smart_revision_threshold <= 5.0):
            errors.append("smart_revision_threshold phải từ 1.0 đến 5.0")
        if not (1.0 <= self.pipeline.quality_gate_threshold <= 5.0):
            errors.append("quality_gate_threshold phải từ 1.0 đến 5.0")
        # Warn about likely-invalid OpenRouter model IDs
        if "openrouter" in self.llm.base_url:
            model = self.llm.model
            if model and "/" not in model:
                errors.append(
                    f"Model '{model}' không hợp lệ cho OpenRouter. "
                    f"Cần format 'provider/model-name' (ví dụ: deepseek/deepseek-chat-v3-0324:free)"
                )
            elif model and model.startswith("openrouter/"):
                errors.append(
                    f"Model '{model}' có thể route random — nên dùng model cụ thể "
                    f"(ví dụ: deepseek/deepseek-chat-v3-0324:free)"
                )
        return errors

    def get_review_threshold(self, genre: str = "") -> float:
        """Return genre-aware self-review threshold.

        Looks up genre (case-insensitive) in self_review_genre_thresholds.
        Falls back to self_review_threshold if not found.
        """
        if not genre:
            return self.pipeline.self_review_threshold
        genre_lower = genre.lower().strip()
        table = self.pipeline.self_review_genre_thresholds or {}
        for key, val in table.items():
            if key.lower() in genre_lower or genre_lower in key.lower():
                return float(val)
        return self.pipeline.self_review_threshold
