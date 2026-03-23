"""Quản lý cấu hình cho Novel Auto Pipeline."""

import os
import json
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
    # Cấu hình backend switching
    backend_type: str = "api"  # "api" hoặc "openclaw"
    openclaw_port: int = 3002
    openclaw_model: str = "deepseek-web/deepseek-chat"
    auto_fallback: bool = True  # Tự động chuyển sang API khi OpenClaw fail
    # Model routing: cheap model for summaries/analysis
    cheap_model: str = ""  # empty = use primary model
    cheap_base_url: str = ""  # empty = use primary base_url
    cache_enabled: bool = True
    cache_ttl_days: int = 7
    max_parallel_workers: int = 3


@dataclass
class PipelineConfig:
    """Cấu hình pipeline tổng thể."""
    # Layer 1 - Tạo truyện
    num_chapters: int = 10
    words_per_chapter: int = 2000
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
    context_window_chapters: int = 2

    # Ngôn ngữ
    language: str = "vi"


class ConfigManager:
    """Singleton quản lý cấu hình."""

    _instance = None
    CONFIG_FILE = "data/config.json"

    def __new__(cls):
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

    def save(self):
        os.makedirs(os.path.dirname(self.CONFIG_FILE), exist_ok=True)
        data = {
            "llm": {
                "api_key": self.llm.api_key,
                "base_url": self.llm.base_url,
                "model": self.llm.model,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
                # Backend switching
                "backend_type": self.llm.backend_type,
                "openclaw_port": self.llm.openclaw_port,
                "openclaw_model": self.llm.openclaw_model,
                "auto_fallback": self.llm.auto_fallback,
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
            },
        }
        with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
