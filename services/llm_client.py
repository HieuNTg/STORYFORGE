"""Client giao tiếp với LLM API."""

import json
import logging
import re
import sqlite3
import time
import random
import threading
from typing import Optional
from openai import OpenAI
from config import ConfigManager
from services.llm_cache import LLMCache

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_DELAY = 1.0

# Patterns that may expose credentials in error messages
_REDACT_PATTERNS = re.compile(
    r'((?:Authorization|Bearer|api[_-]?key|x-api-key)\s*[:=]\s*)'
    r'([A-Za-z0-9\-_.~+/]{8,})',
    re.IGNORECASE,
)


def _redact(message: str) -> str:
    """Strip API keys, bearer tokens, and auth headers from a string before logging."""
    return _REDACT_PATTERNS.sub(r'\1[REDACTED]', str(message))


class WebBackendExhausted(Exception):
    """All web backend attempts failed."""
    pass

# Transient error indicators
_TRANSIENT_CODES = {429, 500, 502, 503, 504}


def _is_transient(exc: Exception) -> bool:
    """Check if exception is transient (worth retrying)."""
    exc_str = str(exc).lower()
    if any(str(code) in exc_str for code in _TRANSIENT_CODES):
        return True
    if any(kw in exc_str for kw in ("timeout", "connection", "reset", "broken pipe")):
        return True
    return False


def _detect_provider(base_url: str) -> str:
    """Detect LLM provider from base URL."""
    if not base_url:
        return "openai"
    url = base_url.lower()
    if "openrouter" in url:
        return "openrouter"
    if "localhost" in url or "127.0.0.1" in url or "ollama" in url:
        return "ollama"
    if "anthropic" in url:
        return "anthropic"
    if "gemini" in url or "googleapis" in url:
        return "google"
    if "api.openai.com" in url:
        return "openai"
    return "custom"


def _parse_retry_after(exc: Exception) -> float | None:
    """Extract Retry-After delay from HTTP error response, if available."""
    # httpx/requests exceptions often embed the response
    resp = getattr(exc, "response", None)
    if resp is not None:
        header = getattr(resp, "headers", {}).get("retry-after") or getattr(resp, "headers", {}).get("Retry-After")
        if header:
            try:
                return float(header)
            except ValueError:
                pass
    return None


def _should_retry(exc: Exception, provider: str) -> tuple[bool, float]:
    """Decide if error is retryable and suggest delay.

    Returns: (should_retry, delay_seconds)
    """
    exc_str = str(exc).lower()

    # Ollama: model not loaded = unrecoverable
    if provider == "ollama" and ("model" in exc_str and ("not found" in exc_str or "not loaded" in exc_str)):
        return False, 0

    # OpenAI: org quota exceeded = unrecoverable
    if provider == "openai" and "quota" in exc_str and "exceeded" in exc_str:
        return False, 0

    # 429 rate limit — use Retry-After header if available, else provider defaults
    if "429" in exc_str:
        retry_after = _parse_retry_after(exc)
        if retry_after is not None:
            return True, retry_after
        if provider == "openrouter":
            return True, 60.0  # OpenRouter needs longer backoff
        return True, 5.0  # Default rate limit delay

    # Standard transient errors
    if _is_transient(exc):
        return True, BASE_DELAY

    return False, 0


class LLMClient:
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
        # Cache OpenAI clients by base_url for model routing
        self._clients_cache: dict[str, OpenAI] = {}
        # Evict expired cache entries on startup
        try:
            config = ConfigManager()
            if config.llm.cache_enabled:
                LLMCache(ttl_days=config.llm.cache_ttl_days).evict_expired()
        except (OSError, sqlite3.Error):
            pass

    def _get_client(self) -> OpenAI:
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
        """Check if currently using web (browser auth) backend."""
        return ConfigManager().llm.backend_type == "web"

    def _get_web_client(self):
        """Get DeepSeekWebClient for web backend. Lazy import."""
        from services.deepseek_web_client import DeepSeekWebClient
        if not hasattr(self, "_web_client") or self._web_client is None:
            self._web_client = DeepSeekWebClient()
        return self._web_client

    def _get_cheap_client(self) -> tuple[OpenAI, str]:
        """Get client and model for cheap tier. Returns (client, model_name)."""
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
        """Execute fn with retry + exponential backoff. Returns result or raises last exception."""
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

    def _stream_with_retry(self, gen_factory, label: str = "stream"):
        """Issue #2: retry wrapper for streaming generators.

        Only retries if no chunks were yielded yet (H1 fix: prevents
        duplicate output when failure occurs mid-stream).
        """
        last_exc = None
        chunks_yielded = 0
        for attempt in range(MAX_RETRIES):
            try:
                for chunk in gen_factory():
                    chunks_yielded += 1
                    yield chunk
                return
            except Exception as e:
                last_exc = e
                if chunks_yielded > 0:
                    # Mid-stream failure — cannot safely retry without duplication
                    logger.error(f"{label} failed after {chunks_yielded} chunks: {_redact(e)}")
                    raise
                if attempt < MAX_RETRIES - 1 and _is_transient(e):
                    delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning(f"{label} attempt {attempt+1} failed: {_redact(e)}. Retry in {delay:.1f}s")
                    time.sleep(delay)
                    continue
                break
        logger.error(f"{label} failed after {MAX_RETRIES} attempts: {_redact(last_exc)}")
        raise last_exc

    def _stream_with_chunk_timeout(self, source_gen, chunk_timeout: int = 60):
        """Wrap a streaming generator with a per-chunk timeout.

        Raises TimeoutError if no chunk is received within `chunk_timeout` seconds.
        Uses a background thread + queue to enforce the deadline without stalling
        the caller on blocked I/O indefinitely.
        """
        import queue as _queue

        _SENTINEL = object()
        chunk_queue: _queue.Queue = _queue.Queue()

        def _producer():
            try:
                for chunk in source_gen:
                    chunk_queue.put(chunk)
            except Exception as exc:
                chunk_queue.put(exc)
            finally:
                chunk_queue.put(_SENTINEL)

        producer_thread = threading.Thread(target=_producer, daemon=True)
        producer_thread.start()

        while True:
            try:
                item = chunk_queue.get(timeout=chunk_timeout)
            except _queue.Empty:
                logger.error(
                    f"Stream chunk timeout: no data received in {chunk_timeout}s"
                )
                raise TimeoutError(
                    f"Streaming response stalled — no chunk received within {chunk_timeout}s"
                )
            if item is _SENTINEL:
                return
            if isinstance(item, Exception):
                raise item
            yield item

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        model_tier: str = "default",
    ) -> str:
        """Gọi LLM với retry, cache. Hỗ trợ API và web (browser auth) backend."""
        config = ConfigManager()
        effective_temp = temperature if temperature is not None else config.llm.temperature

        # Localize prompts for non-Vietnamese languages
        from services.prompts import localize_prompt
        lang = config.pipeline.language
        system_prompt = localize_prompt(system_prompt, lang)
        user_prompt = localize_prompt(user_prompt, lang)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Cache check (only for deterministic calls)
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

        # Route to web backend (DeepSeek browser auth)
        if self._is_web_backend():
            try:
                result = self._generate_web(messages, effective_temp, use_cache, cache, cache_params)
                return result
            except WebBackendExhausted as e:
                logger.warning(f"Web backend exhausted, falling back to API chain: {e}")

        # API backend — build provider chain and try each
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
                # Use provider-aware retry decision for fallback chain traversal
                base_url = getattr(provider["client"], "base_url", None)
                provider_type = _detect_provider(str(base_url) if base_url else "")
                should_try_next, _ = _should_retry(e, provider_type)
                if not should_try_next and not _is_transient(e):
                    raise  # unrecoverable — don't try fallbacks
                logger.warning(f"Provider {provider['label']} failed, trying next...")

        error_msg = "; ".join(all_errors)
        logger.error(f"All LLM providers failed: {error_msg}")
        raise RuntimeError(f"All LLM providers failed: {error_msg}")

    def _build_fallback_chain(self, config, model_tier: str) -> list[dict]:
        """Build ordered list of providers to try: primary → cheap → fallbacks."""
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
        # Add cheap as fallback if not already primary
        if model_tier != "cheap" and config.llm.cheap_model:
            client, model = self._get_cheap_client()
            chain.append({"client": client, "model": model, "label": f"cheap:{model}"})
        # Add configured fallback models
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

        # Detect provider type for smarter retry decisions
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

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model_tier: str = "default",
    ) -> dict:
        """Gọi LLM và parse kết quả JSON với auto-repair."""
        result = self.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            model_tier=model_tier,
        )
        text = result.strip()
        # Strip markdown code block
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        # Attempt 1: direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed, attempting repair: {e}")

        # Attempt 2: repair common issues
        repaired = self._repair_json(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Attempt 3: ask LLM to fix (use cheap model)
        logger.warning("JSON repair failed, asking LLM to fix")
        fixed = self.generate(
            system_prompt="Fix this malformed JSON. Return ONLY valid JSON, no explanation.",
            user_prompt=text[:4000],
            temperature=0.0,
            json_mode=True,
            model_tier="cheap",
        )
        # Re-raise with full diagnostic on final parse failure
        try:
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            preview = fixed[:800] if fixed else "<empty>"
            raise ValueError(
                f"JSON parse failed after 3 attempts. "
                f"Parse error: {e}. "
                f"Last text ({len(fixed)} chars, showing first 800): {preview!r}"
            ) from e

    @staticmethod
    def _repair_json(text: str) -> str:
        """Fix common JSON issues."""
        # Remove trailing commas before } or ]
        text = re.sub(r',\s*([}\]])', r'\1', text)
        # Single-quoted JSON keys/values to double quotes (avoid corrupting apostrophes in values)
        text = re.sub(r"(?<=[\[{,:])\s*'([^']*?)'\s*(?=[,}\]:])", r' "\1" ', text)
        # Extract JSON object/array from surrounding text
        starts = [text.find(c) for c in ('{', '[') if text.find(c) >= 0]
        ends = [text.rfind(c) for c in ('}', ']') if text.rfind(c) >= 0]
        if starts and ends:
            return text[min(starts):max(ends) + 1]
        return text

    def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model_tier: str = "default",
    ):
        """Gọi LLM với streaming. Hỗ trợ API và web backend."""
        config = ConfigManager()
        effective_temp = temperature if temperature is not None else config.llm.temperature

        # Localize prompts for non-Vietnamese languages
        from services.prompts import localize_prompt
        lang = config.pipeline.language
        system_prompt = localize_prompt(system_prompt, lang)
        user_prompt = localize_prompt(user_prompt, lang)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Web backend streaming — use _stream_with_retry + chunk timeout
        if self._is_web_backend():
            def _web_gen():
                web_client = self._get_web_client()
                yield from web_client.chat_completion(
                    messages=messages, temperature=effective_temp, stream=True,
                )
            yield from self._stream_with_chunk_timeout(
                self._stream_with_retry(_web_gen, "Web stream"), chunk_timeout=60
            )
            return

        # API backend streaming
        if model_tier == "cheap" and config.llm.cheap_model:
            client, effective_model = self._get_cheap_client()
        else:
            client = self._get_client()
            effective_model = self._current_model or config.llm.model

        kwargs = {
            "model": effective_model,
            "messages": messages,
            "temperature": effective_temp,
            "max_tokens": max_tokens or config.llm.max_tokens,
            "stream": True,
        }

        # use _stream_with_retry + chunk timeout for API path
        def _api_gen():
            response = client.chat.completions.create(**kwargs)
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        yield from self._stream_with_chunk_timeout(
            self._stream_with_retry(_api_gen, "API stream"), chunk_timeout=60
        )

    def check_connection(self) -> tuple[bool, str]:
        """Kiểm tra kết nối backend (API hoặc web)."""
        if self._is_web_backend():
            try:
                web_client = self._get_web_client()
                return web_client.check_connection()
            except Exception as e:
                return False, f"Lỗi web backend: {e}"

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._current_model or ConfigManager().llm.model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5,
            )
            return True, "Kết nối thành công"
        except Exception as e:
            return False, f"Lỗi kết nối: {str(e)}"
