"""Regression tests for services/security/url_validator.py.

The bug these pin down: a fixed vendor allowlist rejected every custom
OpenAI-compatible endpoint with 400, so the Settings UI could never save one —
while the SSRF protection that actually matters (private/link-local targets)
must stay on.
"""

import ipaddress

import pytest
from fastapi import HTTPException

from services.security import url_validator
from services.security.url_validator import validate_base_url


def _resolve_to(monkeypatch, addr: str):
    monkeypatch.setattr(
        url_validator,
        "_resolved_addresses",
        lambda host: [ipaddress.ip_address(addr)],
    )


class TestCustomHostsAllowed:
    def test_unknown_public_host_is_accepted(self, monkeypatch):
        _resolve_to(monkeypatch, "203.0.113.10")
        validate_base_url("https://llm.example.com/v1")  # must not raise

    def test_known_vendor_still_accepted(self, monkeypatch):
        _resolve_to(monkeypatch, "203.0.113.11")
        validate_base_url("https://api.openai.com/v1")

    def test_public_bare_ip_accepted(self):
        validate_base_url("https://203.0.113.12:8080/v1")

    def test_localhost_bridge_accepted(self):
        # config/presets.py ships a localhost:8000 card — it must keep working.
        validate_base_url("http://localhost:8000/v1")
        validate_base_url("http://127.0.0.1:8000/v1")

    def test_unresolvable_host_is_not_rejected(self, monkeypatch):
        monkeypatch.setattr(url_validator, "_resolved_addresses", lambda host: [])
        validate_base_url("https://offline.example.com/v1")

    def test_empty_url_is_a_no_op(self):
        validate_base_url("")


class TestSsrfStillBlocked:
    @pytest.mark.parametrize(
        "url",
        [
            "http://192.168.1.50:11434/v1",
            "http://10.1.2.3/v1",
            "http://169.254.169.254/latest/meta-data",  # cloud metadata
            "http://172.16.4.4/v1",
        ],
    )
    def test_private_bare_ip_rejected(self, url):
        with pytest.raises(HTTPException) as exc:
            validate_base_url(url)
        assert exc.value.status_code == 400

    def test_hostname_resolving_to_private_rejected(self, monkeypatch):
        _resolve_to(monkeypatch, "169.254.169.254")
        with pytest.raises(HTTPException) as exc:
            validate_base_url("https://evil.example.com/v1")
        assert exc.value.status_code == 400

    def test_non_http_scheme_rejected(self):
        with pytest.raises(HTTPException):
            validate_base_url("file:///etc/passwd")

    def test_missing_host_rejected(self):
        with pytest.raises(HTTPException):
            validate_base_url("https:///v1")


class TestPrivateOptIn:
    def test_env_flag_lifts_the_private_block(self, monkeypatch):
        monkeypatch.setenv("STORYFORGE_ALLOW_PRIVATE_BASE_URL", "1")
        validate_base_url("http://192.168.1.50:11434/v1")  # LAN Ollama box

    def test_flag_off_by_default(self, monkeypatch):
        monkeypatch.delenv("STORYFORGE_ALLOW_PRIVATE_BASE_URL", raising=False)
        with pytest.raises(HTTPException):
            validate_base_url("http://192.168.1.50:11434/v1")


class TestProviderPresets:
    def test_kyma_and_zai_cards_are_gone(self):
        from config import PROVIDER_PRESETS

        names = {p["name"] for p in PROVIDER_PRESETS}
        assert "Kyma" not in names
        assert "Z.AI" not in names

    def test_custom_card_is_offered(self):
        from config import PROVIDER_PRESETS

        custom = [p for p in PROVIDER_PRESETS if p.get("custom")]
        assert len(custom) == 1
        assert custom[0]["base_url"] == ""
        assert custom[0]["models"] == []
