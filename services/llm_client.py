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
        use_cache = config.llm.cache_enabled and effective_temp <= 0.7
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
            return self._generate_web(messages, effective_temp, use_cache, cache, cache_params)

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
                all_errors.append(f"{provider['label']}: {e}")
                if not _is_transient(e):
                    raise  # 4xx errors — don't try fallbacks
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
        """Try a single provider with retry."""
        kwargs = {
            "model": provider["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        last_exc = None
        for attempt in range(2):
            try:
                response = provider["client"].chat.completions.create(**kwargs)
                result = response.choices[0].message.content or ""
                logger.info(f"LLM success via {provider['label']}")
                return result
            except Exception as e:
                last_exc = e
                if attempt == 0 and _is_transient(e):
                    time.sleep(BASE_DELAY)
                    continue
                break
        raise last_exc

    def _generate_web(self, messages, temperature, use_cache, cache, cache_params) -> str:
        """Generate via DeepSeek web backend with retry."""
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                web_client = self._get_web_client()
                result = web_client.chat_completion_sync(
                    messages=messages, temperature=temperature,
                )
                if use_cache and cache is not None and cache_params is not None:
                    cache.put(result, **cache_params)
                return result
            except Exception as e:
                last_exc = e
                if attempt < MAX_RETRIES - 1 and _is_transient(e):
                    delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning(f"Web LLM attempt {attempt+1} failed: {e}. Retry in {delay:.1f}s")
                    time.sleep(delay)
                    continue
                break

        logger.error(f"Lỗi web LLM sau {MAX_RETRIES} lần: {last_exc}")
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

        # Web backend streaming
        if self._is_web_backend():
            last_exc = None
            for attempt in range(MAX_RETRIES):
                try:
                    web_client = self._get_web_client()
                    for chunk in web_client.chat_completion(
                        messages=messages, temperature=effective_temp, stream=True,
                    ):
                        yield chunk
                    return
                except Exception as e:
                    last_exc = e
                    if attempt < MAX_RETRIES - 1 and _is_transient(e):
                        delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                        logger.warning(f"Web stream attempt {attempt+1} failed: {e}. Retry in {delay:.1f}s")
                        time.sleep(delay)
                        continue
                    break
            logger.error(f"Lỗi web stream sau {MAX_RETRIES} lần: {last_exc}")
            raise last_exc

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

        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                response = client.chat.completions.create(**kwargs)
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception as e:
                last_exc = e
                if attempt < MAX_RETRIES - 1 and _is_transient(e):
                    delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning(f"Stream attempt {attempt+1} failed: {e}. Retry in {delay:.1f}s")
                    time.sleep(delay)
                    continue
                break

        logger.error(f"Lỗi stream LLM sau {MAX_RETRIES} lần: {last_exc}")
        raise last_exc

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
