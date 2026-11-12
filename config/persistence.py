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
_SECRETS_FILE = "data/secrets.json"  # legacy — read-only fallback for migration

#: Image providers that automated a consumer web session and were removed.
#: An older config.json may still select one; load_config resets it to "none"
#: and records the name in ``image_provider_notice`` so the UI can say why.
REMOVED_IMAGE_PROVIDERS: frozenset[str] = frozenset({"flowkit", "codex", "qwen-local"})
#: Config keys those providers owned. save_config drops them from the file.
_REMOVED_KEY_PREFIXES = ("flowkit_", "qwen_local_", "codex_")

# Maps env var name -> (section, field_name)
# Note: ZAI_API_KEY is handled directly in client._build_fallback_chain for auto-fallback
_ENV_MAP: dict[str, tuple[str, str]] = {
    "STORYFORGE_API_KEY": ("llm", "api_key"),
    "STORYFORGE_BASE_URL": ("llm", "base_url"),
    "STORYFORGE_MODEL": ("llm", "model"),
    "STORYFORGE_REQUEST_TIMEOUT": ("llm", "request_timeout"),
    "STORYFORGE_TEMPERATURE": ("llm", "temperature"),
    "STORYFORGE_IMAGE_PROVIDER": ("pipeline", "image_provider"),
    "STORYFORGE_LENGTH_GATE": ("pipeline", "enable_length_gate"),
    "STORYFORGE_AGENTIC_REPAIR": ("pipeline", "enable_agentic_repair"),
    "STORYFORGE_LENGTH_GATE_RATIO": ("pipeline", "length_gate_min_ratio"),
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

_FLOAT_FIELDS = {"temperature", "quality_gate_threshold", "request_timeout"}
# Env values arrive as strings. A bool field missing from this set gets the raw
# string, and every non-empty string is truthy — so `FLAG=0` turns the flag ON.
# Any bool in _ENV_MAP must be listed here or its override can only ever enable.
_BOOL_FIELDS = {
    "rag_enabled",
    "enable_character_consistency",
    "use_long_context",
    "enable_agent_debate",
    "enable_smart_revision",
    "enable_quality_gate",
    "block_on_injection",
    # Both were reachable from _ENV_MAP without coercion: STORYFORGE_LENGTH_GATE=0
    # and STORYFORGE_AGENTIC_REPAIR=0 set the string "0" and left the flag on.
    "enable_length_gate",
    "enable_agentic_repair",
}


def load_config(llm: "LLMConfig", pipeline: "PipelineConfig") -> None:
    """Load config from JSON file, then secrets, then env var overrides."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            from services.secret_manager import decrypt_sensitive_fields

            data = decrypt_sensitive_fields(data)
            for k, v in data.get("llm", {}).items():
                if hasattr(llm, k):
                    setattr(llm, k, v)
            for k, v in data.get("pipeline", {}).items():
                if hasattr(pipeline, k):
                    setattr(pipeline, k, v)
        except Exception as e:
            logger.warning(f"Config load error: {e}")

    _migrate_legacy_secrets(llm, pipeline)
    _apply_env_overrides(llm, pipeline)
    _retire_removed_providers(pipeline)


def _retire_removed_providers(pipeline: "PipelineConfig") -> None:
    """Reset a removed image provider to "none" and remember which one it was.

    Runs after the file, the legacy secrets and the environment have all been
    applied, so a removed provider is caught whichever of them selected it.
    """
    for field in ("image_provider", "character_consistency_provider"):
        value = getattr(pipeline, field, "")
        if value in REMOVED_IMAGE_PROVIDERS:
            logger.warning(
                "%s %r is no longer supported; reset to 'none'", field, value
            )
            setattr(pipeline, field, "none")
            if not pipeline.image_provider_notice:
                pipeline.image_provider_notice = value


def _migrate_legacy_secrets(llm: "LLMConfig", pipeline: "PipelineConfig") -> None:
    """One-shot migration from legacy data/secrets.json into config.json.

    Older versions persisted sensitive fields to a separate encrypted file.
    That file became unreadable whenever STORYFORGE_SECRET_KEY was unset,
    silently locking away the user's real API keys/profiles. This recovers
    them: read once, fold into the in-memory config, then on the next save
    config.json becomes the single source of truth and the legacy file is
    can be archived manually after verification.
    """
    if not os.path.exists(_SECRETS_FILE):
        return
    try:
        from services.secret_manager import load_encrypted

        data = load_encrypted(_SECRETS_FILE)
    except Exception as e:
        logger.warning(f"Legacy secrets load error: {e}")
        return
    if not data:
        # Encrypted with a key we no longer have, or corrupt — ignore it.
        logger.warning(
            "%s exists but could not be read (encrypted with a different "
            "key). Config now lives in %s; archive or delete the legacy file "
            "to silence this warning.",
            _SECRETS_FILE,
            CONFIG_FILE,
        )
        return
    recovered = False
    for k, v in data.get("llm", {}).items():
        if hasattr(llm, k) and v and not getattr(llm, k):
            setattr(llm, k, v)
            recovered = True
    for k, v in data.get("pipeline", {}).items():
        if hasattr(pipeline, k) and v and not getattr(pipeline, k):
            setattr(pipeline, k, v)
            recovered = True
    if recovered:
        logger.info("Loaded values from legacy secrets.json into in-memory config")


def _env_overridden_fields(section: str) -> set[str]:
    """Fields in `section` whose value currently comes from the environment.

    save_config must not write these back: an env override wins at runtime, but
    baking it into config.json would silently overwrite the choice the user made
    in Settings, and would outlive the env var itself. Computed from os.environ
    on demand rather than remembered from the last load, so there is no stale
    state to leak between calls.
    """
    return {
        field
        for env_key, (sec, field) in _ENV_MAP.items()
        if sec == section and os.environ.get(env_key)
    }


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


# Fields deliberately kept out of config.json.
#   voice — a derived nested view of the flat voice_*/l2_voice_* fields, rebuilt
#   by PipelineConfig.__post_init__. Persisting it would let a stale copy fight
#   the flat fields that stay authoritative.
#   image_provider_notice — runtime only; it describes this load, not a setting.
_NON_PERSISTED_PIPELINE_FIELDS = frozenset({"voice", "image_provider_notice"})
_NON_PERSISTED_LLM_FIELDS: frozenset[str] = frozenset()


def _section_dict(obj, skip: frozenset) -> dict:
    """Every dataclass field except the excluded ones."""
    import dataclasses

    return {
        f.name: getattr(obj, f.name)
        for f in dataclasses.fields(obj)
        if f.name not in skip
    }


def save_config(llm: "LLMConfig", pipeline: "PipelineConfig") -> None:
    """Persist config to JSON, encrypting sensitive fields (key auto-generated in data/.secret_key).

    Sections are built from the dataclass fields rather than a hand-written list.
    The list had drifted to 103 of 244 fields, so every l2_* knob, the budget
    caps, chapter_batch_size and parallel_chapters_enabled silently reverted to
    code defaults on restart — and because the writer replaced the file wholesale,
    any key it did not know about was deleted on the next save.
    """
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

    # Keep anything already on disk that neither dataclass claims, so a key
    # written by an older or newer build survives a save from this one.
    existing: dict = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read existing config for merge: {e}")

    def _kept(section: str) -> dict:
        # Keys of removed providers are dropped rather than carried forward.
        return {
            k: v
            for k, v in (existing.get(section) or {}).items()
            if not k.startswith(_REMOVED_KEY_PREFIXES)
        }

    data = {
        **{k: v for k, v in existing.items() if k not in ("llm", "pipeline")},
        "llm": {
            **_kept("llm"),
            **_section_dict(
                llm, _NON_PERSISTED_LLM_FIELDS | _env_overridden_fields("llm")
            ),
        },
        "pipeline": {
            **_kept("pipeline"),
            **_section_dict(
                pipeline,
                _NON_PERSISTED_PIPELINE_FIELDS | _env_overridden_fields("pipeline"),
            ),
        },
    }

    from services.secret_manager import encrypt_sensitive_fields

    data = encrypt_sensitive_fields(data)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)
