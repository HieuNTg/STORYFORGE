"""LLMClient — singleton LLM caller with dual-backend routing, retry, and cache."""

import logging
import random
import sqlite3
import time
import threading
from typing import Optional
from services.llm.retry import (
    MAX_RETRIES, BASE_DELAY,
    WebBackendExhausted,
    _redact, _is_transient, _detect_provider, _should_retry,
)
from services.llm.streaming import StreamingMixin
from services.llm.generation import GenerationMixin

logger = logging.getLogger(__name__)


def _imports():
    """Lazy-resolve ConfigManager/OpenAI/LLMCache through compat hub for test mock support."""
    import services.llm_client as m
    return m.ConfigManager, m.OpenAI, m.LLMCache


class LLMClient(StreamingMixin, GenerationMixin):
    """Client gọi LLM API thông qua OpenAI-compatible endpoint."""

    _instance = None
    _lock = threading.Lock()

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
        self._client = None
        self._last_key = ""
        self._current_model = ""
        self._client_lock = threading.Lock()
        self._clients_cache: dict = {}
        ConfigManager, _, LLMCache = _imports()
        try:
            config = ConfigManager()
            if config.llm.cache_enabled:
                LLMCache(ttl_days=config.llm.cache_ttl_days).evict_expired()
        except (OSError, sqlite3.Error):
            pass

    def _get_client(self):
        ConfigManager, OpenAI, _ = _imports()
        config = ConfigManager()
        base_url = config.llm.base_url
        api_key = config.llm.api_key
        model = config.llm.model

        cache_key = f"{base_url}:{api_key}"
        with self._client_lock:
            if self._client is None or self._last_key != cache_key:
                self._client = OpenAI(api_key=api_key, base_url=base_url)
                self._last_key = cache_key
                self._current_model = model

        return self._client

    def _is_web_backend(self) -> bool:
        ConfigManager, _, _ = _imports()
        return ConfigManager().llm.backend_type == "web"

    def _get_web_client(self):
        from services.deepseek_web_client import DeepSeekWebClient
        if not hasattr(self, "_web_client") or self._web_client is None:
            self._web_client = DeepSeekWebClient()
        return self._web_client

    def _get_cheap_client(self):
        ConfigManager, OpenAI, _ = _imports()
        config = ConfigManager()
        if not config.llm.cheap_model:
            client = self._get_client()
            with self._client_lock:
                model = self._current_model or config.llm.model
            return client, model

        cheap_base = config.llm.cheap_base_url or config.llm.base_url
        api_key = config.llm.api_key

        with self._client_lock:
            cache_key = f"{cheap_base}:{api_key}"
            if cache_key not in self._clients_cache:
                self._clients_cache[cache_key] = OpenAI(api_key=api_key, base_url=cheap_base)
            return self._clients_cache[cache_key], config.llm.cheap_model

    def _retry_with_backoff(self, fn, label: str = "LLM", provider: str = ""):
        """Execute fn with retry + exponential backoff."""
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
                    if should_retry:
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
    ) -> str:
        """Call LLM with retry, cache. Supports API and web (browser auth) backend."""
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

        effective_model = config.llm.model if not self._is_web_backend() else "deepseek-web"
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

        if self._is_web_backend():
            try:
                result = self._generate_web(messages, effective_temp, use_cache, cache, cache_params)
                return result
            except WebBackendExhausted as e:
                logger.warning(f"Web backend exhausted, falling back to API chain: {e}")

        chain = self._build_fallback_chain(config, model_tier)
        eff_max_tokens = max_tokens or config.llm.max_tokens

        all_errors = []
        for provider in chain:
            try:
                result = self._try_provider(
                    provider, messages, effective_temp, eff_max_tokens, json_mode
                )
                if use_cache and cache is not None and cache_params is not None:
                    cache.put(result, **cache_params)
                return result
            except Exception as e:
                all_errors.append(f"{provider['label']}: {_redact(e)}")
                base_url = getattr(provider["client"], "base_url", None)
                provider_type = _detect_provider(str(base_url) if base_url else "")
                should_try_next, _ = _should_retry(e, provider_type)
                if not should_try_next and not _is_transient(e):
                    raise
                logger.warning(f"Provider {provider['label']} failed, trying next...")

        error_msg = "; ".join(all_errors)
        logger.error(f"All LLM providers failed: {error_msg}")
        raise RuntimeError(f"All LLM providers failed: {error_msg}")

    def _build_fallback_chain(self, config, model_tier: str) -> list[dict]:
        _, OpenAI, _ = _imports()
        chain = []
        if model_tier == "cheap" and config.llm.cheap_model:
            client, model = self._get_cheap_client()
            chain.append({"client": client, "model": model, "label": f"cheap:{model}"})
        else:
            chain.append({
                "client": self._get_client(),
                "model": self._current_model or config.llm.model,
                "label": "primary",
            })
        if model_tier != "cheap" and config.llm.cheap_model:
            client, model = self._get_cheap_client()
            chain.append({"client": client, "model": model, "label": f"cheap:{model}"})
        for fb in getattr(config.llm, 'fallback_models', []):
            fb_model = fb.get("model", "")
            if not fb_model:
                continue
            fb_base = fb.get("base_url", config.llm.base_url)
            fb_key = fb.get("api_key", config.llm.api_key)
            cache_key = f"{fb_base}:{fb_key}"
            with self._client_lock:
                if cache_key not in self._clients_cache:
                    self._clients_cache[cache_key] = OpenAI(api_key=fb_key, base_url=fb_base)
                chain.append({"client": self._clients_cache[cache_key], "model": fb_model, "label": f"fallback:{fb_model}"})
        return chain

    def _try_provider(self, provider: dict, messages: list, temperature: float,
                      max_tokens: int, json_mode: bool) -> str:
        kwargs = {
            "model": provider["model"], "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        base_url = getattr(provider["client"], "base_url", None)
        provider_type = _detect_provider(str(base_url) if base_url else "")

        def _call():
            response = provider["client"].chat.completions.create(**kwargs)
            result = response.choices[0].message.content or ""
            logger.info(f"LLM success via {provider['label']}")
            return result

        return self._retry_with_backoff(
            _call, label=f"Provider {provider['label']}", provider=provider_type
        )

    def _generate_web(self, messages, temperature, use_cache, cache, cache_params) -> str:
        def _call():
            web_client = self._get_web_client()
            return web_client.chat_completion_sync(messages=messages, temperature=temperature)

        try:
            result = self._retry_with_backoff(_call, label="Web LLM")
            if use_cache and cache is not None and cache_params is not None:
                cache.put(result, **cache_params)
            return result
        except Exception as e:
            logger.error(f"Web LLM failed after {MAX_RETRIES} attempts: {_redact(e)}")
            raise WebBackendExhausted(str(e)) from e

    @staticmethod
    def _repair_json(text: str) -> str:
        """Backward-compat static method — delegates to generation module."""
        from services.llm.generation import _repair_json
        return _repair_json(text)
