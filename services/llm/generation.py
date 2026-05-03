"""Generation mixins — JSON parsing, streaming, and connection check for LLMClient."""

import json
import logging
import re
from typing import Optional


logger = logging.getLogger(__name__)


def _config_manager():
    """Lazy-resolve ConfigManager through compat hub for test mock support."""
    import services.llm_client as m
    return m.ConfigManager


class GenerationMixin:
    """Mixin providing generate_json, generate_stream, and check_connection."""

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model_tier: str = "default",
        model: Optional[str] = None,
    ) -> dict:
        """Call LLM and parse JSON result with auto-repair."""
        text = self._generate_json_text(
            system_prompt, user_prompt, temperature, max_tokens,
            model_tier, model,
        )

        # Attempt 1: direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed, attempting repair: {e}")

        # Attempt 2: repair common issues (trailing commas, quotes, truncation)
        repaired = _repair_json(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Attempt 3: ask LLM to fix (use cheap model) — skip if text is trivially short
        if len(text) < 5:
            raise ValueError(
                f"JSON parse failed: LLM returned near-empty response "
                f"({len(text)} chars): {text!r}"
            )
        logger.warning("JSON repair failed, asking LLM to fix")
        fixed = self.generate(
            system_prompt="Fix this malformed JSON. Return ONLY valid JSON, no explanation.",
            user_prompt=text[:4000],
            temperature=0.0,
            json_mode=True,
            model_tier="cheap",
        )
        try:
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            preview = fixed[:800] if fixed else "<empty>"
            raise ValueError(
                f"JSON parse failed after 3 attempts. "
                f"Parse error: {e}. "
                f"Last text ({len(fixed)} chars, showing first 800): {preview!r}"
            ) from e

    def _generate_json_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float],
        max_tokens: Optional[int],
        model_tier: str,
        model: Optional[str],
        _retried: bool = False,
    ) -> str:
        """Generate text for JSON parsing, retrying once on empty response."""
        result = self.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            model_tier=model_tier,
            model=model,
        )
        text = result.strip()

        # Retry once on empty — likely a flaky free model
        if not text and not _retried:
            logger.warning("LLM returned empty response for JSON request, retrying")
            return self._generate_json_text(
                system_prompt, user_prompt, temperature, max_tokens,
                model_tier, model, _retried=True,
            )

        # Strip markdown code block
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        return text

    def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model_tier: str = "default",
        model: Optional[str] = None,
    ):
        """Call LLM with streaming + chain-level fallback.

        Iterates the same fallback chain used by generate(). The first entry to
        produce any chunk "wins" and its stream is consumed to completion.
        Entries that fail before yielding anything (auth, 429 quota, connection
        error) are skipped with proper rate-limit marking. Mid-stream failures
        re-raise (can't safely retry without duplicating already-yielded tokens).
        """
        config = _config_manager()()
        effective_temp = temperature if temperature is not None else config.llm.temperature

        from services.prompts import localize_prompt
        lang = config.pipeline.language
        system_prompt = localize_prompt(system_prompt, lang)
        user_prompt = localize_prompt(user_prompt, lang)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        eff_max_tokens = max_tokens or config.llm.max_tokens
        chain = self._build_fallback_chain(config, model_tier, model_override=model)
        if not chain:
            raise RuntimeError("LLM fallback chain is empty — check config/model availability")

        from services.llm.retry import (
            _redact, _detect_provider, _should_retry, _is_transient, _is_auth_error,
        )
        from services.llm.model_fallback import get_fallback_manager

        all_errors: list[str] = []
        total_yielded = 0
        for entry in chain:
            provider = entry.get("provider") or entry.get("client")
            entry_model = entry["model"]
            entry_key = entry.get("_api_key", "")
            provider_url = getattr(provider, "base_url", None)
            provider_type = _detect_provider(str(provider_url) if provider_url else "")

            def _api_gen(p=provider, m=entry_model):
                yield from p.stream(messages, m, effective_temp, eff_max_tokens)

            entry_yielded = 0
            try:
                for chunk in self._stream_with_chunk_timeout(
                    self._stream_with_retry(_api_gen, f"stream:{entry['label']}"),
                    chunk_timeout=30,
                    first_chunk_timeout=60,
                ):
                    entry_yielded += 1
                    total_yielded += 1
                    yield chunk
                logger.info(f"Stream success via {entry['label']} ({entry_yielded} chunks)")
                return
            except Exception as e:
                all_errors.append(f"{entry['label']}: {_redact(e)}")
                if entry_yielded > 0 or total_yielded > 0:
                    logger.error(
                        f"Stream failed mid-stream on {entry['label']} after "
                        f"{entry_yielded} chunks: {_redact(e)}"
                    )
                    raise

                # Mark unhealthy (except for transient/auth errors)
                fm = get_fallback_manager()
                if entry_model and not _is_transient(e) and not _is_auth_error(e):
                    fm.mark_unhealthy(entry_model, error_class=type(e).__name__)

                # Rate-limit marking on 429
                err_str = str(e)
                if entry_key and "429" in err_str:
                    if provider_type == "openrouter" and self._is_account_rate_limit(err_str):
                        self._mark_rate_limited(entry_key, 300.0)
                    elif provider_type in ("openrouter", "kyma"):
                        self._mark_model_rate_limited(entry_model, entry_key, 90.0)
                    else:
                        # Google/other: model-level cooldown, keep key usable for other models
                        self._mark_model_rate_limited(entry_model, entry_key, 60.0)

                should_try_next, _ = _should_retry(e, provider_type)
                if not should_try_next and not _is_transient(e):
                    logger.error(f"FATAL streaming error on {entry['label']}: {_redact(e)}")
                    raise
                logger.warning(
                    f"Stream {entry['label']} failed before first chunk, trying next: {_redact(e)}"
                )

        raise RuntimeError(
            f"All LLM providers failed (streaming). Errors: {'; '.join(all_errors)}"
        )

    def check_connection(self) -> tuple[bool, str]:
        """Check API backend connection using full fallback chain."""
        try:
            self.generate(
                system_prompt="Reply OK",
                user_prompt="ping",
                temperature=0.0,
                max_tokens=5,
            )
            return True, "Kết nối thành công"
        except Exception as e:
            return False, f"Lỗi kết nối: {str(e)}"

    def check_provider(self, base_url: str, api_key: str, model: str) -> tuple[bool, str]:
        """Check connection to a specific provider."""
        from services.llm.providers import get_provider
        try:
            provider = get_provider(base_url=base_url, api_key=api_key)
            provider.complete(
                messages=[{"role": "user", "content": "ping"}],
                model=model, temperature=0.0, max_tokens=5,
            )
            return True, "OK"
        except Exception as e:
            return False, str(e)[:200]


def _repair_json(text: str) -> str:
    """Fix common JSON issues: trailing commas, single quotes, truncation."""
    if not text or len(text) < 2:
        return text
    text = re.sub(r',\s*([}\]])', r'\1', text)
    text = re.sub(r"(?<=[\[{,:])\s*'([^']*?)'\s*(?=[,}\]:])", r' "\1" ', text)
    # Extract JSON boundaries
    starts = [text.find(c) for c in ('{', '[') if text.find(c) >= 0]
    ends = [text.rfind(c) for c in ('}', ']') if text.rfind(c) >= 0]
    if starts and ends:
        text = text[min(starts):max(ends) + 1]
    elif starts:
        # Truncated — no closing bracket found; attempt to close
        text = text[min(starts):]
        text = _close_truncated_json(text)
    return text


def _close_truncated_json(text: str) -> str:
    """Best-effort closure of truncated JSON by balancing brackets/quotes."""
    in_string = False
    escape = False
    stack = []
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            stack.append('}' if ch == '{' else ']')
        elif ch in ('}', ']'):
            if stack:
                stack.pop()
    # Close unclosed string
    if in_string:
        text += '"'
    # Remove trailing comma before we close
    text = re.sub(r',\s*$', '', text)
    # Close unclosed brackets in reverse order
    text += ''.join(reversed(stack))
    return text
