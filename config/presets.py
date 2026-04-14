"""Pipeline presets and model presets for StoryForge."""

PIPELINE_PRESETS = {
    "beginner": {
        "label": "Người mới — Cơ bản, dễ dùng",
        "enable_self_review": False,
        "enable_agent_debate": False,
        "enable_smart_revision": False,
        "use_long_context": False,
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
        "enable_smart_revision": True,
        "smart_revision_threshold": 3.5,
        "enable_quality_gate": True,
        "quality_gate_threshold": 2.5,
        "quality_gate_max_retries": 1,
        "use_long_context": False,
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
        "enable_smart_revision": True,
        "smart_revision_threshold": 3.0,
        "enable_quality_gate": True,
        "quality_gate_threshold": 2.5,
        "quality_gate_max_retries": 1,
        "use_long_context": True,
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
_KYMA_BASE = "https://kymaapi.com/v1"

MODEL_PRESETS = {
    "kyma-auto": {
        "label": "Kyma — Auto Failover (recommended)",
        "base_url": _KYMA_BASE,
        "model": "qwen-3.6-plus",
        "cheap_model": "",
        "cheap_base_url": _KYMA_BASE,
        "layer1_model": "",
        "layer2_model": "",
        "fallback_models": [],  # Kyma handles failover internally
    },
    "openrouter-free-auto": {
        "label": "OpenRouter Free — Auto Router",
        "base_url": _OPENROUTER_BASE,
        "model": "openrouter/free",
        "cheap_model": "",
        "cheap_base_url": _OPENROUTER_BASE,
        "layer1_model": "",
        "layer2_model": "",
        "fallback_models": [],
    },
    "openrouter-free-basic": {
        "label": "OpenRouter Free — Hermes 405B",
        "base_url": _OPENROUTER_BASE,
        "model": "nousresearch/hermes-3-llama-3.1-405b:free",
        "cheap_model": "",
        "cheap_base_url": _OPENROUTER_BASE,
        "layer1_model": "",
        "layer2_model": "",
        "fallback_models": [
            {"model": "openrouter/free", "base_url": _OPENROUTER_BASE},
        ],
    },
    "openrouter-free-optimized": {
        "label": "OpenRouter Free — Per-layer routing",
        "base_url": _OPENROUTER_BASE,
        "model": "openrouter/free",
        "cheap_model": "",
        "cheap_base_url": _OPENROUTER_BASE,
        "layer1_model": "nousresearch/hermes-3-llama-3.1-405b:free",
        "layer2_model": "nvidia/nemotron-3-super-120b-a12b:free",
        "fallback_models": [
            {"model": "openrouter/free", "base_url": _OPENROUTER_BASE},
        ],
    },
}
