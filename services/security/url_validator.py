"""SSRF / allowlist validation for user-supplied base_url values."""

import ipaddress
from urllib.parse import urlparse

from fastapi import HTTPException

_ALLOWED_HOSTS = {
    "api.openai.com",
    "api.anthropic.com",
    "openrouter.ai",
    "generativelanguage.googleapis.com",
    "kymaapi.com",
    "api.z.ai",
    "localhost",
    "127.0.0.1",
}

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def validate_base_url(url: str) -> None:
    """Raise HTTPException 400 if url is not on the provider allowlist or targets private networks.

    Empty/None url is allowed (caller may skip the field).
    """
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="base_url scheme must be http or https")
    host = (parsed.hostname or "").lower()
    if not host:
        raise HTTPException(status_code=400, detail="base_url missing host")

    # Reject private/link-local IPs directly
    try:
        addr = ipaddress.ip_address(host)
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                raise HTTPException(status_code=400, detail="base_url targets a private/internal address")
    except ValueError:
        pass  # not a bare IP — continue to host allowlist

    if host not in _ALLOWED_HOSTS:
        raise HTTPException(
            status_code=400,
            detail=f"base_url host '{host}' is not in the provider allowlist",
        )
