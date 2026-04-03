"""Regression tests for StoryForge Phase 1 (browser auth removed in v4.0)."""

import os
import sys
import json
import unittest
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import LLMConfig, ConfigManager  # noqa: E402
from services.llm_client import LLMClient  # noqa: E402


class TestConfigPhase1(unittest.TestCase):
    """Test config.py — basic LLMConfig fields."""

    def test_llm_config_no_openclaw_fields(self):
        """Verify no openclaw fields in LLMConfig."""
        config = LLMConfig()
        self.assertFalse(hasattr(config, "openclaw_port"))
        self.assertFalse(hasattr(config, "openclaw_model"))
        self.assertFalse(hasattr(config, "auto_fallback"))

    def test_llm_config_no_web_auth_fields(self):
        """Verify web auth fields removed from LLMConfig."""
        config = LLMConfig()
        self.assertFalse(hasattr(config, "web_auth_provider"))
        self.assertFalse(hasattr(config, "backend_type"))

    def test_config_manager_singleton(self):
        """Verify ConfigManager is singleton."""
        cm1 = ConfigManager()
        cm2 = ConfigManager()
        self.assertIs(cm1, cm2)


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

        self.assertGreaterEqual(len(data), 5, "Expected at least 5 genres")

    def test_story_templates_multiple_per_genre(self):
        """Verify each genre has at least 1 template."""
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
        """Skipped — Gradio UI archived."""
        self.skipTest("ui.gradio_app archived — Gradio UI removed")

    def test_load_templates_has_content(self):
        """Skipped — Gradio UI archived."""
        self.skipTest("ui.gradio_app archived — Gradio UI removed")

    def test_create_ui_returns_gradio_blocks(self):
        """Skipped — Gradio UI archived."""
        self.skipTest("ui.gradio_app archived — Gradio UI removed")


class TestFilesCompile(unittest.TestCase):
    """Verify all key Python files compile without errors."""

    def test_config_compiles(self):
        """Verify config package compiles (config.py replaced by config/ package)."""
        config_path = os.path.join(project_root, "config", "__init__.py")
        import py_compile
        try:
            py_compile.compile(config_path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"config/__init__.py compile failed: {e}")

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

    def test_browser_auth_files_removed(self):
        """Verify deprecated browser auth files are gone."""
        removed = [
            os.path.join(project_root, "services", "browser_auth.py"),
            os.path.join(project_root, "services", "deepseek_web_client.py"),
        ]
        for path in removed:
            self.assertFalse(os.path.exists(path), f"Deprecated file still exists: {path}")
        ba_pkg = os.path.join(project_root, "services", "browser_auth", "__init__.py")
        self.assertFalse(os.path.exists(ba_pkg), "browser_auth package still exists")


class TestNoOpenClawReferences(unittest.TestCase):
    """Verify no remaining openclaw functional code."""

    def test_config_no_openclaw_functional_code(self):
        """Verify config package has no openclaw functional code."""
        config_path = os.path.join(project_root, "config", "__init__.py")
        with open(config_path, encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("openclaw_port", content)
        self.assertNotIn("openclaw_model", content)
        self.assertNotIn("auto_fallback", content)

    def test_llm_client_no_openclaw_fallback(self):
        """Verify llm_client.py has no openclaw fallback logic."""
        llm_path = os.path.join(project_root, "services", "llm_client.py")
        with open(llm_path, encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("openclaw_manager", content)
        self.assertNotIn("OpenClawManager", content)

    def test_llm_client_no_web_backend(self):
        """Verify llm_client.py has no web backend code."""
        llm_path = os.path.join(project_root, "services", "llm_client.py")
        with open(llm_path, encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("browser_auth", content)
        self.assertNotIn("deepseek_web_client", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
