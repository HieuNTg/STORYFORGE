"""LLMClient — singleton LLM caller with retry and cache."""

import logging
import random
import re
import sqlite3
import time
import threading
import uuid
from dataclasses import dataclass
from typing import Optional
from services.llm.retry import (
    MAX_RETRIES, BASE_DELAY,
    _redact, _is_transient, _is_auth_error, _detect_provider, _should_retry,
    parse_openrouter_reset,
)
from services.llm.streaming import StreamingMixin
from services.llm.generation import GenerationMixin
from services.llm.model_fallback import get_fallback_manager

logger = logging.getLogger(__name__)


@dataclass
class LayerConfig:
    """Configuration for a specific pipeline layer."""
    model: str
    base_url: str
    api_key: str
    is_layer_specific: bool = False  # True if using layer-specific provider


# Explicit OpenRouter → Kyma model mapping (Kyma uses different naming)
_OPENROUTER_TO_KYMA = {
    "qwen/qwen3.6-plus:free": "qwen-3.6-plus",
    "qwen/qwen-3.6-plus:free": "qwen-3.6-plus",
    "qwen/qwen-3-32b:free": "qwen-3-32b",
    "deepseek/deepseek-v3:free": "deepseek-v3",
    "deepseek/deepseek-r1:free": "deepseek-r1",
    "meta-llama/llama-3.3-70b-instruct:free": "llama-3.3-70b",
    "minimax/minimax-m2.5:free": "minimax-m2.5",
    "google/gemini-2.5-flash:free": "gemini-2.5-flash",
    "google/gemma-4-31b-it:free": "gemma-4-31b",
    "openai/gpt-oss-120b:free": "gpt-oss-120b",
}


def _detect_provider_type(base_url: str) -> str:
    """Detect provider type from base URL."""
    if not base_url:
        return "unknown"
    url = base_url.lower()
    if "openrouter" in url:
        return "openrouter"
    if "kymaapi.com" in url:
        return "kyma"
    if "anthropic.com" in url:
        return "anthropic"
    if "openai.com" in url:
        return "openai"
    if "googleapis.com" in url or "generativelanguage" in url:
        return "google"
    if "z.ai" in url:
        return "zai"
    return "generic"


def _model_matches_provider(model: str, provider: str) -> bool:
    """Check if model format matches provider expectations."""
    if not model:
        return False

    # Special routers work only on their provider
    if model == "openrouter/free":
        return provider == "openrouter"

    has_slash = "/" in model
    has_colon = ":" in model

    if provider == "openrouter":
        # OpenRouter uses vendor/model or vendor/model:variant
        return has_slash
    if provider == "kyma":
        # Kyma uses simple IDs without slashes
        return not has_slash and not has_colon
    if provider == "zai":
        # Z.AI uses simple lowercase IDs: glm-4.7-flash, glm-4.5-flash
        return not has_slash and not has_colon
    if provider in ("openai", "anthropic", "google", "generic"):
        # These use simple model IDs
        return not has_slash

    return True  # Unknown provider, assume it matches


def _normalize_model_for_provider(model: str, base_url: str, fallback_model: str = "") -> str:
    """Normalize model name to match provider format.

    If model format doesn't match provider, attempts conversion or returns fallback.
    """
    if not model or not base_url:
        return model or fallback_model

    provider = _detect_provider_type(base_url)

    # Already correct format
    if _model_matches_provider(model, provider):
        return model

    # OpenRouter format on non-OpenRouter provider → extract base model name
    if "/" in model:
        # Kyma has an explicit mapping + regex normalization path.
        if provider == "kyma":
            if model in _OPENROUTER_TO_KYMA:
                return _OPENROUTER_TO_KYMA[model]
            name = model.split("/")[-1].split(":")[0]
            # qwen3.6-plus → qwen-3.6-plus (add hyphen between letter and digit)
            name = re.sub(r"([a-zA-Z])(\d)", r"\1-\2", name)
            return name

        # For native providers (google/openai/anthropic/zai/generic), stripping
        # the OpenRouter slug yields a model name that does not exist on the
        # target provider (e.g. hermes-3-llama-3.1-405b on Gemini → 404).
        # Caller is responsible for supplying the right (base_url, api_key);
        # return the model unchanged so the mismatch surfaces upstream.
        return model

    # Non-OpenRouter format on OpenRouter → return as-is, caller should check compatibility
    if provider == "openrouter" and "/" not in model:
        return model

    return model


def _imports():
    """Lazy-resolve ConfigManager/OpenAI/LLMCache through compat hub for test mock support."""
    import services.llm_client as m
    return m.ConfigManager, m.OpenAI, m.LLMCache


class _LegacyClientAdapter:
    """Thin adapter that wraps a raw OpenAI SDK client (used in test mocks)
    so it satisfies the LLMProvider protocol without requiring a real API key."""

    _is_llm_provider = True

    def __init__(self, raw_client):
        self._raw = raw_client
        self.base_url = getattr(raw_client, "base_url", "")

    def complete(self, messages: list, model: str, temperature: float,
                 max_tokens: int, json_mode: bool = False) -> str:
        kwargs = {
            "model": model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._raw.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError("LLM returned empty content (legacy adapter)")
        return content

    def stream(self, messages: list, model: str, temperature: float,
               max_tokens: int):
        response = self._raw.chat.completions.create(
            model=model, messages=messages, temperature=temperature,
            max_tokens=max_tokens, stream=True,
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


def _get_provider(base_url: str, api_key: str):
    """Instantiate LLM provider via factory, with OpenAI SDK fallback for mocks.

    During tests, services.llm_client.OpenAI may be monkey-patched. We detect
    that by importing get_provider normally; if the providers package is
    unavailable for any reason we fall back to a raw OpenAIProvider.
    """
    from services.llm.providers import get_provider
    return get_provider(base_url=base_url, api_key=api_key)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _record_trace_call(
    *,
    model: str,
    model_tier: str,
    messages: list,
    result: str,
    duration_ms: int,
    success: bool,
    error: str = "",
) -> None:
    """Append LLMCall into active PipelineTrace. No-op if no trace is active."""
    try:
        from services.trace_context import get_trace, get_chapter, get_module, LLMCall
        from services.llm_pricing import compute_cost
    except Exception:
        return
    trace = get_trace()
    if trace is None:
        return
    try:
        chapter = get_chapter()
        module = get_module() or "unknown"
        prompt_text = "".join((m.get("content") or "") for m in messages if isinstance(m, dict))
        prompt_tokens = _estimate_tokens(prompt_text)
        completion_tokens = _estimate_tokens(result) if success else 0
        total = prompt_tokens + completion_tokens
        cost = compute_cost(model, prompt_tokens, completion_tokens)
        call = LLMCall(
            call_id=uuid.uuid4().hex[:8],
            trace_id=trace.trace_id,
            chapter_number=chapter,
            module=module,
            model=model,
            model_tier=model_tier or "primary",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_usd=cost,
            duration_ms=duration_ms,
            success=success,
            error=error,
        )
        trace.add_call(call)
        logger.info(
            "[LLM] trace=%s call=%s ch=%s mod=%s model=%s tokens=%d+%d cost=$%.4f %dms %s",
            trace.trace_id,
            call.call_id,
            chapter if chapter is not None else "-",
            module,
            model,
            prompt_tokens,
            completion_tokens,
            cost,
            duration_ms,
            "OK" if success else "ERR",
        )
    except Exception as e:
        logger.debug("Trace record failed: %s", e)


class LLMClient(StreamingMixin, GenerationMixin):
    """Client gọi LLM API thông qua provider abstraction layer."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    @classmethod
    def reset(cls):
        """Thread-safe singleton reset — use after config changes."""
        with cls._lock:
            cls._instance = None

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._provider = None
        self._last_key = ""
        self._current_model = ""
        self._client_lock = threading.Lock()
        self._providers_cache: dict = {}
        self._key_index = 0
        self._rate_limited_keys: dict[str, float] = {}
        self._rate_limited_models: dict[str, float] = {}  # "model:api_key" -> cooldown_expiry
        ConfigManager, _, LLMCache = _imports()
        try:
            config = ConfigManager()
            if config.llm.cache_enabled:
                LLMCache(ttl_days=config.llm.cache_ttl_days).evict_expired()
            # Initialize fallback manager with config thresholds
            fm = get_fallback_manager(
                max_latency_ms=getattr(config.llm, "fallback_max_latency_ms", 5000),
                max_cost_per_1k=getattr(config.llm, "fallback_max_cost_per_1k", 0.01),
            )
            fm.update_thresholds(
                max_latency_ms=getattr(config.llm, "fallback_max_latency_ms", 5000),
                max_cost_per_1k=getattr(config.llm, "fallback_max_cost_per_1k", 0.01),
            )
        except (OSError, sqlite3.Error):
            pass

    def _get_client(self):
        """Return provider for the primary configured endpoint.

        Named _get_client for backward-compat with generation.py which calls
        self._get_client() in check_connection and generate_stream.
        """
        ConfigManager, _, _ = _imports()
        config = ConfigManager()
        base_url = config.llm.base_url
        api_key = config.llm.api_key
        model = config.llm.model

        cache_key = f"{base_url}:{api_key}"
        with self._client_lock:
            if self._provider is None or self._last_key != cache_key:
                self._provider = _get_provider(base_url, api_key)
                self._last_key = cache_key
                self._current_model = model

        return self._provider

    def model_for_layer(self, layer: int) -> str:
        """Return model name for a given pipeline layer (1, 2, or 3).

        Falls back to primary model if layer-specific model not configured.
        Normalizes model name to match the primary provider format.

        For full provider info (model + base_url + api_key), use get_layer_config().
        """
        return self.get_layer_config(layer).model

    def get_layer_config(self, layer: int) -> LayerConfig:
        """Return full configuration for a pipeline layer.

        Returns LayerConfig with model, base_url, api_key for the layer.
        Falls back to primary config if layer-specific settings not configured.
        """
        ConfigManager, _, _ = _imports()
        config = ConfigManager()
        primary_model = self._current_model or config.llm.model
        primary_base_url = config.llm.base_url
        primary_api_key = config.llm.api_key

        # Layer-specific config lookup
        layer_config_map = {
            1: {
                "model": getattr(config.llm, "layer1_model", ""),
                "base_url": getattr(config.llm, "layer1_base_url", ""),
                "api_key": getattr(config.llm, "layer1_api_key", ""),
            },
            2: {
                "model": getattr(config.llm, "layer2_model", ""),
                "base_url": getattr(config.llm, "layer2_base_url", ""),
                "api_key": getattr(config.llm, "layer2_api_key", ""),
            },
        }

        layer_cfg = layer_config_map.get(layer, {})
        layer_model = layer_cfg.get("model", "")
        layer_base_url = layer_cfg.get("base_url", "")
        layer_api_key = layer_cfg.get("api_key", "")

        # Determine if this is layer-specific or falling back to primary
        is_layer_specific = bool(layer_model or layer_base_url or layer_api_key)

        # Use layer-specific or fallback to primary
        effective_model = layer_model or primary_model
        effective_base_url = layer_base_url or primary_base_url
        effective_api_key = layer_api_key or primary_api_key

        # If user set layer_model but no explicit layer_base_url/layer_api_key,
        # auto-resolve a compatible backend from their configured pools
        # (fallback_models[], api_keys[]) instead of misrouting onto the
        # primary provider. Fail loudly if nothing matches.
        if layer_model and not layer_base_url:
            primary_provider_type = _detect_provider_type(primary_base_url)
            if not _model_matches_provider(layer_model, primary_provider_type):
                resolved = self._find_backend_for_model(config, layer_model)
                if resolved is not None:
                    effective_base_url = resolved["base_url"]
                    effective_api_key = resolved["api_key"]
                else:
                    raise RuntimeError(
                        f"layer{layer}_model '{layer_model}' is not compatible "
                        f"with primary base_url '{primary_base_url}' "
                        f"(detected provider: {primary_provider_type}). "
                        f"No matching backend found in fallback_models[] or api_keys[]. "
                        f"Either (a) set layer{layer}_base_url + layer{layer}_api_key, "
                        f"(b) add a compatible entry to fallback_models, "
                        f"or (c) change layer{layer}_model to match the primary provider."
                    )

        # Normalize model name to match provider format (only converts when
        # format conversion is well-defined, e.g. OpenRouter slug → Kyma slug)
        effective_model = _normalize_model_for_provider(
            effective_model, effective_base_url, primary_model
        )

        return LayerConfig(
            model=effective_model,
            base_url=effective_base_url,
            api_key=effective_api_key,
            is_layer_specific=is_layer_specific,
        )

    def _find_backend_for_model(self, config, model: str) -> Optional[dict]:
        """Scan user's configured pools for a backend compatible with `model`.

        Priority:
        1. Exact model match in fallback_models[] (explicit routing wins).
        2. Provider-type match in fallback_models[] (same format, any entry).
        3. Provider-type match in api_keys[] (secondary keys on any base_url).
        Returns {base_url, api_key} or None.
        """
        fallbacks = getattr(config.llm, "fallback_models", []) or []

        # 1. Exact model match
        for fb in fallbacks:
            if not isinstance(fb, dict) or fb.get("enabled") is False:
                continue
            if fb.get("model") == model:
                return {
                    "base_url": fb.get("base_url", config.llm.base_url),
                    "api_key": fb.get("api_key", config.llm.api_key),
                }

        # 2. Provider-type match in fallback_models
        for fb in fallbacks:
            if not isinstance(fb, dict) or fb.get("enabled") is False:
                continue
            fb_base = fb.get("base_url", "")
            fb_ptype = _detect_provider_type(fb_base)
            if _model_matches_provider(model, fb_ptype):
                return {
                    "base_url": fb_base,
                    "api_key": fb.get("api_key", config.llm.api_key),
                }

        # 3. Provider-type match in secondary api_keys
        for item in getattr(config.llm, "api_keys", []) or []:
            if isinstance(item, dict):
                base_url = item.get("base_url", config.llm.base_url)
                api_key = item.get("key", item.get("api_key", ""))
            else:
                continue
            if _model_matches_provider(model, _detect_provider_type(base_url)):
                return {"base_url": base_url, "api_key": api_key}

        return None

    def _get_cheap_client(self):
        """Return (provider, model) for cheap/fast model tier."""
        ConfigManager, _, _ = _imports()
        config = ConfigManager()
        if not config.llm.cheap_model:
            provider = self._get_client()
            with self._client_lock:
                model = self._current_model or config.llm.model
            return provider, model

        cheap_base = config.llm.cheap_base_url or config.llm.base_url
        api_key = config.llm.api_key

        with self._client_lock:
            cache_key = f"{cheap_base}:{api_key}"
            if cache_key not in self._providers_cache:
                self._providers_cache[cache_key] = _get_provider(cheap_base, api_key)
            return self._providers_cache[cache_key], config.llm.cheap_model

    def _retry_with_backoff(self, fn, label: str = "LLM", provider: str = ""):
        """Execute fn with retry + exponential backoff.

        When ``_should_retry`` returns ``(True, 0)`` the error is
        *not* retryable on the same provider (e.g. 404 model-not-found,
        401/403 auth) but *should* be retried on the next provider in
        the fallback chain.  In that case we break immediately so the
        chain-level loop in ``generate()`` can try the next entry.
        """
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                return fn()
            except Exception as e:
                last_exc = e
                if attempt < MAX_RETRIES - 1:
                    if provider:
                        should_retry, suggested_delay = _should_retry(e, provider)
                    else:
                        should_retry = _is_transient(e)
                        suggested_delay = BASE_DELAY
                    if should_retry and suggested_delay > 0:
                        delay = max(suggested_delay, BASE_DELAY * (2 ** attempt)) + random.uniform(0, 0.5)
                        logger.warning(f"{label} attempt {attempt+1} failed: {_redact(e)}. Retry in {delay:.1f}s")
                        time.sleep(delay)
                        continue
                break
        raise last_exc

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        model_tier: str = "default",
        model: Optional[str] = None,
        budget_remaining: Optional[int] = None,
    ) -> str:
        """Call LLM with retry, cache.

        Args:
            model: Optional model override (e.g. from model_for_layer). Takes
                   precedence over config model in fallback chain.
            budget_remaining: If set, clamps effective max_tokens to this value,
                              preventing overspend on per-chapter token budgets.
        """
        ConfigManager, _, LLMCache = _imports()
        config = ConfigManager()
        effective_temp = temperature if temperature is not None else config.llm.temperature

        from services.prompts import localize_prompt
        lang = config.pipeline.language
        system_prompt = localize_prompt(system_prompt, lang)
        user_prompt = localize_prompt(user_prompt, lang)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        effective_model = config.llm.model
        use_cache = config.llm.cache_enabled and effective_temp <= 1.0
        cache = None
        cache_params = None
        if use_cache:
            cache = LLMCache(ttl_days=config.llm.cache_ttl_days)
            cache_params = dict(
                system_prompt=system_prompt, user_prompt=user_prompt,
                model=effective_model, temperature=effective_temp,
                json_mode=json_mode,
            )
            cached = cache.get(**cache_params)
            if cached is not None and cached.strip():
                return cached

        chain = self._build_fallback_chain(config, model_tier, model_override=model)
        eff_max_tokens = max_tokens or config.llm.max_tokens
        if budget_remaining is not None:
            eff_max_tokens = min(eff_max_tokens, budget_remaining)
            logger.debug("budget_remaining=%d → effective max_tokens=%d", budget_remaining, eff_max_tokens)

        # Chain-level retry config
        chain_retry_max = getattr(config.llm, "chain_retry_max", 2)
        chain_retry_base_delay = getattr(config.llm, "chain_retry_base_delay", 30.0)

        last_chain_error = None
        for chain_attempt in range(chain_retry_max + 1):
            if chain_attempt > 0:
                delay = chain_retry_base_delay * (2 ** (chain_attempt - 1)) + random.uniform(0, 5)
                logger.warning(f"Chain exhausted, retrying entire chain in {delay:.1f}s (attempt {chain_attempt + 1}/{chain_retry_max + 1})")
                time.sleep(delay)
                # Clear rate-limit state for fresh retry
                self._rate_limited_keys.clear()
                self._rate_limited_models.clear()
                chain = self._build_fallback_chain(config, model_tier, model_override=model)

            all_errors = []
            skip_keys: set[str] = set()
            account_rl_reset: float | None = None  # seconds-until-reset across all exhausted OR keys
            logger.debug(f"Fallback chain has {len(chain)} entries (chain attempt {chain_attempt + 1})")
            for entry in chain:
                entry_key = entry.get("_api_key", "")
                logger.debug(f"Trying {entry.get('label', '?')} (key: {entry_key[:12] if entry_key else 'none'}...)")
                if entry_key and entry_key in skip_keys:
                    all_errors.append(f"{entry['label']}: skipped (account rate-limited)")
                    continue
                try:
                    result = self._try_provider(
                        entry, messages, effective_temp, eff_max_tokens, json_mode
                    )
                    if use_cache and cache is not None and cache_params is not None and result.strip():
                        # Cache with actual model used (may differ from primary)
                        actual_model = entry.get("model", effective_model)
                        cache.put(result, **{**cache_params, "model": actual_model})
                    return result
                except Exception as e:
                    all_errors.append(f"{entry['label']}: {_redact(e)}")
                    pobj = entry.get("provider") or entry.get("client")
                    provider_url = getattr(pobj, "base_url", None)
                    provider_type = _detect_provider(str(provider_url) if provider_url else "")
                    should_try_next, suggested_delay = _should_retry(e, provider_type)

                    # Mark model as unhealthy for fallback manager (skip auth errors - those are config issues)
                    fm = get_fallback_manager()
                    model_name = entry.get("model", "")
                    if model_name and not _is_transient(e) and not _is_auth_error(e):
                        fm.mark_unhealthy(model_name)

                    if "_api_key" in entry:
                        err_str = str(e)
                        if "429" in err_str:
                            if provider_type == "openrouter" and self._is_account_rate_limit(err_str):
                                reset_delta = parse_openrouter_reset(err_str)
                                cooldown = reset_delta if reset_delta is not None else 300.0
                                if reset_delta is not None:
                                    account_rl_reset = min(account_rl_reset, reset_delta) if account_rl_reset else reset_delta
                                self._mark_rate_limited(entry_key, cooldown)
                                skip_keys.add(entry_key)
                                logger.warning("Account-level rate limit on key %s...%s — cooldown %.0fs, skipping remaining models",
                                               entry_key[:8], entry_key[-4:] if len(entry_key) > 8 else "", cooldown)
                            elif provider_type == "openrouter":
                                self._mark_model_rate_limited(model_name, entry_key, 90.0)
                            else:
                                self._mark_rate_limited(entry_key, suggested_delay or 60.0)
                        elif "404" in err_str and provider_type == "openrouter":
                            self._mark_model_rate_limited(model_name, entry_key, 600.0)
                    if not should_try_next and not _is_transient(e):
                        logger.error(f"FATAL: Non-retryable error from {entry.get('label', '?')}: {_redact(e)}")
                        raise
                    logger.warning(f"Provider {entry['label']} failed, trying next...")

            # Chain exhausted this attempt
            logger.debug(f"Chain exhausted. Tried {len(all_errors)} providers, skip_keys={[k[:12]+'...' for k in skip_keys]}")
            last_chain_error = (all_errors, account_rl_reset, chain)

        # All chain retries exhausted
        all_errors, account_rl_reset, chain = last_chain_error
        hint = self._build_exhaustion_hint(account_rl_reset, chain)
        error_msg = "; ".join(all_errors)
        logger.error(f"All LLM providers failed after {chain_retry_max + 1} chain attempts: {hint} | details: {error_msg}")
        raise RuntimeError(f"All LLM providers failed. {hint}")

    @staticmethod
    def _build_exhaustion_hint(reset_delta: float | None, chain: list) -> str:
        """User-facing guidance when every provider is exhausted.

        Tells the user *when* OpenRouter's free tier resets and *how* to unblock
        themselves now (add credits or plug in a non-OpenRouter provider).
        """
        only_openrouter = all(
            "openrouter" in str(getattr(e.get("provider") or e.get("client"), "base_url", "")).lower()
            for e in chain
        ) if chain else False
        parts = []
        if reset_delta is not None:
            hours = reset_delta / 3600.0
            if hours >= 1:
                parts.append(f"OpenRouter free tier resets in ~{hours:.1f}h")
            else:
                parts.append(f"OpenRouter free tier resets in ~{reset_delta/60.0:.0f}min")
        if only_openrouter:
            parts.append("To unblock now: add $10 OpenRouter credits (unlocks 1000 req/day), add more API keys in Settings > LLM, or configure a non-OpenRouter fallback (Gemini/Anthropic)")
        return " — ".join(parts) if parts else "All LLM providers failed."

    def _resolve_api_keys(self, config) -> list[dict]:
        """Build ordered list of {base_url, api_key} from primary + api_keys pool.

        Skips keys that are currently rate-limited (cooldown not expired).
        """
        now = time.time()
        entries = [{"base_url": config.llm.base_url, "api_key": config.llm.api_key}]
        for item in getattr(config.llm, "api_keys", []):
            if isinstance(item, str):
                entries.append({"base_url": config.llm.base_url, "api_key": item})
            elif isinstance(item, dict):
                entries.append({
                    "base_url": item.get("base_url", config.llm.base_url),
                    "api_key": item.get("key", item.get("api_key", "")),
                })
        result = []
        for e in entries:
            cooldown_until = self._rate_limited_keys.get(e["api_key"], 0)
            if now >= cooldown_until:
                result.append(e)
        if not result:
            self._rate_limited_keys.clear()
            result = entries
        return result

    def _mark_rate_limited(self, api_key: str, cooldown: float = 60.0):
        """Mark an API key as rate-limited for `cooldown` seconds."""
        self._rate_limited_keys[api_key] = time.time() + cooldown
        logger.warning("API key %s...%s rate-limited, cooldown %.0fs",
                       api_key[:8], api_key[-4:] if len(api_key) > 8 else "", cooldown)

    def _mark_model_rate_limited(self, model: str, api_key: str, cooldown: float = 90.0):
        """Mark a model+key combo as rate-limited."""
        combo = f"{model}:{api_key}"
        self._rate_limited_models[combo] = time.time() + cooldown
        logger.warning("Model %s rate-limited for %.0fs", model, cooldown)

    def _is_model_rate_limited(self, model: str, api_key: str) -> bool:
        combo = f"{model}:{api_key}"
        expiry = self._rate_limited_models.get(combo, 0)
        return time.time() < expiry

    @staticmethod
    def _is_account_rate_limit(err_str: str) -> bool:
        """Detect OpenRouter account-level rate limits (not model-specific)."""
        return "free-models-per-day" in err_str or "free-models-per-min" in err_str

    def _get_or_create_provider(self, base_url: str, api_key: str):
        """Get cached provider or create new one. Single lock acquisition."""
        cache_key = f"{base_url}:{api_key}"
        with self._client_lock:
            if cache_key not in self._providers_cache:
                self._providers_cache[cache_key] = _get_provider(base_url, api_key)
            return self._providers_cache[cache_key]

    @staticmethod
    def _detect_provider_type(base_url: str) -> str:
        """Detect provider type from URL. Delegates to module-level helper
        so callers get the full taxonomy (openrouter, kyma, anthropic, openai,
        google, zai, generic) — needed so `_model_matches_provider` can
        correctly reject cross-provider model slugs (e.g. OpenRouter slug on
        a Gemini base_url) instead of silently routing them to a 404.
        """
        return _detect_provider_type(base_url)

    def _can_use_model(self, model: str, api_key: str, fm, cost: float = 0.0) -> tuple[bool, str]:
        """Check if model can be used (not rate-limited, healthy, within cost)."""
        if self._is_model_rate_limited(model, api_key):
            return False, "rate_limited"
        skip, reason = fm.should_skip_model(model, cost)
        if skip:
            return False, reason
        return True, ""

    def _add_to_chain(
        self, chain: list, provider, model: str, label: str, api_key: str = ""
    ) -> None:
        """Add entry to chain."""
        entry = {"provider": provider, "model": model, "label": label}
        if api_key:
            entry["_api_key"] = api_key
        chain.append(entry)

    def _build_fallback_chain(self, config, model_tier: str, model_override: Optional[str] = None) -> list[dict]:
        chain = []
        api_key_entries = self._resolve_api_keys(config)
        fm = get_fallback_manager()

        # Resolve primary model
        default_model = self._current_model or config.llm.model
        raw_model = model_override or default_model

        # If the caller asked for a specific model that doesn't match the
        # primary provider's format (e.g. OpenRouter slug on a Gemini
        # base_url), promote the model's own backend to the front of the
        # resolve order so it's tried first. Without this, the chain would
        # skip the model entirely (format mismatch) and the caller's
        # explicit choice would be silently ignored.
        if model_override:
            primary_ptype = _detect_provider_type(config.llm.base_url)
            if not _model_matches_provider(model_override, primary_ptype):
                resolved = self._find_backend_for_model(config, model_override)
                if resolved is not None:
                    promoted = {"base_url": resolved["base_url"], "api_key": resolved["api_key"]}
                    # Deduplicate: drop existing entry with same (base_url, api_key)
                    api_key_entries = [promoted] + [
                        e for e in api_key_entries
                        if not (e.get("base_url") == promoted["base_url"]
                                and e.get("api_key") == promoted["api_key"])
                    ]

        primary_model = _normalize_model_for_provider(
            raw_model, api_key_entries[0]["base_url"] if api_key_entries else config.llm.base_url, default_model
        )

        # Detect which provider types we have
        provider_types = {self._detect_provider_type(e.get("base_url", "")) for e in api_key_entries}

        # Lazy-load model lists
        openrouter_models: list[str] = []
        kyma_models: list[str] = []
        if "openrouter" in provider_types:
            openrouter_models = self._get_openrouter_free_models(config, primary_model)
        if "kyma" in provider_types:
            kyma_models = self._get_kyma_models(config, primary_model)

        # Cheap model first if requested
        cheap_model_name = None
        if model_tier == "cheap" and config.llm.cheap_model:
            provider, cheap_model_name = self._get_cheap_client()
            self._add_to_chain(chain, provider, cheap_model_name, f"cheap:{cheap_model_name}")

        # Primary + round-robin models across all API keys
        for i, entry in enumerate(api_key_entries):
            base_url, api_key = entry["base_url"], entry["api_key"]
            prov = self._get_or_create_provider(base_url, api_key)
            key_label = "primary" if i == 0 else f"key-{i+1}"
            ptype = self._detect_provider_type(base_url)

            # Add primary model (skip if cheap tier already added it or format mismatch)
            if cheap_model_name is None and _model_matches_provider(primary_model, ptype):
                can_use, reason = self._can_use_model(primary_model, api_key, fm)
                if can_use:
                    label = f"{key_label}:{primary_model}" if model_override else key_label
                    self._add_to_chain(chain, prov, primary_model, label, api_key)
                elif reason:
                    logger.debug(f"Skipping {primary_model}: {reason}")

            # Round-robin for OpenRouter/Kyma
            if ptype in ("openrouter", "kyma"):
                models = kyma_models if ptype == "kyma" else openrouter_models
                for model_name in models:
                    if model_name in (primary_model, cheap_model_name):
                        continue
                    can_use, reason = self._can_use_model(model_name, api_key, fm)
                    if can_use:
                        self._add_to_chain(chain, prov, model_name, f"{key_label}:rr:{model_name}", api_key)
                    elif reason:
                        logger.debug(f"Skipping {model_name}: {reason}")

        # Cheap model as fallback (if not already first)
        if model_tier != "cheap" and config.llm.cheap_model:
            provider, model = self._get_cheap_client()
            self._add_to_chain(chain, provider, model, f"cheap:{model}")

        # Configured fallback models
        existing_combos = {(c["model"], c.get("_api_key", "")) for c in chain}
        for fb in getattr(config.llm, 'fallback_models', []):
            fb_model = fb.get("model", "")
            if not fb_model or fb.get("enabled") is False:
                continue

            fb_base = fb.get("base_url", config.llm.base_url)
            fb_key = fb.get("api_key", config.llm.api_key)
            fb_cost = fb.get("cost_per_1k", 0.0)
            fb_prov = self._get_or_create_provider(fb_base, fb_key)
            ptype = self._detect_provider_type(fb_base)

            # Add configured fallback model
            if (fb_model, fb_key) not in existing_combos:
                can_use, reason = self._can_use_model(fb_model, fb_key, fm, fb_cost)
                if can_use:
                    self._add_to_chain(chain, fb_prov, fb_model, f"fallback:{fb_model}", fb_key)
                    existing_combos.add((fb_model, fb_key))
                elif reason:
                    logger.warning(f"Skipping fallback {fb_model}: {reason}")
                    # Clear health if unhealthy so next request retries
                    if "unhealthy" in reason:
                        fm.clear_model_health(fb_model)

            # Round-robin on fallback OpenRouter/Kyma keys
            if ptype in ("openrouter", "kyma"):
                # Lazy-load if needed
                if ptype == "kyma" and not kyma_models:
                    kyma_models = self._get_kyma_models(config, primary_model)
                elif ptype == "openrouter" and not openrouter_models:
                    openrouter_models = self._get_openrouter_free_models(config, primary_model)

                models = kyma_models if ptype == "kyma" else openrouter_models
                for model_name in models:
                    if (model_name, fb_key) in existing_combos:
                        continue
                    can_use, reason = self._can_use_model(model_name, fb_key, fm)
                    if can_use:
                        self._add_to_chain(chain, fb_prov, model_name, f"fallback:rr:{model_name}", fb_key)
                        existing_combos.add((model_name, fb_key))
                    elif reason:
                        logger.warning(f"Skipping fallback:rr:{model_name}: {reason}")

        # Auto-add Z.AI from environment if available and not already in chain
        import os
        zai_key = os.environ.get("ZAI_API_KEY", "")
        if zai_key and not any(
            self._detect_provider_type(e.get("base_url", "")) == "zai"
            for e in api_key_entries
        ):
            zai_base = "https://api.z.ai/api/paas/v4"
            zai_prov = self._get_or_create_provider(zai_base, zai_key)
            zai_models = ["glm-4.7-flash", "glm-4.5-flash"]
            for m in zai_models:
                if (m, zai_key) not in existing_combos:
                    can_use, reason = self._can_use_model(m, zai_key, fm)
                    if can_use:
                        self._add_to_chain(chain, zai_prov, m, f"zai:{m}", zai_key)
                        existing_combos.add((m, zai_key))
                        logger.debug(f"Auto-added Z.AI fallback: {m}")

        return chain

    def _get_openrouter_free_models(self, config, primary_model: str) -> list[str]:
        """Get all free OpenRouter models, primary first."""
        try:
            from services.openrouter_model_discovery import get_free_models
            api_key = config.llm.api_key
            models = get_free_models(api_key=api_key)
            # Primary model first, then the rest
            ordered = []
            if primary_model in models:
                ordered.append(primary_model)
            for m in models:
                if m != primary_model:
                    ordered.append(m)
            return ordered
        except Exception as e:
            logger.warning("Failed to fetch free models for round-robin: %s", e)
            return []

    def _get_kyma_models(self, config, primary_model: str) -> list[str]:
        """Get all Kyma models, primary first."""
        try:
            from services.kyma_model_discovery import get_kyma_models
            api_key = config.llm.api_key
            models = get_kyma_models(api_key=api_key)
            ordered = []
            if primary_model in models:
                ordered.append(primary_model)
            for m in models:
                if m != primary_model:
                    ordered.append(m)
            return ordered
        except Exception as e:
            logger.warning("Failed to fetch Kyma models for round-robin: %s", e)
            return []

    def _try_provider(self, entry: dict, messages: list, temperature: float,
                      max_tokens: int, json_mode: bool) -> str:
        # Support legacy {"client": ..., "model": ...} entries (test mocks use this form)
        if "client" in entry and "provider" not in entry:
            raw_client = entry["client"]
            # Wrap raw OpenAI client in a thin adapter so existing mock tests pass
            provider = _LegacyClientAdapter(raw_client)
        else:
            provider = entry["provider"]
        model = entry["model"]
        provider_url = getattr(provider, "base_url", None)
        provider_type = _detect_provider(str(provider_url) if provider_url else "")
        # Tier label for trace: "cheap" / "fallback" / "primary" / ...
        tier_label = entry.get("label", "").split(":", 1)[0] or "primary"

        def _call():
            start_time = time.monotonic()
            try:
                result = provider.complete(messages, model, temperature, max_tokens, json_mode)
                latency_ms = (time.monotonic() - start_time) * 1000

                # Track latency for fallback decisions
                fm = get_fallback_manager()
                fm.record_latency(model, latency_ms)
                fm.mark_healthy(model)

                logger.info(f"LLM success via {entry['label']} ({latency_ms:.0f}ms)")
                _record_trace_call(
                    model=model, model_tier=tier_label, messages=messages, result=result,
                    duration_ms=int(latency_ms), success=True, error="",
                )
                return result
            except Exception as exc:
                latency_ms = (time.monotonic() - start_time) * 1000
                _record_trace_call(
                    model=model, model_tier=tier_label, messages=messages, result="",
                    duration_ms=int(latency_ms), success=False, error=str(exc)[:200],
                )
                raise

        return self._retry_with_backoff(
            _call, label=f"Provider {entry['label']}", provider=provider_type
        )

    async def agenerate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        model_tier: str = "default",
        model: Optional[str] = None,
        budget_remaining: Optional[int] = None,
    ) -> str:
        """Async wrapper around generate() — offloads blocking I/O to thread pool.

        Signature mirrors generate() exactly so callers can migrate by replacing
        `self.llm.generate(...)` with `await self.llm.agenerate(...)`.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
                model_tier=model_tier,
                model=model,
                budget_remaining=budget_remaining,
            ),
        )

    async def agenerate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model_tier: str = "default",
        model: Optional[str] = None,
    ) -> dict:
        """Async wrapper around generate_json() — offloads blocking I/O to thread pool.

        Signature mirrors generate_json() exactly so callers can migrate by replacing
        `self.llm.generate_json(...)` with `await self.llm.agenerate_json(...)`.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                model_tier=model_tier,
                model=model,
            ),
        )

    def generate_for_layer(
        self,
        layer: int,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        budget_remaining: Optional[int] = None,
    ) -> str:
        """Generate using layer-specific provider configuration.

        If layer has specific base_url/api_key configured, prepends that provider
        to the fallback chain. Otherwise, uses standard generate() with layer model.

        Args:
            layer: Pipeline layer (1 for story gen, 2 for drama analysis)
            Other args same as generate()
        """
        layer_cfg = self.get_layer_config(layer)

        if layer_cfg.is_layer_specific:
            # Layer has dedicated provider — prepend to fallback chain
            ConfigManager, _, LLMCache = _imports()
            config = ConfigManager()
            effective_temp = temperature if temperature is not None else config.llm.temperature
            eff_max_tokens = max_tokens or config.llm.max_tokens
            if budget_remaining is not None:
                eff_max_tokens = min(eff_max_tokens, budget_remaining)

            from services.prompts import localize_prompt
            lang = config.pipeline.language
            system_prompt = localize_prompt(system_prompt, lang)
            user_prompt = localize_prompt(user_prompt, lang)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            # Build chain: layer provider first, then standard fallback chain
            layer_provider = self._get_or_create_provider(layer_cfg.base_url, layer_cfg.api_key)
            layer_entry = {
                "provider": layer_provider,
                "model": layer_cfg.model,
                "label": f"layer{layer}:{layer_cfg.model}",
                "_api_key": layer_cfg.api_key,
            }

            # Standard fallback chain as backup
            fallback_chain = self._build_fallback_chain(config, "default", model_override=None)

            # Full chain: layer-specific first, then fallbacks
            chain = [layer_entry] + fallback_chain

            # Use same retry logic as generate()
            from services.llm.retry import _redact, _detect_provider, _should_retry, _is_transient, _is_auth_error, parse_openrouter_reset

            all_errors = []
            skip_keys: set[str] = set()
            account_rl_reset: float | None = None
            fm = get_fallback_manager()

            for entry in chain:
                entry_key = entry.get("_api_key", "")
                if entry_key and entry_key in skip_keys:
                    all_errors.append(f"{entry['label']}: skipped (account rate-limited)")
                    continue
                try:
                    return self._try_provider(entry, messages, effective_temp, eff_max_tokens, json_mode)
                except Exception as e:
                    all_errors.append(f"{entry['label']}: {_redact(e)}")
                    pobj = entry.get("provider")
                    provider_url = getattr(pobj, "base_url", None)
                    provider_type = _detect_provider(str(provider_url) if provider_url else "")
                    should_try_next, suggested_delay = _should_retry(e, provider_type)

                    model_name = entry.get("model", "")
                    if model_name and not _is_transient(e) and not _is_auth_error(e):
                        fm.mark_unhealthy(model_name)

                    if entry_key:
                        err_str = str(e)
                        if "429" in err_str:
                            if provider_type == "openrouter" and self._is_account_rate_limit(err_str):
                                reset_delta = parse_openrouter_reset(err_str)
                                cooldown = reset_delta if reset_delta is not None else 300.0
                                if reset_delta is not None:
                                    account_rl_reset = min(account_rl_reset, reset_delta) if account_rl_reset else reset_delta
                                self._mark_rate_limited(entry_key, cooldown)
                                skip_keys.add(entry_key)
                            elif provider_type == "openrouter":
                                self._mark_model_rate_limited(model_name, entry_key, 90.0)
                            else:
                                self._mark_rate_limited(entry_key, suggested_delay or 60.0)
                        elif "404" in err_str and provider_type == "openrouter":
                            self._mark_model_rate_limited(model_name, entry_key, 600.0)

                    if not should_try_next and not _is_transient(e):
                        raise
                    logger.warning(f"Provider {entry['label']} failed, trying next...")

            hint = self._build_exhaustion_hint(account_rl_reset, chain)
            error_msg = "; ".join(all_errors)
            logger.error(f"All LLM providers failed for layer {layer}: {hint} | details: {error_msg}")
            raise RuntimeError(f"All LLM providers failed for layer {layer}. {hint}")

        # No layer-specific provider — use standard generate with model override
        return self.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            model=layer_cfg.model,
            budget_remaining=budget_remaining,
        )

    async def agenerate_for_layer(
        self,
        layer: int,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        budget_remaining: Optional[int] = None,
    ) -> str:
        """Async wrapper around generate_for_layer()."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate_for_layer(
                layer=layer,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
                budget_remaining=budget_remaining,
            ),
        )

    @staticmethod
    def _repair_json(text: str) -> str:
        """Backward-compat static method — delegates to generation module."""
        from services.llm.generation import _repair_json
        return _repair_json(text)
