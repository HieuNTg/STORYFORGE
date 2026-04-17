"""Native Google Gemini provider."""
import logging
from typing import Iterator

logger = logging.getLogger(__name__)


class GeminiProvider:
    _is_llm_provider = True

    def __init__(self, api_key: str, base_url: str = ""):
        try:
            from google import genai
            self.client = genai.Client(api_key=api_key)
            self._base_url = base_url
            self._api_key = api_key
        except ImportError:
            raise ImportError(
                "Google GenAI SDK not installed. Run: pip install google-genai"
            )

    def _extract_rate_limits(self, response) -> None:
        """Extract rate limit info from response (if available)."""
        try:
            # Google SDK doesn't expose HTTP headers directly
            # Check for usage_metadata which contains token counts
            usage = getattr(response, "usage_metadata", None)
            if not usage:
                return
            # Could track token usage here for internal accounting
            # but Google doesn't expose rate limit headers in the same way
        except Exception as e:
            logger.debug(f"Rate limit extraction failed: {e}")

    @property
    def base_url(self):
        return self._base_url

    def _build_contents(self, messages: list[dict]) -> tuple[str | None, list[dict]]:
        """Extract system instruction and convert messages to Gemini format."""
        system_instruction = None
        contents = []
        for m in messages:
            if m["role"] == "system":
                system_instruction = m["content"]
            else:
                role = "user" if m["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m["content"]}]})
        return system_instruction, contents

    def complete(self, messages: list[dict], model: str, temperature: float,
                 max_tokens: int, json_mode: bool = False) -> str:
        from google.genai import types
        system_instruction, contents = self._build_contents(messages)
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
        )
        if json_mode:
            config.response_mime_type = "application/json"
        response = self.client.models.generate_content(
            model=model, contents=contents, config=config
        )
        self._extract_rate_limits(response)
        content = response.text
        if not content or not content.strip():
            raise RuntimeError(f"LLM returned empty content (model={model})")
        return content

    def stream(self, messages: list[dict], model: str, temperature: float,
               max_tokens: int) -> Iterator[str]:
        from google.genai import types
        system_instruction, contents = self._build_contents(messages)
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
        )
        for chunk in self.client.models.generate_content_stream(
            model=model, contents=contents, config=config
        ):
            if chunk.text:
                yield chunk.text
