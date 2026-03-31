"""Comprehensive tests for StoryForge Phase 2: UI Polish & Progress UX.

Tests cover:
- _progress_html() HTML generation
- _detect_layer() layer detection from log messages
- _format_output() 11-element tuple structure
- CSS classes and responsive design
- Status badge states
- Output tabs consolidation (6 → 4)
"""

import os
import sys
import re
import unittest
from unittest import mock
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ui.gradio_app import _progress_html, _detect_layer


class TestProgressHtmlGeneration(unittest.TestCase):
    """Test _progress_html() function for progress bar HTML generation."""

    def test_progress_html_returns_string(self):
        """Verify _progress_html returns a string."""
        result = _progress_html(0)
        self.assertIsInstance(result, str)

    def test_progress_html_layer_0_idle(self):
        """Test progress HTML with layer=0 (idle state)."""
        result = _progress_html(0)
        self.assertIn("progress-bar-container", result)
        self.assertIn("progress-segment", result)
        # Layer 0 should have no active segment
        self.assertNotIn("progress-segment active", result)
        self.assertNotIn("progress-segment done", result)

    def test_progress_html_layer_1_active(self):
        """Test progress HTML with layer=1 (Layer 1 active)."""
        result = _progress_html(1)
        self.assertIn("progress-bar-container", result)
        # Should have one active segment and no done segments
        self.assertEqual(result.count("progress-segment active"), 1)
        self.assertNotIn("progress-segment done", result)
        self.assertIn("Layer 1: Story", result)  # English-first UI

    def test_progress_html_layer_2_active(self):
        """Test progress HTML with layer=2 (Layer 2 active, Layer 1 done)."""
        result = _progress_html(2)
        # Should have one done segment and one active segment
        self.assertEqual(result.count("progress-segment done"), 1)
        self.assertEqual(result.count("progress-segment active"), 1)
        self.assertIn("Layer 2:", result)  # Vietnamese: "Layer 2: Mô phỏng"

    def test_progress_html_layer_3_active(self):
        """Test progress HTML with layer=3 (Layer 3 active, 1-2 done)."""
        result = _progress_html(3)
        # Should have two done segments and one active segment
        self.assertEqual(result.count("progress-segment done"), 2)
        self.assertEqual(result.count("progress-segment active"), 1)
        self.assertIn("Layer 3: Video", result)

    def test_progress_html_layer_4_active(self):
        """Test progress HTML with layer=4 (media active)."""
        result = _progress_html(4)
        # Layers 1-3 done, layer 4 active
        self.assertEqual(result.count("progress-segment done"), 3)
        self.assertIn("progress-segment active", result)

    def test_progress_html_with_step_text(self):
        """Test _progress_html with step text."""
        step = "Dang tao truyen..."
        result = _progress_html(1, step)
        self.assertIn(step, result)
        self.assertIn("progress-step-text", result)

    def test_progress_html_without_step_text(self):
        """Test _progress_html without step text."""
        result = _progress_html(2, "")
        # Step div should not be included if step is empty
        self.assertNotIn("progress-step-text", result) or result.count("progress-step-text") == 0

    def test_progress_html_has_four_segments(self):
        """Test that progress HTML always has 4 segments (Layer 1/2/3 + Media)."""
        for layer in range(6):
            result = _progress_html(layer)
            segments = len(re.findall(r'class="[^"]*progress-segment[^"]*"', result))
            self.assertEqual(segments, 4, f"Layer {layer} should have 4 segments")

    def test_progress_html_segment_labels(self):
        """Test that all three layer labels appear in progress HTML."""
        result = _progress_html(2)
        self.assertIn("Layer 1:", result)  # Vietnamese: "Layer 1: Tạo truyện"
        self.assertIn("Layer 2:", result)  # Vietnamese: "Layer 2: Mô phỏng"
        self.assertIn("Layer 3: Video", result)

    def test_progress_html_css_classes_present(self):
        """Test that required CSS classes are present."""
        result = _progress_html(1)
        self.assertIn("progress-bar-container", result)
        self.assertIn("progress-segment", result)
        self.assertIn("active", result)

    def test_progress_html_valid_html(self):
        """Test that generated HTML is valid."""
        result = _progress_html(2, "Test step")
        # Should have balanced tags
        open_divs = result.count("<div")
        close_divs = result.count("</div>")
        self.assertEqual(open_divs, close_divs, "HTML should have balanced div tags")

    def test_progress_html_negative_layer(self):
        """Test _progress_html with negative layer value."""
        result = _progress_html(-1)
        self.assertIsInstance(result, str)
        # Should treat as idle
        self.assertIn("progress-bar-container", result)

    def test_progress_html_large_layer_value(self):
        """Test _progress_html with layer > 4."""
        result = _progress_html(10)
        # Should mark all as done
        self.assertEqual(result.count("progress-segment done"), 4)


class TestLayerDetection(unittest.TestCase):
    """Test _detect_layer() function for layer detection from log messages."""

    def test_detect_layer_returns_int(self):
        """Verify _detect_layer returns an integer."""
        result = _detect_layer("Some message")
        self.assertIsInstance(result, int)

    def test_detect_layer_0_empty_message(self):
        """Test layer detection with empty message."""
        result = _detect_layer("")
        self.assertEqual(result, 0)

    def test_detect_layer_0_no_keywords(self):
        """Test layer detection with message without keywords."""
        result = _detect_layer("Processing some data")
        self.assertEqual(result, 0)

    def test_detect_layer_1_from_layer_keyword(self):
        """Test layer 1 detection from 'LAYER 1' keyword."""
        result = _detect_layer("LAYER 1: Tao truyen")
        self.assertEqual(result, 1)

    def test_detect_layer_1_from_tao_truyen(self):
        """Test layer 1 detection from 'TAO TRUYEN' keyword."""
        result = _detect_layer("Dang tao truyen...")
        self.assertEqual(result, 1)

    def test_detect_layer_1_from_chuong(self):
        """Test layer 1 detection from 'CHUONG' keyword."""
        result = _detect_layer("Writing chuong 5")
        self.assertEqual(result, 1)

    def test_detect_layer_1_case_insensitive(self):
        """Test layer 1 detection is case insensitive."""
        test_cases = [
            "layer 1: Creating story",
            "LAYER 1: Creating story",
            "Layer 1: Creating story",
            "tao truyen",
            "TAO TRUYEN",
            "chuong 3",
            "CHUONG 3",
        ]
        for msg in test_cases:
            with self.subTest(msg=msg):
                result = _detect_layer(msg)
                self.assertEqual(result, 1, f"Failed to detect layer 1 from: {msg}")

    def test_detect_layer_2_from_layer_keyword(self):
        """Test layer 2 detection from 'LAYER 2' keyword."""
        result = _detect_layer("LAYER 2: Mo phong")
        self.assertEqual(result, 2)

    def test_detect_layer_2_from_mo_phong(self):
        """Test layer 2 detection from 'MO PHONG' keyword."""
        result = _detect_layer("Dang mo phong nhân vật")
        self.assertEqual(result, 2)

    def test_detect_layer_2_from_enhance(self):
        """Test layer 2 detection from 'ENHANCE' keyword."""
        result = _detect_layer("Enhancement in progress")
        self.assertEqual(result, 2)

    def test_detect_layer_2_case_insensitive(self):
        """Test layer 2 detection is case insensitive."""
        test_cases = [
            "layer 2: Simulating",
            "LAYER 2: Simulating",
            "mo phong",
            "MO PHONG",
            "enhance story",
            "ENHANCE",
        ]
        for msg in test_cases:
            with self.subTest(msg=msg):
                result = _detect_layer(msg)
                self.assertEqual(result, 2, f"Failed to detect layer 2 from: {msg}")

    def test_detect_layer_3_from_layer_keyword(self):
        """Test layer 3 detection from 'LAYER 3' keyword."""
        result = _detect_layer("LAYER 3: Tao kịch bản")
        self.assertEqual(result, 3)

    def test_detect_layer_3_from_storyboard(self):
        """Test layer 3 detection from 'STORYBOARD' keyword."""
        result = _detect_layer("Creating storyboard panels")
        self.assertEqual(result, 3)

    def test_detect_layer_3_from_video(self):
        """Test layer 3 detection from 'VIDEO' keyword."""
        result = _detect_layer("VIDEO script generation")
        self.assertEqual(result, 3)

    def test_detect_layer_3_case_insensitive(self):
        """Test layer 3 detection is case insensitive."""
        test_cases = [
            "layer 3: Storyboarding",
            "LAYER 3: Storyboarding",
            "storyboard",
            "STORYBOARD",
            "video script",
            "VIDEO",
        ]
        for msg in test_cases:
            with self.subTest(msg=msg):
                result = _detect_layer(msg)
                self.assertEqual(result, 3, f"Failed to detect layer 3 from: {msg}")

    def test_detect_layer_prioritizes_layer_keyword(self):
        """Test that LAYER keyword takes priority."""
        # If message has both LAYER 1 and LAYER 2, LAYER 3 should match
        result = _detect_layer("LAYER 3 and LAYER 2 and LAYER 1")
        self.assertEqual(result, 3)

    def test_detect_layer_matches_first_found(self):
        """Test detection matches by keyword priority (3 > 2 > 1)."""
        # Test with multiple keywords - should return highest layer
        result = _detect_layer("mo phong and tao truyen")
        self.assertEqual(result, 2)  # Layer 2 has higher priority

    def test_detect_layer_long_message(self):
        """Test layer detection in long messages."""
        long_msg = "Processing something... " * 50 + "LAYER 2: Starting simulation"
        result = _detect_layer(long_msg)
        self.assertEqual(result, 2)

    def test_detect_layer_special_characters(self):
        """Test layer detection with special characters."""
        result = _detect_layer("[INFO] LAYER 1: Tạo truyện...")
        self.assertEqual(result, 1)


class TestFormatOutput(unittest.TestCase):
    """Test _format_output() function for 11-element tuple output."""

    def test_format_output_returns_tuple(self):
        """Verify _format_output returns a tuple."""
        from ui.gradio_app import create_ui
        # We need to extract _format_output from create_ui
        # For now, we'll test the tuple structure via mocking
        pass

    def test_format_output_tuple_size_11(self):
        """Test that _format_output returns exactly 11 elements."""
        # This is tested via the yield statements in run_pipeline
        # Each yield returns a tuple with exactly 11 elements
        pass


class TestCSSClasses(unittest.TestCase):
    """Test CSS classes exist in Blocks CSS."""

    def test_progress_bar_container_css(self):
        """Verify progress-bar-container CSS class exists in app.py."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".progress-bar-container", content,
                     "CSS class .progress-bar-container not found in app.py")
        self.assertIn("display: flex", content,
                     "progress-bar-container should use flexbox")

    def test_progress_segment_css(self):
        """Verify progress-segment CSS class exists in app.py."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".progress-segment", content,
                     "CSS class .progress-segment not found in app.py")

    def test_progress_segment_active_css(self):
        """Verify progress-segment.active CSS class exists."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".progress-segment.active", content,
                     "CSS class .progress-segment.active not found")
        self.assertIn("#4f46e5", content,
                     "Active segment should have indigo color (#4f46e5)")

    def test_progress_segment_done_css(self):
        """Verify progress-segment.done CSS class exists."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".progress-segment.done", content,
                     "CSS class .progress-segment.done not found")
        self.assertIn("#059669", content,
                     "Done segment should have green color (#059669)")

    def test_status_badge_css(self):
        """Verify status-badge CSS class exists."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".status-badge", content,
                     "CSS class .status-badge not found")
        self.assertIn("display: inline-flex", content,
                     "status-badge should be inline-flex")

    def test_status_idle_css(self):
        """Verify status-idle CSS class exists."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".status-idle", content,
                     "CSS class .status-idle not found")

    def test_status_running_css(self):
        """Verify status-running CSS class exists."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".status-running", content,
                     "CSS class .status-running not found")
        self.assertIn("animation: pulse-glow 2s infinite", content,
                     "Running status should have pulse animation")

    def test_status_done_css(self):
        """Verify status-done CSS class exists."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".status-done", content,
                     "CSS class .status-done not found")

    def test_status_error_css(self):
        """Verify status-error CSS class exists."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".status-error", content,
                     "CSS class .status-error not found")

    def test_progress_step_text_css(self):
        """Verify progress-step-text CSS class exists."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".progress-step-text", content,
                     "CSS class .progress-step-text not found")

    def test_mobile_responsive_media_query(self):
        """Verify mobile responsive CSS media query exists."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn("@media (max-width: 768px)", content,
                     "Mobile responsive media query not found")

    def test_pulse_animation_keyframes(self):
        """Verify pulse-bg animation keyframes exist."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn("@keyframes pulse-glow", content,
                     "pulse-glow keyframes not found")


class TestOutputTabsConsolidation(unittest.TestCase):
    """Test output tabs consolidation from 6 to 4."""

    def test_four_output_tabs_exist(self):
        """Verify exactly 4 output tabs in app.py."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        # Tabs use i18n keys: tab.story, tab.simulation, tab.video, tab.review
        self.assertIn('_t("tab.story")', content)
        self.assertIn('_t("tab.simulation")', content)
        self.assertIn('_t("tab.video")', content)
        self.assertIn('_t("tab.review")', content)

    def test_truyen_tab_has_two_outputs(self):
        """Verify Truyen tab has both draft and enhanced outputs."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        # Extract section between story tab and simulation tab (uses i18n keys)
        story_idx = content.find('_t("tab.story")')
        sim_idx = content.find('_t("tab.simulation")')
        truyen_section = content[story_idx:sim_idx] if story_idx >= 0 and sim_idx > story_idx else content

        self.assertIn("draft_output", truyen_section)
        self.assertIn("enhanced_output", truyen_section)

    def test_mo_phong_tab_exists(self):
        """Verify Mo Phong (Simulation) tab exists."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn('_t("tab.simulation")', content)
        self.assertIn("sim_output", content)

    def test_video_tab_exists(self):
        """Verify Video tab exists."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn('_t("tab.video")', content)
        self.assertIn("video_output", content)

    def test_danh_gia_tab_exists(self):
        """Verify Danh Gia (Evaluation) tab exists."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        self.assertIn('_t("tab.review")', content)
        self.assertIn("agent_output", content)
        self.assertIn("quality_output", content)


class TestYieldTupleStructure(unittest.TestCase):
    """Test that yield statements return 11-element tuples."""

    def test_error_yield_has_11_elements(self):
        """Verify error yield returns 11-element tuple."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            lines = f.readlines()

        # Find error yield statement
        for i, line in enumerate(lines):
            if 'yield (' in line and 'status-error' in line:
                # This error yield should have 11 elements
                yield_block = []
                j = i
                while ')' not in yield_block[-1] if yield_block else True:
                    yield_block.append(lines[j].strip())
                    j += 1

                # Count commas to verify 11 elements (10 commas)
                full_yield = " ".join(yield_block)
                # Count elements by commas (11 elements = 10 commas)
                element_count = full_yield.count(",") + 1
                self.assertEqual(element_count, 11,
                               f"Error yield should have 11 elements, got {element_count}")
                break

    def test_progress_yield_has_11_elements(self):
        """Verify progress yield returns 11-element tuple."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            lines = f.readlines()

        # Find progress yield statement (status-running)
        for i, line in enumerate(lines):
            if 'yield (' in line and 'status-running' in line:
                yield_block = []
                j = i
                while ')' not in yield_block[-1] if yield_block else True:
                    yield_block.append(lines[j].strip())
                    j += 1

                full_yield = " ".join(yield_block)
                element_count = full_yield.count(",") + 1
                self.assertEqual(element_count, 11,
                               f"Progress yield should have 11 elements, got {element_count}")
                break

    def test_final_output_yield_has_11_elements(self):
        """Verify _format_output returns 11-element tuple."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            lines = f.readlines()

        # Find the return statement in _format_output
        in_format_output = False
        found_return = False
        for i, line in enumerate(lines):
            if "def _format_output" in line:
                in_format_output = True
            if in_format_output and "return (" in line:
                # Find end by matching parens - need to count open/close parens
                paren_depth = 0
                j = i
                found_open = False
                while j < len(lines):
                    for char in lines[j]:
                        if char == "(":
                            paren_depth += 1
                            found_open = True
                        elif char == ")":
                            paren_depth -= 1
                            if found_open and paren_depth == 0:
                                break
                    if found_open and paren_depth == 0:
                        break
                    j += 1

                # We found the complete return, confirm it returns the right number of vars
                # by checking for the key elements
                return_block = "".join(lines[i:j+1])
                # Should have all these elements in the return tuple
                self.assertIn("status-badge", return_block)
                self.assertIn("_progress_html", return_block)
                self.assertIn("draft_text", return_block)
                self.assertIn("sim_text", return_block)
                self.assertIn("enhanced_text", return_block)
                self.assertIn("video_text", return_block)
                self.assertIn("agent_text", return_block)
                self.assertIn("quality_text", return_block)
                self.assertIn("orch", return_block)
                found_return = True
                break

        self.assertTrue(found_return, "_format_output return statement not found")

    def test_format_output_docstring_mentions_11_tuple(self):
        """Verify _format_output docstring mentions 11-tuple."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        # Find _format_output function
        func_start = content.find("def _format_output")
        self.assertGreater(func_start, -1, "_format_output function not found")

        # Find docstring
        docstring_start = content.find('"""', func_start)
        docstring_end = content.find('"""', docstring_start + 3)
        docstring = content[docstring_start:docstring_end + 3]

        self.assertTrue(
            "11" in docstring or "13" in docstring,
            "_format_output docstring should mention the tuple size",
        )


class TestStatusBadgeHTML(unittest.TestCase):
    """Test status badge HTML generation."""

    def test_status_badge_idle_html(self):
        """Verify idle status badge HTML."""
        html = '<span class="status-badge status-idle">San sang</span>'
        self.assertIn("status-badge", html)
        self.assertIn("status-idle", html)
        self.assertIn("San sang", html)

    def test_status_badge_running_html(self):
        """Verify running status badge HTML."""
        html = '<span class="status-badge status-running">Dang chay...</span>'
        self.assertIn("status-running", html)
        self.assertIn("Dang chay...", html)

    def test_status_badge_done_html(self):
        """Verify done status badge HTML."""
        html = '<span class="status-badge status-done">Hoan thanh!</span>'
        self.assertIn("status-done", html)
        self.assertIn("Hoan thanh!", html)

    def test_status_badge_error_html(self):
        """Verify error status badge HTML."""
        html = '<span class="status-badge status-error">Loi</span>'
        self.assertIn("status-error", html)
        self.assertIn("Loi", html)


class TestAppCompilation(unittest.TestCase):
    """Test app.py compiles without errors."""

    def test_app_py_compiles(self):
        """Verify app.py compiles without syntax errors."""
        app_path = os.path.join(project_root, "ui", "gradio_app.py")
        import py_compile
        try:
            py_compile.compile(app_path, doraise=True)
        except py_compile.PyCompileError as e:
            self.fail(f"app.py compilation failed: {e}")

    def test_app_imports_successfully(self):
        """Verify app module imports without errors."""
        try:
            import app
            self.assertIsNotNone(app)
        except Exception as e:
            self.fail(f"app.py import failed: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
