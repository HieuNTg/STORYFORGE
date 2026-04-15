"""Tests for Z.AI provider detection and model validation."""

import unittest


class TestZaiProviderDetection(unittest.TestCase):
    """Tests for _detect_provider_type with Z.AI URLs."""

    def test_zai_api_url(self):
        from services.llm.client import _detect_provider_type
        result = _detect_provider_type("https://api.z.ai/api/paas/v4")
        self.assertEqual(result, "zai")

    def test_zai_url_case_insensitive(self):
        from services.llm.client import _detect_provider_type
        result = _detect_provider_type("https://API.Z.AI/api/paas/v4")
        self.assertEqual(result, "zai")

    def test_zai_with_trailing_slash(self):
        from services.llm.client import _detect_provider_type
        result = _detect_provider_type("https://api.z.ai/api/paas/v4/")
        self.assertEqual(result, "zai")


class TestZaiModelValidation(unittest.TestCase):
    """Tests for _model_matches_provider with Z.AI models."""

    def test_glm_47_flash_valid(self):
        from services.llm.client import _model_matches_provider
        result = _model_matches_provider("glm-4.7-flash", "zai")
        self.assertTrue(result)

    def test_glm_45_flash_valid(self):
        from services.llm.client import _model_matches_provider
        result = _model_matches_provider("glm-4.5-flash", "zai")
        self.assertTrue(result)

    def test_glm_46v_flash_valid(self):
        from services.llm.client import _model_matches_provider
        result = _model_matches_provider("glm-4.6v-flash", "zai")
        self.assertTrue(result)

    def test_openrouter_format_invalid_for_zai(self):
        from services.llm.client import _model_matches_provider
        # OpenRouter format with slash should NOT match Z.AI
        result = _model_matches_provider("vendor/glm-4.7-flash", "zai")
        self.assertFalse(result)

    def test_colon_format_invalid_for_zai(self):
        from services.llm.client import _model_matches_provider
        # Format with colon should NOT match Z.AI
        result = _model_matches_provider("glm-4.7-flash:free", "zai")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
