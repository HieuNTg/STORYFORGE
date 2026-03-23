"""Client giao tiếp với LLM API."""

import json
import logging
import re
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
        except Exception:
            pass

    def _get_client(self) -> OpenAI:
        config = ConfigManager()
        if config.llm.backend_type == "openclaw":
            base_url = f"http://localhost:{config.llm.openclaw_port}/v1"
            api_key = "openclaw-token"
            model = config.llm.openclaw_model
        else:
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

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        model_tier: str = "default",
    ) -> str:
        """Gọi LLM với retry, cache, và fallback."""
        config = ConfigManager()

        # Resolve client and model based on tier
        if model_tier == "cheap" and config.llm.cheap_model:
            client, effective_model = self._get_cheap_client()
        else:
            client = self._get_client()
            effective_model = self._current_model or config.llm.model

        effective_temp = temperature if temperature is not None else config.llm.temperature

        kwargs = {
            "model": effective_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": effective_temp,
            "max_tokens": max_tokens or config.llm.max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        # Cache check (only for deterministic calls)
        use_cache = config.llm.cache_enabled and effective_temp <= 0.7
        cache = None
        cache_params = None
        if use_cache:
            cache = LLMCache(ttl_days=config.llm.cache_ttl_days)
            cache_params = dict(
                system_prompt=system_prompt, user_prompt=user_prompt,
                model=kwargs["model"], temperature=effective_temp,
                json_mode=json_mode,
            )
            cached = cache.get(**cache_params)
            if cached is not None:
                return cached

        # Retry loop with exponential backoff
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                response = client.chat.completions.create(**kwargs)
                result = response.choices[0].message.content or ""
                # Store in cache
                if use_cache and cache is not None and cache_params is not None:
                    cache.put(result, **cache_params)
                return result
            except Exception as e:
                last_exc = e
                if attempt < MAX_RETRIES - 1 and _is_transient(e):
                    delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning(f"LLM attempt {attempt+1} failed: {e}. Retry in {delay:.1f}s")
                    time.sleep(delay)
                    continue
                break

        # OpenClaw fallback (existing logic — config already bound above)
        if config.llm.backend_type == "openclaw" and config.llm.auto_fallback and config.llm.api_key:
            logger.warning(f"OpenClaw lỗi, fallback sang API: {last_exc}")
            fallback_client = OpenAI(api_key=config.llm.api_key, base_url=config.llm.base_url)
            kwargs["model"] = config.llm.model
            try:
                response = fallback_client.chat.completions.create(**kwargs)
                result = response.choices[0].message.content or ""
                if use_cache and cache is not None and cache_params is not None:
                    cache.put(result, **cache_params)
                return result
            except Exception as e2:
                logger.error(f"Fallback API cũng lỗi: {e2}")
                raise

        logger.error(f"Lỗi gọi LLM sau {MAX_RETRIES} lần: {last_exc}")
        raise last_exc

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
        return json.loads(fixed)

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
        """Gọi LLM với streaming."""
        config = ConfigManager()

        if model_tier == "cheap" and config.llm.cheap_model:
            client, effective_model = self._get_cheap_client()
        else:
            client = self._get_client()
            effective_model = self._current_model or config.llm.model

        kwargs = {
            "model": effective_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature if temperature is not None else config.llm.temperature,
            "max_tokens": max_tokens or config.llm.max_tokens,
            "stream": True,
        }

        try:
            response = client.chat.completions.create(**kwargs)
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            if config.llm.backend_type == "openclaw" and config.llm.auto_fallback and config.llm.api_key:
                logger.warning(f"OpenClaw lỗi, fallback sang API: {e}")
                fallback_client = OpenAI(api_key=config.llm.api_key, base_url=config.llm.base_url)
                kwargs["model"] = config.llm.model
                try:
                    response = fallback_client.chat.completions.create(**kwargs)
                    for chunk in response:
                        if chunk.choices and chunk.choices[0].delta.content:
                            yield chunk.choices[0].delta.content
                    return
                except Exception as e2:
                    logger.error(f"Fallback API cũng lỗi: {e2}")
                    raise
            logger.error(f"Lỗi stream LLM: {e}")
            raise

    def check_connection(self) -> tuple[bool, str]:
        """Kiểm tra kết nối backend."""
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
