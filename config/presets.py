"""Pipeline presets and model presets for StoryForge."""

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
