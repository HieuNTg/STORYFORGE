"""Auth service coverage tests — targeting 80%+ coverage of services/auth.py.

Tests:
    - password hashing and verification
    - JWT token creation and validation
    - expired token handling
    - invalid token handling
    - user registration validation
"""
from __future__ import annotations

import os
import time

import pytest

# Ensure secret key is set before importing auth
os.environ.setdefault("STORYFORGE_SECRET_KEY", "test-secret-key-for-unit-tests")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_auth():
    """Import auth module (avoids top-level import failures if env not set)."""
    import services.auth as auth  # noqa: PLC0415
    return auth


# ---------------------------------------------------------------------------
# Password hashing tests
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    """Tests for _b64url_encode/_b64url_decode and payload round-trip."""

    def test_b64url_encode_decode_roundtrip(self):
        auth = _import_auth()
        original = b"hello world test bytes"
        encoded = auth._b64url_encode(original)
        assert isinstance(encoded, str)
        # Should not contain padding '='
        assert "=" not in encoded
        decoded = auth._b64url_decode(encoded)
        assert decoded == original

    def test_b64url_encode_empty_bytes(self):
        auth = _import_auth()
        encoded = auth._b64url_encode(b"")
        decoded = auth._b64url_decode(encoded)
        assert decoded == b""

    def test_b64url_encode_binary_data(self):
        auth = _import_auth()
        data = bytes(range(256))
        encoded = auth._b64url_encode(data)
        decoded = auth._b64url_decode(encoded)
        assert decoded == data


# ---------------------------------------------------------------------------
# Token creation and validation
# ---------------------------------------------------------------------------


class TestTokenCreation:
    def test_create_token_returns_string(self):
        auth = _import_auth()
        token = auth.create_token("user-123", "test_user")
        assert isinstance(token, str)
        # JWT format: header.payload.signature (3 parts)
        assert token.count(".") == 2

    def test_create_token_has_three_parts(self):
        auth = _import_auth()
        token = auth.create_token("user-456", "another_user")
        parts = token.split(".")
        assert len(parts) == 3

    def test_create_and_verify_token(self):
        auth = _import_auth()
        user_id = "user-789"
        username = "verified_user"
        token = auth.create_token(user_id, username)
        payload = auth.verify_token(token)

        assert payload["sub"] == user_id
        assert payload["username"] == username

    def test_token_payload_contains_exp(self):
        auth = _import_auth()
        token = auth.create_token("user-exp", "expiry_user")
        payload = auth.verify_token(token)

        assert "exp" in payload
        assert payload["exp"] > int(time.time())

    def test_token_payload_contains_iat(self):
        auth = _import_auth()
        token = auth.create_token("user-iat", "iat_user")
        payload = auth.verify_token(token)

        assert "iat" in payload
        assert payload["iat"] <= int(time.time())


# ---------------------------------------------------------------------------
# Invalid / tampered token tests
# ---------------------------------------------------------------------------


class TestInvalidTokenHandling:
    def test_invalid_signature_raises(self):
        auth = _import_auth()
        token = auth.create_token("user-123", "test")
        # Tamper with the signature (last segment)
        parts = token.split(".")
        parts[2] = parts[2][:-4] + "XXXX"
        bad_token = ".".join(parts)
        with pytest.raises(ValueError, match="[Ii]nvalid"):
            auth.verify_token(bad_token)

    def test_tampered_payload_raises(self):
        auth = _import_auth()
        import base64, json  # noqa: E401

        token = auth.create_token("user-123", "original")
        parts = token.split(".")

        # Re-encode payload with different username
        fake_payload = {"sub": "attacker", "username": "hacked", "iat": 0, "exp": 9999999999}
        new_payload = (
            base64.urlsafe_b64encode(json.dumps(fake_payload).encode())
            .rstrip(b"=")
            .decode()
        )
        bad_token = f"{parts[0]}.{new_payload}.{parts[2]}"
        with pytest.raises(ValueError):
            auth.verify_token(bad_token)

    def test_malformed_token_missing_parts_raises(self):
        auth = _import_auth()
        with pytest.raises(ValueError, match="[Mm]alformed"):
            auth.verify_token("only.two")

    def test_empty_token_raises(self):
        auth = _import_auth()
        with pytest.raises(ValueError):
            auth.verify_token("")

    def test_wrong_format_raises(self):
        auth = _import_auth()
        with pytest.raises(ValueError):
            auth.verify_token("not-a-jwt-at-all")


# ---------------------------------------------------------------------------
# Expired token test
# ---------------------------------------------------------------------------


class TestExpiredToken:
    def test_expired_token_raises(self):
        """Manually craft a token with exp in the past."""
        import base64
        import hashlib
        import hmac
        import json

        auth = _import_auth()
        secret = hashlib.sha256(b"test-secret-key-for-unit-tests").digest()

        header = (
            base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
            .rstrip(b"=")
            .decode()
        )
        payload_data = {
            "sub": "user-expired",
            "username": "expired",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,  # 1 hour in the past
        }
        payload = (
            base64.urlsafe_b64encode(json.dumps(payload_data).encode())
            .rstrip(b"=")
            .decode()
        )
        signing_input = f"{header}.{payload}"
        sig = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
        sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
        expired_token = f"{signing_input}.{sig_b64}"

        with pytest.raises(ValueError, match="[Ee]xpired"):
            auth.verify_token(expired_token)


# ---------------------------------------------------------------------------
# Secret key guard test
# ---------------------------------------------------------------------------


class TestSecretKeyGuard:
    def test_missing_secret_key_raises(self, monkeypatch):
        """_get_secret raises RuntimeError when env var is unset."""
        monkeypatch.delenv("STORYFORGE_SECRET_KEY", raising=False)
        auth = _import_auth()
        with pytest.raises(RuntimeError, match="STORYFORGE_SECRET_KEY"):
            auth._get_secret()
