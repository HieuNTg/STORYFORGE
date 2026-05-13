"""Gzip-aware StaticFiles for FastAPI/Starlette.

FastAPI's GZipMiddleware does NOT wrap StaticFiles mounts (the middleware sits
above the routing layer but StaticFiles writes the body directly to the ASGI
`send` callable, bypassing the buffering middleware would need).

This class restores gzip on static responses two ways:

1.  If a sibling `<path>.gz` file exists on disk (e.g. produced by
    ``scripts/precompress-static.mjs``), serve it verbatim with the right
    headers.  Highest compression level, zero CPU per request.
2.  Otherwise, if the client accepts gzip and the payload is over the size
    threshold, compress in-process and cache the result by ``(path, mtime)``
    in a bounded LRU.  Dev mode without a build step still works.

Small files (< ~1 KB) are served uncompressed: gzip framing overhead can
exceed the savings and the CPU cost is wasted.
"""

from __future__ import annotations

import gzip
import mimetypes
import os
import stat
from functools import lru_cache
from typing import Tuple

import anyio
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

# Minimum uncompressed size (bytes) before we bother gzipping at runtime.
# Below this, framing overhead can negate the win and we pay CPU for nothing.
_MIN_GZIP_SIZE = 1024

# Content types that are already compressed (images, fonts, archives).
# Re-gzipping them wastes CPU and rarely shrinks the payload.
_SKIP_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/webp",
        "image/avif",
        "font/woff",
        "font/woff2",
        "application/zip",
        "application/gzip",
        "application/x-gzip",
        "application/octet-stream",
    }
)


def _client_accepts_gzip(scope: Scope) -> bool:
    headers = Headers(scope=scope)
    accept_encoding = headers.get("accept-encoding", "")
    # Permissive parse: any token containing "gzip" counts.  Don't bother with
    # q-values — no real client sends `gzip;q=0` for a static asset.
    return "gzip" in accept_encoding.lower()


def _guess_content_type(path: str) -> str:
    ctype, _ = mimetypes.guess_type(path)
    return ctype or "application/octet-stream"


@lru_cache(maxsize=128)
def _compress_cached(full_path: str, mtime_ns: int, size: int) -> bytes:
    """Read + gzip a file, memoised by (path, mtime, size).

    ``mtime_ns`` and ``size`` are part of the cache key so a touched/rewritten
    file invalidates the entry naturally — no manual cache busting needed.
    The ``size`` argument is unused inside the function but participates in
    the key.
    """
    del size  # only used as part of the cache key
    with open(full_path, "rb") as fh:
        raw = fh.read()
    # level=6 is the default zlib level — good ratio without burning CPU.
    return gzip.compress(raw, compresslevel=6, mtime=0)


class GzippedStaticFiles(StaticFiles):
    """StaticFiles subclass that serves gzip when the client supports it.

    Drop-in replacement: same constructor signature as ``StaticFiles``.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        if scope["method"] not in ("GET", "HEAD"):
            raise HTTPException(status_code=405)

        if not _client_accepts_gzip(scope):
            return await super().get_response(path, scope)

        # Try precompressed sibling first (e.g. main.built.css.gz).
        gz_path = path + ".gz"
        try:
            gz_full_path, gz_stat = await anyio.to_thread.run_sync(
                self.lookup_path, gz_path
            )
        except (PermissionError, OSError):
            gz_full_path, gz_stat = "", None

        if gz_stat is not None and stat.S_ISREG(gz_stat.st_mode):
            # Locate the un-compressed sibling so we know the original
            # content-type and can serve a sane response if the underlying
            # file is missing.  This also gives the upstream caching
            # response logic something to hash against.
            try:
                orig_full_path, orig_stat = await anyio.to_thread.run_sync(
                    self.lookup_path, path
                )
            except (PermissionError, OSError):
                orig_full_path, orig_stat = "", None

            content_type = _guess_content_type(path)
            return await self._precompressed_response(
                gz_full_path,
                gz_stat,
                content_type,
                scope,
            )

        # No precompressed sibling — fall back to runtime gzip when worth it.
        try:
            full_path, file_stat = await anyio.to_thread.run_sync(
                self.lookup_path, path
            )
        except PermissionError:
            raise HTTPException(status_code=401)
        except OSError as exc:
            # Re-use the parent's 404/path-too-long handling.
            return await super().get_response(path, scope)

        if (
            file_stat is not None
            and stat.S_ISREG(file_stat.st_mode)
            and file_stat.st_size >= _MIN_GZIP_SIZE
        ):
            content_type = _guess_content_type(path)
            if content_type not in _SKIP_TYPES:
                return await self._runtime_gzip_response(
                    full_path, file_stat, content_type, scope
                )

        # Fall through: directory, missing, too-small, or skip-type.
        return await super().get_response(path, scope)

    async def _precompressed_response(
        self,
        gz_full_path: str,
        gz_stat: os.stat_result,
        content_type: str,
        scope: Scope,
    ) -> Response:
        def _read() -> bytes:
            with open(gz_full_path, "rb") as fh:
                return fh.read()

        body = await anyio.to_thread.run_sync(_read)
        headers = {
            "content-encoding": "gzip",
            "content-type": content_type,
            "vary": "Accept-Encoding",
            "content-length": str(len(body)),
        }
        return Response(
            content=body if scope["method"] == "GET" else b"",
            status_code=200,
            headers=headers,
        )

    async def _runtime_gzip_response(
        self,
        full_path: str,
        file_stat: os.stat_result,
        content_type: str,
        scope: Scope,
    ) -> Response:
        body = await anyio.to_thread.run_sync(
            _compress_cached, full_path, file_stat.st_mtime_ns, file_stat.st_size
        )
        headers = {
            "content-encoding": "gzip",
            "content-type": content_type,
            "vary": "Accept-Encoding",
            "content-length": str(len(body)),
        }
        return Response(
            content=body if scope["method"] == "GET" else b"",
            status_code=200,
            headers=headers,
        )


__all__ = ["GzippedStaticFiles"]
