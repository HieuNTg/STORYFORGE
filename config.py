"""Quản lý cấu hình cho StoryForge."""

import os
import json
import threading
from dataclasses import dataclass, field
from typing import Optional


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
    self_review_threshold: float = 3.0  # Score threshold (1.0-5.0)

    # TTS provider
    tts_provider: str = "edge-tts"  # edge-tts / kling / none
    kling_tts_api_key: str = ""
    kling_tts_api_url: str = ""

    # RAG world-building
    rag_enabled: bool = False
    rag_persist_dir: str = "data/rag"

    # XTTS v2 voice cloning
    xtts_api_url: str = ""  # http://localhost:8020 or Replicate URL
    xtts_reference_audio: str = ""  # default reference audio path
    character_voice_map: dict = field(default_factory=dict)  # {"CharName": "data/voices/char.wav"}

    # Character-consistent images
    enable_character_consistency: bool = False
    replicate_api_key: str = ""
    character_consistency_provider: str = "seedream"  # seedream | replicate


VIDEO_QUALITY_PRESETS = {
    "draft": {"resolution": "512x512", "fps": 24, "crf": "28", "preset": "fast"},
    "final": {"resolution": "1024x1024", "fps": 30, "crf": "23", "preset": "medium"},
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
                    data = json.load(f)
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
            "XTTS_API_URL": ("pipeline", "xtts_api_url"),
            "XTTS_REFERENCE_AUDIO": ("pipeline", "xtts_reference_audio"),
            "REPLICATE_API_KEY": ("pipeline", "replicate_api_key"),
            "STORYFORGE_CHAR_CONSISTENCY": ("pipeline", "enable_character_consistency"),
        }
        for env_key, (section, field) in env_map.items():
            val = os.environ.get(env_key)
            if val:
                target = self.llm if section == "llm" else self.pipeline
                # Convert to float for temperature
                if field == "temperature":
                    try:
                        val = float(val)
                    except ValueError:
                        continue
                # Convert to bool for boolean fields
                elif field in ("rag_enabled", "enable_character_consistency"):
                    val = val.lower() in ("1", "true", "yes")
                setattr(target, field, val)

    def save(self) -> list[str]:
        """Save config. Returns warnings. Raises ValueError on critical errors."""
        os.makedirs(os.path.dirname(self.CONFIG_FILE), exist_ok=True)
        warnings = self.validate()
        critical = [w for w in warnings if "bắt buộc" in w or "phải" in w]
        if critical:
            raise ValueError(f"Config invalid: {'; '.join(critical)}")
        data = {
            "llm": {
                "api_key": self.llm.api_key,
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
                "image_api_key": self.pipeline.image_api_key,
                "image_api_url": self.pipeline.image_api_url,
                "seedream_api_key": self.pipeline.seedream_api_key,
                "seedream_api_url": self.pipeline.seedream_api_url,
                "arc_size": self.pipeline.arc_size,
                "story_bible_enabled": self.pipeline.story_bible_enabled,
                "enable_self_review": self.pipeline.enable_self_review,
                "self_review_threshold": self.pipeline.self_review_threshold,
                "tts_provider": self.pipeline.tts_provider,
                "kling_tts_api_key": self.pipeline.kling_tts_api_key,
                "kling_tts_api_url": self.pipeline.kling_tts_api_url,
                "rag_enabled": self.pipeline.rag_enabled,
                "rag_persist_dir": self.pipeline.rag_persist_dir,
                "xtts_api_url": self.pipeline.xtts_api_url,
                "xtts_reference_audio": self.pipeline.xtts_reference_audio,
                "character_voice_map": self.pipeline.character_voice_map,
                "enable_character_consistency": self.pipeline.enable_character_consistency,
                "replicate_api_key": self.pipeline.replicate_api_key,
                "character_consistency_provider": self.pipeline.character_consistency_provider,
            },
        }
        if warnings:
            import logging
            for w in warnings:
                logging.getLogger(__name__).warning(f"Config: {w}")
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
        return errors
