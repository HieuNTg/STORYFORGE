"""Save/load config from JSON and apply environment variable overrides."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .defaults import LLMConfig, PipelineConfig

logger = logging.getLogger(__name__)

CONFIG_FILE = "data/config.json"
_SECRETS_FILE = "data/secrets.json"

# Maps env var name -> (section, field_name)
# Note: ZAI_API_KEY is handled directly in client._build_fallback_chain for auto-fallback
_ENV_MAP: dict[str, tuple[str, str]] = {
    "STORYFORGE_API_KEY": ("llm", "api_key"),
    "STORYFORGE_BASE_URL": ("llm", "base_url"),
    "STORYFORGE_MODEL": ("llm", "model"),
    "STORYFORGE_TEMPERATURE": ("llm", "temperature"),
    "STORYFORGE_IMAGE_PROVIDER": ("pipeline", "image_provider"),
    "IMAGE_API_KEY": ("pipeline", "image_api_key"),
    "IMAGE_API_URL": ("pipeline", "image_api_url"),
    "SEEDREAM_API_KEY": ("pipeline", "seedream_api_key"),
    "SEEDREAM_API_URL": ("pipeline", "seedream_api_url"),
    "STORYFORGE_RAG_ENABLED": ("pipeline", "rag_enabled"),
    "STORYFORGE_RAG_DIR": ("pipeline", "rag_persist_dir"),
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

_FLOAT_FIELDS = {"temperature", "quality_gate_threshold"}
_BOOL_FIELDS = {
    "rag_enabled", "enable_character_consistency", "use_long_context",
    "enable_agent_debate", "enable_smart_revision", "enable_quality_gate",
    "block_on_injection",
}


def load_config(llm: "LLMConfig", pipeline: "PipelineConfig") -> None:
    """Load config from JSON file, then secrets, then env var overrides."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.get("llm", {}).items():
                if hasattr(llm, k):
                    setattr(llm, k, v)
            for k, v in data.get("pipeline", {}).items():
                if hasattr(pipeline, k):
                    setattr(pipeline, k, v)
        except Exception as e:
            logger.warning(f"Config load error: {e}")

    _load_secrets(llm, pipeline)
    _apply_env_overrides(llm, pipeline)


def _load_secrets(llm: "LLMConfig", pipeline: "PipelineConfig") -> None:
    """Load encrypted secrets from secrets file.

    Only loads when STORYFORGE_SECRET_KEY is set (encryption active).
    Without it, config.json already contains all values in plaintext
    and secrets.json may hold stale/dummy data that would overwrite
    real keys.
    """
    if not os.path.exists(_SECRETS_FILE):
        return
    if not os.environ.get("STORYFORGE_SECRET_KEY"):
        return
    try:
        from services.secret_manager import load_encrypted
        data = load_encrypted(_SECRETS_FILE)
        for k, v in data.get("llm", {}).items():
            if hasattr(llm, k) and v:
                setattr(llm, k, v)
        for k, v in data.get("pipeline", {}).items():
            if hasattr(pipeline, k) and v:
                setattr(pipeline, k, v)
    except Exception as e:
        logger.warning(f"Secrets load error: {e}")


def _save_secrets(llm: "LLMConfig", pipeline: "PipelineConfig") -> None:
    """Persist sensitive fields (api keys, fallback profiles) to encrypted file."""
    try:
        from services.secret_manager import save_encrypted
        data = {
            "llm": {
                "api_key": llm.api_key,
                "api_keys": llm.api_keys,
                "fallback_models": llm.fallback_models,
            },
            "pipeline": {
                k: getattr(pipeline, k)
                for k in ("image_api_key", "seedream_api_key", "replicate_api_key",
                           "long_context_api_key", "hf_token")
                if getattr(pipeline, k, "")
            },
        }
        os.makedirs(os.path.dirname(_SECRETS_FILE), exist_ok=True)
        save_encrypted(_SECRETS_FILE, data)
    except Exception as e:
        logger.warning(f"Secrets save error: {e}")


def _apply_env_overrides(llm: "LLMConfig", pipeline: "PipelineConfig") -> None:
    """Apply environment variable overrides (for Docker/production)."""
    for env_key, (section, field) in _ENV_MAP.items():
        val = os.environ.get(env_key)
        if not val:
            continue
        target = llm if section == "llm" else pipeline
        if field in _FLOAT_FIELDS:
            try:
                val = float(val)  # type: ignore[assignment]
            except ValueError:
                continue
        elif field in _BOOL_FIELDS:
            val = val.lower() in ("1", "true", "yes")  # type: ignore[assignment]
        setattr(target, field, val)


def save_config(llm: "LLMConfig", pipeline: "PipelineConfig") -> None:
    """Persist config to JSON including API keys for local self-hosted use."""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    data = {
        "llm": {
            "api_key": llm.api_key,
            "api_keys": llm.api_keys,
            "fallback_models": llm.fallback_models,
            "base_url": llm.base_url,
            "model": llm.model,
            "temperature": llm.temperature,
            "max_tokens": llm.max_tokens,
            "cheap_model": llm.cheap_model,
            "cheap_base_url": llm.cheap_base_url,
            "cache_enabled": llm.cache_enabled,
            "cache_ttl_days": llm.cache_ttl_days,
            "max_parallel_workers": llm.max_parallel_workers,
            "layer1_model": llm.layer1_model,
            "layer2_model": llm.layer2_model,
        },
        "pipeline": {
            "num_chapters": pipeline.num_chapters,
            "words_per_chapter": pipeline.words_per_chapter,
            "genre": pipeline.genre,
            "writing_style": pipeline.writing_style,
            "num_simulation_rounds": pipeline.num_simulation_rounds,
            "num_agents": pipeline.num_agents,
            "drama_intensity": pipeline.drama_intensity,
            "context_window_chapters": pipeline.context_window_chapters,
            "language": pipeline.language,
            "user_storage_path": pipeline.user_storage_path,
            "image_prompt_style": pipeline.image_prompt_style,
            "share_base_url": pipeline.share_base_url,
            "pdf_font": pipeline.pdf_font,
            "image_provider": pipeline.image_provider,
            "image_api_key": pipeline.image_api_key,
            "image_api_url": pipeline.image_api_url,
            "seedream_api_key": pipeline.seedream_api_key,
            "seedream_api_url": pipeline.seedream_api_url,
            "arc_size": pipeline.arc_size,
            "story_bible_enabled": pipeline.story_bible_enabled,
            "enable_self_review": pipeline.enable_self_review,
            "self_review_threshold": pipeline.self_review_threshold,
            "rag_enabled": pipeline.rag_enabled,
            "rag_persist_dir": pipeline.rag_persist_dir,
            "enable_character_consistency": pipeline.enable_character_consistency,
            "replicate_api_key": getattr(pipeline, "replicate_api_key", ""),
            "character_consistency_provider": pipeline.character_consistency_provider,
            "enable_smart_revision": pipeline.enable_smart_revision,
            "smart_revision_threshold": pipeline.smart_revision_threshold,
            "enable_quality_gate": pipeline.enable_quality_gate,
            "quality_gate_threshold": pipeline.quality_gate_threshold,
            "quality_gate_chapter_threshold": pipeline.quality_gate_chapter_threshold,
            "quality_gate_max_retries": pipeline.quality_gate_max_retries,
            "hf_token": getattr(pipeline, "hf_token", ""),
            "hf_image_model": getattr(pipeline, "hf_image_model", ""),
            "long_context_api_key": getattr(pipeline, "long_context_api_key", ""),
            "long_context_provider": getattr(pipeline, "long_context_provider", ""),
            "long_context_model": getattr(pipeline, "long_context_model", ""),
            "long_context_base_url": getattr(pipeline, "long_context_base_url", ""),
        },
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _save_secrets(llm, pipeline)
