"""Tests for CodexImageClient — auth/refresh + SSE image assembly.

All HTTP is mocked; no live network calls and no real Codex login are touched.
The on-disk ``auth.json`` / ``config.toml`` are faked under ``tmp_path`` so the
token-rotation persistence path can be asserted without touching ``~/.codex``.
"""

import base64
import hashlib
import json
import struct
import zlib
from unittest.mock import MagicMock, patch

from services.media.codex_image_client import CodexImageClient


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


# Minimal real PNG so the magic-byte validation in _extract_image passes. The
# IDAT filler is deterministic but high-entropy (sha256 chaining) so it does NOT
# compress away — the base64 string must clear the 5000-char threshold that
# _extract_image uses to skip non-image payloads. ``blocks`` controls the size so
# tests can build a clearly-"larger" frame to exercise the largest-wins logic.
def _png_bytes(
    payload: bytes = b"storyforge-codex-test", *, blocks: int = 220
) -> bytes:
    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    filler = b""
    seed = hashlib.sha256(payload).digest()
    for _ in range(blocks):
        seed = hashlib.sha256(seed).digest()
        filler += seed

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(filler)  # ~32*blocks bytes of incompressible data
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


def _jwt(exp: int) -> str:
    """Build an unsigned JWT whose payload carries the given ``exp``."""

    def b64(obj: dict) -> str:
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64({'exp': exp})}.sig"


def _write_auth(tmp_path, *, access=None, refresh="refresh-orig", account="acct-123"):
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": access,
                    "refresh_token": refresh,
                    "id_token": "id-orig",
                    "account_id": account,
                },
                "last_refresh": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return str(auth)


def _sse_response(events, status=200, *, as_bytes=False):
    """Fake a streaming requests.Response yielding SSE ``data:`` lines.

    ``as_bytes`` reproduces the REAL behavior of ``requests`` on chatgpt.com's
    SSE: the ``text/event-stream`` response carries no charset, so
    ``iter_lines(decode_unicode=True)`` is a no-op and yields ``bytes``, not
    ``str``. The default str mode keeps the rest of the suite readable.
    """
    resp = MagicMock()
    resp.status_code = status
    lines = []
    for ev in events:
        lines.append("data: " + json.dumps(ev))
        lines.append("")
    resp.iter_lines.return_value = (
        [ln.encode("utf-8") for ln in lines] if as_bytes else lines
    )
    resp.text = "" if status == 200 else "error-body"
    resp.close = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


def test_is_configured_true_with_refresh_and_account(tmp_path):
    path = _write_auth(tmp_path, access=_jwt(9_999_999_999))
    client = CodexImageClient(model="gpt-5.5", auth_path=path)
    assert client.is_configured() is True


def test_is_configured_false_when_no_auth_file(tmp_path):
    client = CodexImageClient(model="gpt-5.5", auth_path=str(tmp_path / "nope.json"))
    assert client.is_configured() is False


def test_is_configured_false_without_account_id(tmp_path):
    path = _write_auth(tmp_path, access=_jwt(9_999_999_999), account="")
    client = CodexImageClient(model="gpt-5.5", auth_path=path)
    assert client.is_configured() is False


# ---------------------------------------------------------------------------
# model discovery from config.toml
# ---------------------------------------------------------------------------


def test_model_read_from_config_toml(tmp_path):
    _write_auth(tmp_path)
    (tmp_path / "config.toml").write_text('model = "gpt-5.5-codex"\n', encoding="utf-8")
    client = CodexImageClient(auth_path=str(tmp_path / "auth.json"))
    assert client.model == "gpt-5.5-codex"


def test_explicit_model_overrides_config_toml(tmp_path):
    _write_auth(tmp_path)
    (tmp_path / "config.toml").write_text('model = "gpt-5.5-codex"\n', encoding="utf-8")
    client = CodexImageClient(model="gpt-6", auth_path=str(tmp_path / "auth.json"))
    assert client.model == "gpt-6"


def test_model_default_when_no_config(tmp_path):
    _write_auth(tmp_path)
    client = CodexImageClient(auth_path=str(tmp_path / "auth.json"))
    assert client.model == "gpt-5.5"


# ---------------------------------------------------------------------------
# token lifecycle
# ---------------------------------------------------------------------------


def test_ensure_token_uses_cached_when_not_near_expiry(tmp_path):
    path = _write_auth(tmp_path, access=_jwt(9_999_999_999))
    client = CodexImageClient(auth_path=path)
    with patch("services.media.codex_image_client.requests.post") as post:
        tok = client._ensure_token()
    post.assert_not_called()  # fresh token → no refresh
    assert tok == client._load_auth()["tokens"]["access_token"]


def test_ensure_token_refreshes_when_expired_and_persists_rotation(tmp_path):
    path = _write_auth(tmp_path, access=_jwt(1))  # already expired
    client = CodexImageClient(auth_path=path)

    refreshed = MagicMock()
    refreshed.json.return_value = {
        "access_token": "access-NEW",
        "refresh_token": "refresh-ROTATED",
        "id_token": "id-NEW",
    }
    refreshed.raise_for_status = MagicMock()

    with patch(
        "services.media.codex_image_client.requests.post", return_value=refreshed
    ) as post:
        tok = client._ensure_token()

    assert tok == "access-NEW"
    post.assert_called_once()
    # The rotated refresh token MUST be written back so the user's Codex CLI survives.
    persisted = client._load_auth()["tokens"]
    assert persisted["access_token"] == "access-NEW"
    assert persisted["refresh_token"] == "refresh-ROTATED"
    assert persisted["id_token"] == "id-NEW"


def test_refresh_failure_returns_none(tmp_path):
    path = _write_auth(tmp_path, access=_jwt(1))
    client = CodexImageClient(auth_path=path)
    boom = MagicMock()
    boom.raise_for_status.side_effect = RuntimeError("network down")
    with patch("services.media.codex_image_client.requests.post", return_value=boom):
        assert client._ensure_token() is None
    # auth.json must be left untouched on a failed refresh.
    assert client._load_auth()["tokens"]["refresh_token"] == "refresh-orig"


# ---------------------------------------------------------------------------
# SSE image extraction
# ---------------------------------------------------------------------------


def test_extract_image_picks_largest_valid_png():
    small = _png_bytes(b"x", blocks=180)
    big = _png_bytes(b"the-final-frame", blocks=400)
    resp = _sse_response(
        [
            {
                "type": "image_generation_call.partial_image",
                "partial_image_b64": base64.b64encode(small).decode(),
            },
            {
                "type": "image_generation_call.partial_image",
                "partial_image_b64": base64.b64encode(big).decode(),
            },
            {"type": "response.completed"},
        ]
    )
    out = CodexImageClient._extract_image(resp)
    assert out == big
    resp.close.assert_called_once()


def test_extract_image_ignores_non_png_base64():
    junk = base64.b64encode(b"NOTPNG" * 2000).decode()
    resp = _sse_response([{"type": "x", "partial_image_b64": junk}])
    assert CodexImageClient._extract_image(resp) is None


def test_extract_image_handles_bytes_lines_from_real_stream():
    # Regression: chatgpt.com's text/event-stream has no charset, so
    # requests' decode_unicode is a no-op and iter_lines yields bytes. The
    # extractor must decode them itself instead of crashing on
    # bytes.startswith("data:") and silently losing the image.
    png = _png_bytes(b"bytes-stream")
    resp = _sse_response(
        [
            {
                "type": "image_generation_call.partial_image",
                "partial_image_b64": base64.b64encode(png).decode(),
            },
            {"type": "response.completed"},
        ],
        as_bytes=True,
    )
    assert CodexImageClient._extract_image(resp) == png


def test_extract_image_reads_result_on_output_item():
    png = _png_bytes(b"item-result")
    resp = _sse_response(
        [
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "image_generation_call",
                    "result": base64.b64encode(png).decode(),
                },
            }
        ]
    )
    assert CodexImageClient._extract_image(resp) == png


# ---------------------------------------------------------------------------
# _stream_image — request shape, refs, 401 retry
# ---------------------------------------------------------------------------


def test_stream_image_sends_auth_and_account_headers(tmp_path):
    path = _write_auth(tmp_path, access=_jwt(9_999_999_999), account="acct-XYZ")
    client = CodexImageClient(model="gpt-5.5", auth_path=path)
    png = _png_bytes()
    resp = _sse_response(
        [{"type": "x", "partial_image_b64": base64.b64encode(png).decode()}]
    )
    with patch(
        "services.media.codex_image_client.requests.post", return_value=resp
    ) as post:
        out = client._stream_image([{"type": "input_text", "text": "hi"}], "1024x1024")

    assert out == png
    _, kwargs = post.call_args
    headers = kwargs["headers"]
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["chatgpt-account-id"] == "acct-XYZ"
    assert headers["Accept"] == "text/event-stream"
    body = kwargs["json"]
    assert body["model"] == "gpt-5.5"
    assert body["tools"] == [{"type": "image_generation", "size": "1024x1024"}]
    assert body["stream"] is True


def test_stream_image_401_triggers_force_refresh_and_retry(tmp_path):
    path = _write_auth(tmp_path, access=_jwt(9_999_999_999))
    client = CodexImageClient(auth_path=path)

    unauthorized = _sse_response([], status=401)
    png = _png_bytes()
    ok = _sse_response(
        [{"type": "x", "partial_image_b64": base64.b64encode(png).decode()}]
    )

    refreshed = MagicMock()
    refreshed.json.return_value = {"access_token": "access-NEW", "refresh_token": "r2"}
    refreshed.raise_for_status = MagicMock()

    # First POST is the responses call (401); second is oauth refresh; third is the retry.
    with patch(
        "services.media.codex_image_client.requests.post",
        side_effect=[unauthorized, refreshed, ok],
    ) as post:
        out = client._stream_image([{"type": "input_text", "text": "hi"}], "1024x1024")

    assert out == png
    assert post.call_count == 3
    # The retry must carry the refreshed bearer token.
    retry_headers = post.call_args_list[2].kwargs["headers"]
    assert retry_headers["Authorization"] == "Bearer access-NEW"


def test_image_with_refs_attaches_input_image_parts(tmp_path):
    path = _write_auth(tmp_path, access=_jwt(9_999_999_999))
    client = CodexImageClient(auth_path=path)
    ref = tmp_path / "hero.png"
    ref.write_bytes(_png_bytes(b"hero"))
    out_file = tmp_path / "out.png"

    captured = {}

    def _fake_stream(parts, size):
        captured["parts"] = parts
        return _png_bytes(b"gen")

    with patch.object(client, "_stream_image", side_effect=_fake_stream):
        result = client.image_with_refs("draw hero", [str(ref)], str(out_file))

    assert result == str(out_file)
    assert out_file.read_bytes() == _png_bytes(b"gen")
    kinds = [p["type"] for p in captured["parts"]]
    assert kinds == ["input_text", "input_image"]
    assert captured["parts"][1]["image_url"].startswith("data:image/png;base64,")


def test_text_to_image_not_configured_returns_none(tmp_path):
    client = CodexImageClient(auth_path=str(tmp_path / "absent.json"))
    assert client.text_to_image("prompt", str(tmp_path / "out.png")) is None


def test_text_to_image_writes_file(tmp_path):
    path = _write_auth(tmp_path, access=_jwt(9_999_999_999))
    client = CodexImageClient(auth_path=path)
    out_file = tmp_path / "sub" / "out.png"
    png = _png_bytes(b"final")
    with patch.object(client, "_stream_image", return_value=png):
        result = client.text_to_image("a red circle", str(out_file))
    assert result == str(out_file)
    assert out_file.read_bytes() == png
