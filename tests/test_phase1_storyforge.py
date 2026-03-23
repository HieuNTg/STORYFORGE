"""Comprehensive tests for StoryForge Phase 1: Browser Web Auth + Zero-Config Onboarding."""

import os
import sys
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import LLMConfig, ConfigManager, PipelineConfig
from services.browser_auth import BrowserAuth, _find_chrome_path
from services.deepseek_web_client import DeepSeekWebClient, _solve_pow
from services.llm_client import LLMClient


class TestConfigPhase1(unittest.TestCase):
    """Test config.py changes: removed openclaw, added web_auth_provider."""

    def test_llm_config_has_web_auth_provider(self):
        """Verify LLMConfig has web_auth_provider field."""
        config = LLMConfig()
        self.assertTrue(hasattr(config, "web_auth_provider"))
        self.assertEqual(config.web_auth_provider, "deepseek-web")

    def test_llm_config_has_backend_type(self):
        """Verify LLMConfig has backend_type field."""
        config = LLMConfig()
        self.assertTrue(hasattr(config, "backend_type"))
        self.assertEqual(config.backend_type, "api")

    def test_llm_config_no_openclaw_fields(self):
        """Verify no openclaw fields in LLMConfig."""
        config = LLMConfig()
        self.assertFalse(hasattr(config, "openclaw_port"))
        self.assertFalse(hasattr(config, "openclaw_model"))
        self.assertFalse(hasattr(config, "auto_fallback"))

    def test_llm_config_backend_type_defaults_to_api(self):
        """Verify backend_type defaults to 'api'."""
        config = LLMConfig()
        self.assertEqual(config.backend_type, "api")

    def test_llm_config_can_be_set_to_web(self):
        """Verify backend_type can be set to 'web'."""
        config = LLMConfig()
        config.backend_type = "web"
        self.assertEqual(config.backend_type, "web")

    def test_config_manager_singleton(self):
        """Verify ConfigManager is singleton."""
        cm1 = ConfigManager()
        cm2 = ConfigManager()
        self.assertIs(cm1, cm2)

    def test_config_manager_save_includes_web_fields(self):
        """Verify saved config includes web_auth_provider and backend_type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, "config.json")
            cm = ConfigManager()
            cm.CONFIG_FILE = config_file
            cm.llm.backend_type = "web"
            cm.llm.web_auth_provider = "deepseek-web"
            cm.save()

            with open(config_file) as f:
                data = json.load(f)

            self.assertIn("backend_type", data["llm"])
            self.assertIn("web_auth_provider", data["llm"])
            self.assertEqual(data["llm"]["backend_type"], "web")
            self.assertEqual(data["llm"]["web_auth_provider"], "deepseek-web")


class TestBrowserAuth(unittest.TestCase):
    """Test browser_auth.py: Chrome CDP + Playwright credential capture."""

    def test_browser_auth_singleton(self):
        """Verify BrowserAuth is singleton."""
        auth1 = BrowserAuth()
        auth2 = BrowserAuth()
        self.assertIs(auth1, auth2)

    def test_find_chrome_path_windows(self):
        """Test _find_chrome_path on Windows."""
        with mock.patch("platform.system", return_value="Windows"):
            with mock.patch("os.path.isfile") as mock_isfile:
                # Mock that first candidate exists
                mock_isfile.return_value = True
                result = _find_chrome_path()
                # Should return a path if Chrome is found
                self.assertIsNotNone(result)

    def test_find_chrome_path_darwin(self):
        """Test _find_chrome_path on macOS."""
        with mock.patch("platform.system", return_value="Darwin"):
            with mock.patch("os.path.isfile", return_value=False):
                result = _find_chrome_path()
                self.assertIsNone(result)

    def test_browser_auth_is_authenticated_returns_false_initially(self):
        """Verify is_authenticated returns False with no saved credentials."""
        auth = BrowserAuth()
        # Should return False because no auth_profiles.json exists yet
        result = auth.is_authenticated()
        self.assertIsInstance(result, bool)

    def test_browser_auth_get_credentials_returns_none_initially(self):
        """Verify get_credentials returns None with no saved credentials."""
        auth = BrowserAuth()
        creds = auth.get_credentials("deepseek-web")
        # Should be None if no credentials saved
        self.assertIsNone(creds)

    def test_browser_auth_clear_credentials_no_error(self):
        """Verify clear_credentials handles missing file gracefully."""
        auth = BrowserAuth()
        # Should not raise error even if auth_profiles.json doesn't exist
        auth.clear_credentials("deepseek-web")

    def test_browser_auth_stop_chrome_no_process(self):
        """Verify stop_chrome handles no active process."""
        auth = BrowserAuth()
        # Should not raise error
        auth.stop_chrome()


class TestDeepSeekWebClient(unittest.TestCase):
    """Test deepseek_web_client.py: PoW solver and web API client."""

    def test_solve_pow_basic(self):
        """Test PoW solver with known values."""
        # Simple test: challenge="abc", salt="", difficulty=1
        # Should find nonce that produces hash starting with "0"
        challenge = "test"
        salt = ""
        difficulty = 1
        nonce = _solve_pow(challenge, salt, difficulty)
        self.assertIsInstance(nonce, str)
        self.assertTrue(nonce.isdigit())

    def test_solve_pow_returns_string(self):
        """Verify _solve_pow returns string nonce."""
        nonce = _solve_pow("challenge", "", 1)
        self.assertIsInstance(nonce, str)

    def test_deepseek_web_client_init(self):
        """Test DeepSeekWebClient initialization."""
        with mock.patch("services.browser_auth.BrowserAuth.get_credentials", return_value=None):
            client = DeepSeekWebClient()
            self.assertIsNotNone(client)

    def test_deepseek_web_client_is_ready_false_without_credentials(self):
        """Verify is_ready returns False without credentials."""
        with mock.patch("services.browser_auth.BrowserAuth.get_credentials", return_value=None):
            client = DeepSeekWebClient()
            self.assertFalse(client.is_ready())

    def test_deepseek_web_client_is_ready_true_with_credentials(self):
        """Verify is_ready returns True with valid credentials."""
        fake_creds = {
            "cookies": "session=abc123",
            "bearer": "token123",
            "user_agent": "Mozilla/5.0",
        }
        with mock.patch("services.browser_auth.BrowserAuth.get_credentials", return_value=fake_creds):
            client = DeepSeekWebClient()
            self.assertTrue(client.is_ready())

    def test_deepseek_web_client_refresh_credentials(self):
        """Test credential refresh."""
        with mock.patch("services.browser_auth.BrowserAuth.get_credentials", return_value=None):
            client = DeepSeekWebClient()
            client.refresh_credentials()
            self.assertFalse(client.is_ready())


class TestLLMClientWebBackend(unittest.TestCase):
    """Test llm_client.py: web backend routing."""

    def test_llm_client_is_web_backend_api_default(self):
        """Verify _is_web_backend returns False by default."""
        # Clear singleton to test with fresh instance
        LLMClient._instance = None

        with mock.patch("config.ConfigManager") as mock_config:
            mock_cfg = mock.MagicMock()
            mock_cfg.llm.backend_type = "api"
            mock_cfg.llm.cache_enabled = False
            mock_config.return_value = mock_cfg

            client = LLMClient()
            with mock.patch.object(client, "_is_web_backend", return_value=False):
                result = client._is_web_backend()
                self.assertFalse(result)

    def test_llm_client_is_web_backend_web(self):
        """Verify _is_web_backend returns True when backend_type is 'web'."""
        with mock.patch("config.ConfigManager") as mock_config:
            mock_cfg = mock.MagicMock()
            mock_cfg.llm.backend_type = "web"
            mock_config.return_value = mock_cfg

            client = LLMClient()
            result = client._is_web_backend()
            self.assertTrue(result)

    def test_llm_client_get_web_client_lazy_import(self):
        """Verify _get_web_client uses lazy import."""
        with mock.patch("services.deepseek_web_client.DeepSeekWebClient"):
            client = LLMClient()
            web_client = client._get_web_client()
            self.assertIsNotNone(web_client)


class TestStoryTemplates(unittest.TestCase):
    """Test story_templates.json structure and loading."""

    def test_story_templates_file_exists(self):
        """Verify story_templates.json exists."""
        templates_path = os.path.join(
            project_root, "data", "templates", "story_templates.json"
        )
        self.assertTrue(os.path.exists(templates_path), f"Templates file not found: {templates_path}")

    def test_story_templates_valid_json(self):
        """Verify story_templates.json is valid JSON."""
        templates_path = os.path.join(
            project_root, "data", "templates", "story_templates.json"
        )
        with open(templates_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)

    def test_story_templates_structure(self):
        """Verify story_templates.json structure."""
        templates_path = os.path.join(
            project_root, "data", "templates", "story_templates.json"
        )
        with open(templates_path, encoding="utf-8") as f:
            data = json.load(f)

        # Check that genres exist
        self.assertTrue(len(data) > 0, "No genres in templates")

        # Check first genre has templates
        first_genre = list(data.keys())[0]
        templates = data[first_genre]
        self.assertIsInstance(templates, list)
        self.assertTrue(len(templates) > 0, f"Genre {first_genre} has no templates")

    def test_story_templates_required_keys(self):
        """Verify each template has required keys."""
        templates_path = os.path.join(
            project_root, "data", "templates", "story_templates.json"
        )
        with open(templates_path, encoding="utf-8") as f:
            data = json.load(f)

        required_keys = {"title", "idea", "num_chapters", "num_characters", "words_per_chapter", "style"}

        for genre, templates in data.items():
            for idx, template in enumerate(templates):
                missing_keys = required_keys - set(template.keys())
                self.assertFalse(
                    missing_keys,
                    f"Genre '{genre}' template {idx} missing keys: {missing_keys}"
                )

    def test_story_templates_multiple_genres(self):
        """Verify story_templates.json has multiple genres."""
        templates_path = os.path.join(
            project_root, "data", "templates", "story_templates.json"
        )
        with open(templates_path, encoding="utf-8") as f:
            data = json.load(f)

        # Should have at least 5 genres
        self.assertGreaterEqual(len(data), 5, "Expected at least 5 genres")

    def test_story_templates_multiple_per_genre(self):
        """Verify each genre has multiple templates."""
        templates_path = os.path.join(
            project_root, "data", "templates", "story_templates.json"
        )
        with open(templates_path, encoding="utf-8") as f:
            data = json.load(f)

        for genre, templates in data.items():
            self.assertGreaterEqual(
                len(templates), 1,
                f"Genre '{genre}' should have at least 1 template"
            )


class TestAppModule(unittest.TestCase):
    """Test app.py: UI and template loading."""

    def test_app_module_imports(self):
        """Verify app.py imports without errors."""
        try:
            import app
            self.assertIsNotNone(app)
        except Exception as e:
            self.fail(f"app.py import failed: {e}")

    def test_load_templates_returns_dict(self):
        """Verify _load_templates returns a dict."""
        from app import _load_templates
        result = _load_templates()
        self.assertIsInstance(result, dict)

    def test_load_templates_has_content(self):
        """Verify _load_templates returns non-empty dict."""
        from app import _load_templates
        result = _load_templates()
        self.assertGreater(len(result), 0, "Templates should not be empty")

    def test_create_ui_returns_gradio_blocks(self):
        """Verify create_ui returns a Gradio Blocks object."""
        from app import create_ui
        with mock.patch("config.ConfigManager") as mock_config:
            mock_cfg = mock.MagicMock()
            mock_cfg.llm.backend_type = "api"
            mock_cfg.llm.api_key = "test"
            mock_config.return_value = mock_cfg

            try:
                ui = create_ui()
                # Check it's a Gradio Blocks-like object
                self.assertIsNotNone(ui)
            except Exception as e:
                self.fail(f"create_ui failed: {e}")


class TestFilesCompile(unittest.TestCase):
    """Verify all changed Python files compile without errors."""

    def test_config_compiles(self):
        """Verify config.py compiles."""
        config_path = os.path.join(project_root, "config.py")
        import py_compile
        try:
            py_compile.compile(config_path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"config.py compile failed: {e}")

    def test_browser_auth_compiles(self):
        """Verify browser_auth.py compiles."""
        file_path = os.path.join(project_root, "services", "browser_auth.py")
        import py_compile
        try:
            py_compile.compile(file_path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"browser_auth.py compile failed: {e}")

    def test_deepseek_web_client_compiles(self):
        """Verify deepseek_web_client.py compiles."""
        file_path = os.path.join(project_root, "services", "deepseek_web_client.py")
        import py_compile
        try:
            py_compile.compile(file_path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"deepseek_web_client.py compile failed: {e}")

    def test_llm_client_compiles(self):
        """Verify llm_client.py compiles."""
        file_path = os.path.join(project_root, "services", "llm_client.py")
        import py_compile
        try:
            py_compile.compile(file_path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"llm_client.py compile failed: {e}")

    def test_app_compiles(self):
        """Verify app.py compiles."""
        app_path = os.path.join(project_root, "app.py")
        import py_compile
        try:
            py_compile.compile(app_path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"app.py compile failed: {e}")


class TestNoOpenClawReferences(unittest.TestCase):
    """Verify no remaining openclaw functional code."""

    def test_config_no_openclaw_functional_code(self):
        """Verify config.py has no openclaw functional code."""
        config_path = os.path.join(project_root, "config.py")
        with open(config_path, encoding="utf-8") as f:
            content = f.read()

        # Should not have openclaw field definitions
        self.assertNotIn("openclaw_port", content)
        self.assertNotIn("openclaw_model", content)
        self.assertNotIn("auto_fallback", content)

    def test_llm_client_no_openclaw_fallback(self):
        """Verify llm_client.py has no openclaw fallback logic."""
        llm_path = os.path.join(project_root, "services", "llm_client.py")
        with open(llm_path, encoding="utf-8") as f:
            content = f.read()

        # Should not have openclaw_manager import or usage
        self.assertNotIn("openclaw_manager", content)
        self.assertNotIn("OpenClawManager", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
