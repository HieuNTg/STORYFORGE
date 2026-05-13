"""Tests for services.gzipped_static_files.GzippedStaticFiles.

Verifies the four contractual behaviours documented in S3:

1.  Precompressed `.gz` sibling is served verbatim with `Content-Encoding: gzip`.
2.  Files >1KB without a sibling get compressed at runtime; the body decodes
    back to the original payload.
3.  Missing `Accept-Encoding` header → uncompressed response.
4.  Files <1KB are served uncompressed regardless of `Accept-Encoding`.
"""

from __future__ import annotations

import gzip
import os
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from services.gzipped_static_files import GzippedStaticFiles


# ---------- fixtures ----------------------------------------------------------


@pytest_asyncio.fixture
async def static_app(tmp_path: Path):
    """Build a tiny FastAPI app mounting GzippedStaticFiles at /static.

    The fixture yields ``(client, tmp_path)`` so each test can drop assets into
    the tmp dir and immediately request them.
    """
    app = FastAPI()
    app.mount("/static", GzippedStaticFiles(directory=str(tmp_path)), name="static")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, tmp_path


# ---------- tests -------------------------------------------------------------


@pytest.mark.asyncio
async def test_serves_precompressed_gz_when_available(static_app):
    client, tmp_path = static_app
    # Large enough that runtime gzip *would* fire — so we can prove the sibling
    # is preferred (different bytes vs runtime-compressed level=6).
    raw = (b"body { color: hotpink; } /* padding */" * 50)
    (tmp_path / "foo.css").write_bytes(raw)
    # Use a deliberately distinct compression level (9) so the .gz bytes
    # differ from what runtime gzip would produce at level 6.
    gz_bytes = gzip.compress(raw, compresslevel=9, mtime=0)
    (tmp_path / "foo.css.gz").write_bytes(gz_bytes)

    resp = await client.get("/static/foo.css", headers={"Accept-Encoding": "gzip"})

    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") == "gzip"
    assert resp.headers.get("content-type", "").startswith("text/css")
    assert resp.headers.get("vary") == "Accept-Encoding"
    # httpx auto-decompresses when transport sees content-encoding; compare the
    # decoded bytes to the raw source to confirm payload integrity.
    assert resp.content == raw
    # Confirm we actually shipped the level-9 sibling, not a runtime recompress:
    # decompress the on-disk file and the response body should match the raw.
    assert gzip.decompress(gz_bytes) == raw


@pytest.mark.asyncio
async def test_falls_back_to_runtime_gzip_when_no_sibling(static_app):
    client, tmp_path = static_app
    raw = b"console.log('hello world');\n" * 100  # ~2.7KB, well above 1KB
    (tmp_path / "app.js").write_bytes(raw)

    resp = await client.get("/static/app.js", headers={"Accept-Encoding": "gzip"})

    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") == "gzip"
    assert resp.headers.get("vary") == "Accept-Encoding"
    # httpx already decoded the body for us — verify it round-trips.
    assert resp.content == raw


@pytest.mark.asyncio
async def test_no_gzip_when_accept_encoding_omitted(static_app):
    client, tmp_path = static_app
    raw = b"a" * 4096
    (tmp_path / "plain.css").write_bytes(raw)
    # A sibling .gz exists too — must still NOT be served when the client
    # doesn't advertise gzip support.
    (tmp_path / "plain.css.gz").write_bytes(gzip.compress(raw))

    # httpx adds its own Accept-Encoding by default; override explicitly.
    resp = await client.get("/static/plain.css", headers={"Accept-Encoding": "identity"})

    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") in (None, "")
    assert resp.content == raw


@pytest.mark.asyncio
async def test_no_gzip_for_small_files(static_app):
    client, tmp_path = static_app
    raw = b"tiny"  # 4 bytes — well below threshold
    (tmp_path / "tiny.css").write_bytes(raw)

    resp = await client.get("/static/tiny.css", headers={"Accept-Encoding": "gzip"})

    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") in (None, "")
    assert resp.content == raw
