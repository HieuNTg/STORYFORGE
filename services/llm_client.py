"""Client giao tiếp với LLM API."""

import json
import logging
from typing import Optional
from openai import OpenAI
from config import ConfigManager

logger = logging.getLogger(__name__)


class LLMClient:
    """Client gọi LLM API thông qua OpenAI-compatible endpoint."""

    _instance = None

    def __new__(cls):
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

    def _get_client(self) -> OpenAI:
        config = ConfigManager()

        # Xác định base_url và api_key theo backend
        if config.llm.backend_type == "openclaw":
            base_url = f"http://localhost:{config.llm.openclaw_port}/v1"
            api_key = "openclaw-token"  # OpenClaw không cần real key
            model = config.llm.openclaw_model
        else:
            base_url = config.llm.base_url
            api_key = config.llm.api_key
            model = config.llm.model

        # Cache key để biết khi nào cần tạo client mới
        cache_key = f"{base_url}:{api_key}"
        if self._client is None or self._last_key != cache_key:
            self._client = OpenAI(api_key=api_key, base_url=base_url)
            self._last_key = cache_key
            self._current_model = model

        return self._client

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """Gọi LLM và trả về văn bản kết quả."""
        config = ConfigManager()
        client = self._get_client()

        kwargs = {
            "model": self._current_model or config.llm.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature or config.llm.temperature,
            "max_tokens": max_tokens or config.llm.max_tokens,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except Exception as e:
            config = ConfigManager()
            # Auto-fallback: nếu đang dùng OpenClaw và có API key, thử lại với API
            if config.llm.backend_type == "openclaw" and config.llm.auto_fallback and config.llm.api_key:
                logger.warning(f"OpenClaw lỗi, fallback sang API: {e}")
                # Tạm thời switch sang API
                fallback_client = OpenAI(
                    api_key=config.llm.api_key,
                    base_url=config.llm.base_url,
                )
                kwargs["model"] = config.llm.model
                try:
                    response = fallback_client.chat.completions.create(**kwargs)
                    return response.choices[0].message.content or ""
                except Exception as e2:
                    logger.error(f"Fallback API cũng lỗi: {e2}")
                    raise
            logger.error(f"Lỗi gọi LLM: {e}")
            raise

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
    ) -> dict:
        """Gọi LLM và parse kết quả JSON."""
        result = self.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            json_mode=True,
        )
        # Cố gắng parse JSON, xử lý trường hợp có markdown code block
        text = result.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        return json.loads(text)

    def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """Gọi LLM với streaming."""
        config = ConfigManager()
        client = self._get_client()

        kwargs = {
            "model": self._current_model or config.llm.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature or config.llm.temperature,
            "max_tokens": max_tokens or config.llm.max_tokens,
            "stream": True,
        }

        try:
            response = client.chat.completions.create(**kwargs)
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            # Auto-fallback: nếu đang dùng OpenClaw và có API key, thử lại với API
            if config.llm.backend_type == "openclaw" and config.llm.auto_fallback and config.llm.api_key:
                logger.warning(f"OpenClaw lỗi, fallback sang API: {e}")
                fallback_client = OpenAI(
                    api_key=config.llm.api_key,
                    base_url=config.llm.base_url,
                )
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
        """Kiểm tra kết nối backend. Returns (ok, message)."""
        try:
            client = self._get_client()
            # Gửi request nhỏ để test
            response = client.chat.completions.create(
                model=self._current_model or ConfigManager().llm.model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5,
            )
            return True, "Kết nối thành công"
        except Exception as e:
            return False, f"Lỗi kết nối: {str(e)}"
