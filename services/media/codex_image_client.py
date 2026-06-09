"""ChatGPT image generation via the Codex OAuth surface (free, Plus-entitled).

This client reuses the user's *own* "Sign in with ChatGPT" credentials that the
official Codex CLI stores in ``~/.codex/auth.json`` and calls the same backend
endpoint Codex CLI uses (``/backend-api/codex/responses``) with the Responses
API ``image_generation`` tool. It is NOT the paid OpenAI Images API and NOT the
consumer web-chat endpoint (that one is gated by proof-of-work + Turnstile — we
deliberately never touch it).

Why this is the clean path:
  * Auth is the user's own official Codex login (no credential harvesting).
  * The Codex endpoint has no Cloudflare/PoW/Turnstile challenge, so a plain
    HTTP client reaches it — no bot-detection bypass is involved.
  * The image tool binds to ``gpt-image-2-codex`` and supports reference images
    (``input_image``), which gives the comic pipeline character consistency.

Token handling is conservative: access tokens live ~10 days, so we only refresh
when the cached token is actually near expiry, and a refresh (which rotates the
refresh token) is persisted back to ``auth.json`` atomically so the user's Codex
CLI keeps working.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Public OAuth client id used by the official Codex CLI ("Sign in with ChatGPT").
_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
_DEFAULT_MODEL = "gpt-5.5"
# Sizes the image_generation tool accepts; anything else falls back to "auto".
_ALLOWED_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}
# Refresh when the access token has less than this many seconds left.
_EXP_SKEW = 300


class CodexImageClient:
    """Generate images through the user's logged-in Codex (ChatGPT Plus) session."""

    def __init__(
        self,
        model: str = "",
        auth_path: str = "",
        request_timeout: float = 180.0,
    ):
        self.auth_path = auth_path or os.path.join(
            os.path.expanduser("~"), ".codex", "auth.json"
        )
        self.config_path = os.path.join(
            os.path.dirname(self.auth_path), "config.toml"
        )
        self.model = model or self._read_config_model() or _DEFAULT_MODEL
        self.request_timeout = request_timeout
        self._access: Optional[str] = None  # cached access token (in-memory)

    # ── Configuration / discovery ─────────────────────────────────────────────

    def is_configured(self) -> bool:
        """True when a usable Codex login exists on disk."""
        data = self._load_auth()
        if not data:
            return False
        tokens = data.get("tokens") or {}
        return bool(
            tokens.get("account_id")
            and (tokens.get("refresh_token") or tokens.get("access_token"))
        )

    def _read_config_model(self) -> str:
        """Best-effort read of the account's Codex model from ~/.codex/config.toml."""
        try:
            with open(self.config_path, "rb") as f:
                try:
                    import tomllib  # py3.11+
                    cfg = tomllib.load(f)
                    val = cfg.get("model")
                    return val if isinstance(val, str) else ""
                except ModuleNotFoundError:  # pragma: no cover - old runtimes
                    f.seek(0)
                    for line in f.read().decode("utf-8", "replace").splitlines():
                        s = line.strip()
                        if s.startswith("model") and "=" in s:
                            return s.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
        return ""

    # ── Auth file I/O ──────────────────────────────────────────────────────────

    def _load_auth(self) -> dict:
        try:
            with open(self.auth_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_auth(self, data: dict) -> None:
        """Atomically persist the updated auth.json (preserves unrelated fields)."""
        tmp = f"{self.auth_path}.tmp.{uuid.uuid4().hex}"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self.auth_path)  # atomic on same volume (incl. Windows)
        except OSError as e:
            logger.warning("Could not persist refreshed Codex token: %s", e)
            try:
                os.remove(tmp)
            except OSError:
                pass

    # ── Token lifecycle ────────────────────────────────────────────────────────

    @staticmethod
    def _jwt_exp(token: str) -> int:
        """Return the JWT ``exp`` (epoch seconds), or 0 if it can't be parsed."""
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)  # pad base64url
            claims = json.loads(base64.urlsafe_b64decode(payload))
            return int(claims.get("exp", 0))
        except Exception:
            return 0

    def _refresh(self, refresh_token: str, auth_data: dict) -> Optional[str]:
        """Exchange the refresh token; persist the rotated set; return new access."""
        try:
            resp = requests.post(
                _OAUTH_TOKEN_URL,
                json={
                    "client_id": _CODEX_CLIENT_ID,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "scope": "openid profile email",
                },
                timeout=60,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            logger.error("Codex token refresh failed: %s", e)
            return None

        access = body.get("access_token")
        if not access:
            logger.error("Codex token refresh returned no access_token")
            return None

        # Persist the rotated tokens so the user's Codex CLI stays valid.
        tokens = dict(auth_data.get("tokens") or {})
        tokens["access_token"] = access
        if body.get("refresh_token"):
            tokens["refresh_token"] = body["refresh_token"]
        if body.get("id_token"):
            tokens["id_token"] = body["id_token"]
        auth_data["tokens"] = tokens
        auth_data["last_refresh"] = datetime.now(timezone.utc).isoformat()
        self._save_auth(auth_data)

        self._access = access
        return access

    def _ensure_token(self, force_refresh: bool = False) -> Optional[str]:
        """Return a valid access token, refreshing only when necessary."""
        data = self._load_auth()
        tokens = data.get("tokens") or {}
        access = tokens.get("access_token")

        if not force_refresh and access:
            exp = self._jwt_exp(access)
            if exp == 0 or exp - time.time() > _EXP_SKEW:
                self._access = access
                return access

        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            # No way to refresh; fall back to whatever access token we have.
            self._access = access
            return access
        return self._refresh(refresh_token, data)

    def _account_id(self) -> str:
        return ((self._load_auth().get("tokens") or {}).get("account_id")) or ""

    # ── Request / SSE assembly ─────────────────────────────────────────────────

    def _build_tools(self, size: str) -> list:
        tool: dict = {"type": "image_generation"}
        if size in _ALLOWED_SIZES and size != "auto":
            tool["size"] = size
        return [tool]

    def _stream_image(self, content_parts: list, size: str) -> Optional[bytes]:
        """POST to the Codex responses endpoint and return the generated PNG bytes."""
        account_id = self._account_id()
        body = {
            "model": self.model,
            "instructions": "You are a helpful assistant that generates images.",
            "input": [{"type": "message", "role": "user", "content": content_parts}],
            "tools": self._build_tools(size),
            "tool_choice": "auto",
            "stream": True,
            "store": False,
        }

        def _do(access: str) -> tuple[int, Optional[bytes]]:
            headers = {
                "Authorization": f"Bearer {access}",
                "chatgpt-account-id": account_id,
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "OpenAI-Beta": "responses=experimental",
                "originator": "codex_cli_rs",
                "session_id": str(uuid.uuid4()),
                "User-Agent": "codex_cli_rs/0.1",
            }
            resp = requests.post(
                _RESPONSES_URL,
                headers=headers,
                json=body,
                stream=True,
                timeout=self.request_timeout,
            )
            if resp.status_code != 200:
                detail = resp.text[:300]
                resp.close()
                logger.warning("Codex responses HTTP %s: %s", resp.status_code, detail)
                return resp.status_code, None
            return 200, self._extract_image(resp)

        access = self._ensure_token()
        if not access:
            logger.error("Codex image generation skipped: no usable access token.")
            return None

        status, img = _do(access)
        if status == 401:
            # Token rejected mid-flight — force a refresh and retry once.
            access = self._ensure_token(force_refresh=True)
            if not access:
                return None
            _, img = _do(access)
        return img

    @staticmethod
    def _extract_image(resp) -> Optional[bytes]:
        """Assemble the SSE stream and return the largest decoded image payload."""
        biggest = b""
        try:
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                payload = raw[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    ev = json.loads(payload)
                except ValueError:
                    continue
                if ev.get("type") == "response.failed" or ev.get("error"):
                    logger.warning("Codex stream error: %.200s", payload)
                # The image arrives as base64 on partial_image events and/or the
                # completed output item; take the largest valid PNG we decode.
                candidates = [ev.get("partial_image_b64"), ev.get("result")]
                item = ev.get("item")
                if isinstance(item, dict):
                    candidates.append(item.get("result"))
                for c in candidates:
                    if isinstance(c, str) and len(c) > 5000:
                        try:
                            data = base64.b64decode(c)
                        except (ValueError, base64.binascii.Error):
                            continue
                        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > len(biggest):
                            biggest = data
        finally:
            resp.close()
        return biggest or None

    # ── Public API ─────────────────────────────────────────────────────────────

    def text_to_image(
        self, prompt: str, filepath: str, size: str = "1024x1024"
    ) -> Optional[str]:
        """Generate an image from a text prompt; save to ``filepath``."""
        if not self.is_configured():
            logger.error("Codex image generation skipped: no Codex login found.")
            return None
        parts = [{"type": "input_text", "text": prompt}]
        return self._save(self._stream_image(parts, size), filepath)

    def image_with_refs(
        self,
        prompt: str,
        reference_paths: list,
        filepath: str,
        size: str = "1024x1024",
    ) -> Optional[str]:
        """Generate conditioned on character reference image(s)."""
        if not self.is_configured():
            logger.error("Codex image generation skipped: no Codex login found.")
            return None
        parts: list = [{"type": "input_text", "text": prompt}]
        for ref in reference_paths or []:
            data_url = self._encode_image(ref)
            if data_url:
                parts.append({"type": "input_image", "image_url": data_url})
        return self._save(self._stream_image(parts, size), filepath)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _encode_image(path: str) -> Optional[str]:
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as e:
            logger.warning("Could not read reference image %s: %s", path, e)
            return None
        mime = "image/png"
        lower = path.lower()
        if lower.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        elif lower.endswith(".webp"):
            mime = "image/webp"
        return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")

    @staticmethod
    def _save(image: Optional[bytes], filepath: str) -> Optional[str]:
        if not image:
            return None
        try:
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(image)
        except OSError as e:
            logger.error("Could not save Codex image to %s: %s", filepath, e)
            return None
        logger.info("Generated Codex image: %s (%d bytes)", filepath, len(image))
        return filepath
