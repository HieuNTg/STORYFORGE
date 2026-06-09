"""Pipeline presets and provider presets for StoryForge."""

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

# Local OpenAI-compatible bridge to the Gemini web app (gemini-webapi server).
# Runs at http://localhost:8000 — see Gemini-API/server/README.md.
_GEMINI_LOCAL_BASE = "http://localhost:8000/v1"

# ---------------------------------------------------------------------------
# Provider presets — single source of truth for the "Quick provider" cards in
# the Settings UI (frontend fetches these via GET /api/config/provider-presets).
#
# Each entry is a per-provider setup card: a base_url, a list of selectable
# models, and a key placeholder. The user picks a model and enters their own
# API key to create a profile.
#
# Keep this the ONLY place provider cards are defined — the frontend no longer
# hardcodes them. Keys are snake_case (API convention); the UI maps base_url →
# baseUrl when rendering.
# ---------------------------------------------------------------------------
PROVIDER_PRESETS = [
    {
        "name": "Google Gemini",
        "label": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.5-flash",
        "models": [
            {"id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash"},
            {"id": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash Lite"},
            {"id": "gemini-3.1-flash-lite-preview", "label": "Gemini 3.1 Flash Lite Preview"},
            {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
            {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
            {"id": "gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
            {"id": "gemma-4-31b-it", "label": "Gemma 4 31B"},
            {"id": "gemma-4-26b-a4b-it", "label": "Gemma 4 26B A4B"},
        ],
        "placeholder": "AIza...",
    },
    {
        "name": "Anthropic",
        "label": "Anthropic",
        "base_url": "https://api.anthropic.com/v1/",
        "model": "claude-sonnet-4-6",
        "models": [
            {"id": "claude-opus-4-7", "label": "Claude Opus 4.7"},
            {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
            {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
            {"id": "claude-opus-4-6", "label": "Claude Opus 4.6"},
            {"id": "claude-sonnet-4-5-20250929", "label": "Claude Sonnet 4.5"},
        ],
        "placeholder": "sk-ant-...",
    },
    {
        "name": "OpenAI",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.4-mini",
        "models": [
            {"id": "gpt-5.5", "label": "GPT-5.5"},
            {"id": "gpt-5.4-mini", "label": "GPT-5.4 Mini"},
            {"id": "gpt-5.4-nano", "label": "GPT-5.4 Nano"},
            {"id": "gpt-chat-latest", "label": "GPT Chat Latest"},
            {"id": "gpt-4o-mini", "label": "GPT-4o Mini"},
            {"id": "gpt-4o", "label": "GPT-4o"},
        ],
        "placeholder": "sk-...",
    },
    {
        "name": "OpenRouter",
        "label": "OpenRouter Free",
        "base_url": _OPENROUTER_BASE,
        "model": "openrouter/free",
        "models": [
            {"id": "openrouter/free", "label": "Free Models Router"},
            {"id": "baidu/cobuddy:free", "label": "Baidu CoBuddy (free)"},
            {"id": "openrouter/owl-alpha", "label": "Owl Alpha"},
            {"id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "label": "NVIDIA Nemotron 3 Nano Omni (free)"},
            {"id": "poolside/laguna-xs.2:free", "label": "Poolside Laguna XS.2 (free)"},
            {"id": "poolside/laguna-m.1:free", "label": "Poolside Laguna M.1 (free)"},
            {"id": "deepseek/deepseek-v4-flash:free", "label": "DeepSeek V4 Flash (free)"},
            {"id": "z-ai/glm-5.1", "label": "Z.AI GLM 5.1 (free)"},
            {"id": "google/gemma-4-26b-a4b-it:free", "label": "Google Gemma 4 26B A4B (free)"},
            {"id": "google/gemma-4-31b-it:free", "label": "Google Gemma 4 31B (free)"},
            {"id": "arcee-ai/trinity-large-thinking:free", "label": "Arcee Trinity Large Thinking (free)"},
            {"id": "nvidia/nemotron-3-super-120b-a12b:free", "label": "NVIDIA Nemotron 3 Super (free)"},
            {"id": "minimax/minimax-m2.5:free", "label": "MiniMax M2.5 (free)"},
            {"id": "qwen/qwen3-next-80b-a3b-instruct:free", "label": "Qwen3 Next 80B A3B Instruct (free)"},
            {"id": "openai/gpt-oss-120b:free", "label": "OpenAI GPT OSS 120B (free)"},
            {"id": "openai/gpt-oss-20b:free", "label": "OpenAI GPT OSS 20B (free)"},
            {"id": "z-ai/glm-4.5-air:free", "label": "Z.AI GLM 4.5 Air (free)"},
            {"id": "qwen/qwen3-coder:free", "label": "Qwen3 Coder 480B A35B (free)"},
            {"id": "meta-llama/llama-3.3-70b-instruct:free", "label": "Llama 3.3 70B Instruct (free)"},
        ],
        "placeholder": "sk-or-...",
    },
    {
        "name": "Z.AI",
        "label": "Z.AI",
        "base_url": "https://api.z.ai/api/paas/v4",
        "model": "glm-4.7-flash",
        "models": [
            {"id": "glm-4.7-flash", "label": "GLM 4.7 Flash"},
            {"id": "glm-4.6", "label": "GLM 4.6"},
            {"id": "glm-4-flash", "label": "GLM 4 Flash"},
        ],
        "placeholder": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.xxxxx",
    },
    {
        "name": "Kyma",
        "label": "Kyma",
        "base_url": _KYMA_BASE,
        "model": "qwen-3.6-plus",
        "models": [
            {"id": "qwen-3.6-plus", "label": "Qwen 3.6 Plus"},
            {"id": "qwen-3.6", "label": "Qwen 3.6"},
            {"id": "deepseek-v3.2", "label": "DeepSeek V3.2"},
        ],
        "placeholder": "ky-...",
    },
    {
        # Local OpenAI-compatible bridge to the Gemini web app (gemini-webapi).
        # Requires running the bridge at localhost:8000 — see Gemini-API/server/README.md.
        # The bridge maps any model name to the web app's current default (Gemini 3.5 Flash).
        "name": "Gemini Web (local/dev)",
        "label": "Gemini Web (local/dev)",
        "base_url": _GEMINI_LOCAL_BASE,
        "model": "gemini-3.5-flash",
        "models": [
            {"id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash (web default)"},
        ],
        "placeholder": "changeme-internal-key",
    },
]
