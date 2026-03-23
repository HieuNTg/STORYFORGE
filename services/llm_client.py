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

    def _get_client(self) -> OpenAI:
        config = ConfigManager()
        if self._client is None or self._last_key != config.llm.api_key:
            self._client = OpenAI(
                api_key=config.llm.api_key,
                base_url=config.llm.base_url,
            )
            self._last_key = config.llm.api_key
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
            "model": config.llm.model,
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

        response = client.chat.completions.create(
            model=config.llm.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature or config.llm.temperature,
            max_tokens=max_tokens or config.llm.max_tokens,
            stream=True,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
