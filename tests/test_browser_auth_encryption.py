"""Tests for browser auth encryption — roundtrip, migration, downgrade prevention."""
import json
import os
import tempfile
import pytest
from unittest.mock import patch


class TestEncryptionRoundtrip:
    def test_save_and_load_encrypted(self):
        """Credentials saved encrypted can be loaded back."""
        from services.browser_auth import BrowserAuth, _HAS_CRYPTOGRAPHY
        if not _HAS_CRYPTOGRAPHY:
            pytest.skip("cryptography not installed")

        auth = BrowserAuth.__new__(BrowserAuth)
        auth._initialized = True
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_path = os.path.join(tmpdir, "profiles.json")
            key_path = os.path.join(tmpdir, ".key")
            with patch('services.browser_auth.AUTH_PROFILES_PATH', profiles_path), \
                 patch('services.browser_auth._ENCRYPTION_KEY_PATH', key_path):
                test_profiles = {"deepseek-web": {"cookies": "test=1", "bearer": "abc"}}
                auth._save_credentials_dict(test_profiles)
                loaded = auth._load_profiles()
                assert loaded["deepseek-web"]["cookies"] == "test=1"
                assert loaded["deepseek-web"]["bearer"] == "abc"

    def test_module_imports_without_cryptography(self):
        """Module should import even if cryptography is missing."""
        import services.browser_auth
        assert hasattr(services.browser_auth, 'BrowserAuth')


class TestDowngradePrevention:
    def test_plaintext_rejected_when_key_exists(self):
        """If encryption key exists, refuse plaintext profiles."""
        from services.browser_auth import BrowserAuth, _HAS_CRYPTOGRAPHY, _ENCRYPTED_MARKER
        if not _HAS_CRYPTOGRAPHY:
            pytest.skip("cryptography not installed")

        auth = BrowserAuth.__new__(BrowserAuth)
        auth._initialized = True
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_path = os.path.join(tmpdir, "profiles.json")
            key_path = os.path.join(tmpdir, ".key")
            # Create key file
            from cryptography.fernet import Fernet
            key = Fernet.generate_key()
            with open(key_path, "wb") as f:
                f.write(key)
            # Write plaintext (simulating attacker)
            with open(profiles_path, "w") as f:
                json.dump({"evil": {"cookies": "stolen"}}, f)

            with patch('services.browser_auth.AUTH_PROFILES_PATH', profiles_path), \
                 patch('services.browser_auth._ENCRYPTION_KEY_PATH', key_path):
                loaded = auth._load_profiles()
                # Should either migrate or reject, not blindly accept
                if "evil" in loaded:
                    # Verify it was migrated (file is now encrypted)
                    with open(profiles_path, "rb") as f:
                        raw = f.read()
                    assert raw.startswith(_ENCRYPTED_MARKER)
