"""SSRF validation for user-supplied base_url values.

StoryForge is a local, single-user, open-source app, and users legitimately
point it at endpoints we have never heard of: a self-hosted vLLM, a personal
proxy, a new provider that ships an OpenAI-compatible API tomorrow. The old
fixed vendor allowlist made that impossible — every custom base_url came back
`400 base_url host '…' is not in the provider allowlist` — so the rule is now
"any public host, no private ones" instead of "these six vendors".

What still gets blocked is what SSRF actually needs blocked: non-HTTP schemes,
and anything that RESOLVES to a private or link-local address (cloud metadata
at 169.254.169.254 included) — resolution matters, otherwise `evil.example`
pointing at 127.0.0.1 walks straight through a hostname-only check.

Two deliberate exceptions:
  * Loopback typed explicitly (localhost / 127.0.0.1 / ::1) is allowed — local
    bridges are a supported provider (see config/presets.py, the Gemini Web
    card at localhost:8000).
  * STORYFORGE_ALLOW_PRIVATE_BASE_URL=1 lifts the private-range block for the
    LAN case (an Ollama/vLLM box at 192.168.x.x). Opt-in, off by default.
"""

import ipaddress
import os
import socket
from urllib.parse import urlparse

from fastapi import HTTPException

# Typed-by-hand loopback. Allowed because running a local OpenAI-compatible
# bridge is a first-class feature here, not an SSRF bypass we forgot to close.
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local + cloud metadata
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _allow_private() -> bool:
    """True when the operator opted into private/LAN endpoints."""
    return os.environ.get("STORYFORGE_ALLOW_PRIVATE_BASE_URL", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _is_private(addr: ipaddress._BaseAddress) -> bool:
    return any(addr in net for net in _BLOCKED_NETWORKS)


def _resolved_addresses(host: str) -> list[ipaddress._BaseAddress]:
    """Every address `host` resolves to, or [] when resolution fails.

    A name that does not resolve cannot be reached either, so an empty list is
    not treated as a rejection — it keeps `base_url` savable while offline.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    out: list[ipaddress._BaseAddress] = []
    for info in infos:
        raw = info[4][0]
        try:
            out.append(ipaddress.ip_address(raw.split("%", 1)[0]))
        except ValueError:
            continue
    return out


def validate_base_url(url: str) -> None:
    """Raise HTTPException 400 if url is malformed or targets a private network.

    Empty/None url is allowed (caller may skip the field).
    """
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400, detail="base_url scheme must be http or https"
        )
    host = (parsed.hostname or "").lower()
    if not host:
        raise HTTPException(status_code=400, detail="base_url missing host")

    if host in _LOOPBACK_HOSTS or _allow_private():
        return

    # A bare IP needs no DNS round-trip.
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if _is_private(addr):
            raise HTTPException(
                status_code=400,
                detail="base_url targets a private/internal address",
            )
        return

    for resolved in _resolved_addresses(host):
        if _is_private(resolved):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"base_url host '{host}' resolves to a private/internal "
                    "address. Set STORYFORGE_ALLOW_PRIVATE_BASE_URL=1 if that "
                    "is intentional."
                ),
            )
