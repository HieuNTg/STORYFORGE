"""LLMClient — singleton LLM caller with retry and cache."""

import logging
import random
import sqlite3
import time
import threading
from typing import Optional
from services.llm.retry import (
    MAX_RETRIES, BASE_DELAY,
    _redact, _is_transient, _detect_provider, _should_retry,
)
from services.llm.streaming import StreamingMixin
from services.llm.generation import GenerationMixin

logger = logging.getLogger(__name__)


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
        return response.choices[0].message.content or ""

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
        ConfigManager, _, LLMCache = _imports()
        try:
            config = ConfigManager()
            if config.llm.cache_enabled:
                LLMCache(ttl_days=config.llm.cache_ttl_days).evict_expired()
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
        """
        ConfigManager, _, _ = _imports()
        config = ConfigManager()
        layer_map = {
            1: config.llm.layer1_model,
            2: config.llm.layer2_model,
        }
        layer_model = layer_map.get(layer, "")
        return layer_model or self._current_model or config.llm.model

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
            if cached is not None:
                return cached

        chain = self._build_fallback_chain(config, model_tier, model_override=model)
        eff_max_tokens = max_tokens or config.llm.max_tokens
        if budget_remaining is not None:
            eff_max_tokens = min(eff_max_tokens, budget_remaining)
            logger.debug("budget_remaining=%d → effective max_tokens=%d", budget_remaining, eff_max_tokens)

        all_errors = []
        for entry in chain:
            try:
                result = self._try_provider(
                    entry, messages, effective_temp, eff_max_tokens, json_mode
                )
                if use_cache and cache is not None and cache_params is not None:
                    cache.put(result, **cache_params)
                return result
            except Exception as e:
                all_errors.append(f"{entry['label']}: {_redact(e)}")
                pobj = entry.get("provider") or entry.get("client")
                provider_url = getattr(pobj, "base_url", None)
                provider_type = _detect_provider(str(provider_url) if provider_url else "")
                should_try_next, suggested_delay = _should_retry(e, provider_type)
                if "429" in str(e) and "_api_key" in entry:
                    self._mark_rate_limited(entry["_api_key"], suggested_delay or 60.0)
                if not should_try_next and not _is_transient(e):
                    raise
                logger.warning(f"Provider {entry['label']} failed, trying next...")

        error_msg = "; ".join(all_errors)
        logger.error(f"All LLM providers failed: {error_msg}")
        raise RuntimeError(f"All LLM providers failed: {error_msg}")

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

    def _build_fallback_chain(self, config, model_tier: str, model_override: Optional[str] = None) -> list[dict]:
        chain = []
        if model_tier == "cheap" and config.llm.cheap_model:
            provider, model = self._get_cheap_client()
            chain.append({"provider": provider, "model": model, "label": f"cheap:{model}"})
        else:
            primary_model = model_override or self._current_model or config.llm.model
            api_key_entries = self._resolve_api_keys(config)
            for i, entry in enumerate(api_key_entries):
                cache_key = f"{entry['base_url']}:{entry['api_key']}"
                with self._client_lock:
                    if cache_key not in self._providers_cache:
                        self._providers_cache[cache_key] = _get_provider(
                            entry["base_url"], entry["api_key"]
                        )
                label = "primary" if i == 0 else f"key-{i+1}"
                if model_override:
                    label = f"{label}:{primary_model}"
                chain.append({
                    "provider": self._providers_cache[cache_key],
                    "model": primary_model,
                    "label": label,
                    "_api_key": entry["api_key"],
                })
        if model_tier != "cheap" and config.llm.cheap_model:
            provider, model = self._get_cheap_client()
            chain.append({"provider": provider, "model": model, "label": f"cheap:{model}"})
        for fb in getattr(config.llm, 'fallback_models', []):
            fb_model = fb.get("model", "")
            if not fb_model or fb.get("enabled") is False:
                continue
            fb_base = fb.get("base_url", config.llm.base_url)
            fb_key = fb.get("api_key", config.llm.api_key)
            cache_key = f"{fb_base}:{fb_key}"
            with self._client_lock:
                if cache_key not in self._providers_cache:
                    self._providers_cache[cache_key] = _get_provider(fb_base, fb_key)
                chain.append({
                    "provider": self._providers_cache[cache_key],
                    "model": fb_model,
                    "label": f"fallback:{fb_model}",
                })
        return chain

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

        def _call():
            result = provider.complete(messages, model, temperature, max_tokens, json_mode)
            logger.info(f"LLM success via {entry['label']}")
            return result

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

    @staticmethod
    def _repair_json(text: str) -> str:
        """Backward-compat static method — delegates to generation module."""
        from services.llm.generation import _repair_json
        return _repair_json(text)
