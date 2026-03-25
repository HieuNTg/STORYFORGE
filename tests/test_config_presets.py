"""Tests for PIPELINE_PRESETS and preset apply logic."""

import pytest
from config import PIPELINE_PRESETS, PipelineConfig, ConfigManager


# ── Preset data validity ──

def test_all_presets_have_label():
    for key, preset in PIPELINE_PRESETS.items():
        assert "label" in preset, f"Preset '{key}' missing 'label'"
        assert isinstance(preset["label"], str) and preset["label"]


def test_preset_keys_are_expected():
    assert set(PIPELINE_PRESETS.keys()) == {"beginner", "advanced", "pro"}


def test_preset_fields_are_valid_pipeline_attributes():
    """Every field in each preset (except 'label') must map to a PipelineConfig attribute."""
    dummy = PipelineConfig()
    for key, preset in PIPELINE_PRESETS.items():
        for field_name in preset:
            if field_name == "label":
                continue
            assert hasattr(dummy, field_name), (
                f"Preset '{key}' field '{field_name}' not in PipelineConfig"
            )


def test_beginner_disables_all_advanced_features():
    p = PIPELINE_PRESETS["beginner"]
    assert p["enable_self_review"] is False
    assert p["enable_agent_debate"] is False
    assert p["enable_smart_revision"] is False
    assert p["use_long_context"] is False
    assert p["enable_voice_emotion"] is False
    assert p["enable_character_consistency"] is False
    assert p["rag_enabled"] is False


def test_advanced_enables_core_features():
    p = PIPELINE_PRESETS["advanced"]
    assert p["enable_self_review"] is True
    assert p["enable_agent_debate"] is True
    assert p["enable_smart_revision"] is True
    # advanced keeps heavy features off
    assert p["use_long_context"] is False
    assert p["enable_voice_emotion"] is False
    assert p["rag_enabled"] is False


def test_pro_enables_all_features():
    p = PIPELINE_PRESETS["pro"]
    assert p["enable_self_review"] is True
    assert p["enable_agent_debate"] is True
    assert p["enable_smart_revision"] is True
    assert p["use_long_context"] is True
    assert p["enable_voice_emotion"] is True
    assert p["enable_character_consistency"] is True
    assert p["rag_enabled"] is True


def test_threshold_values_in_valid_range():
    for key, preset in PIPELINE_PRESETS.items():
        for field_name in ("self_review_threshold", "smart_revision_threshold"):
            if field_name in preset:
                val = preset[field_name]
                assert 1.0 <= val <= 5.0, (
                    f"Preset '{key}': {field_name}={val} out of range [1.0, 5.0]"
                )


def test_drama_intensity_valid_values():
    valid = {"thấp", "trung bình", "cao"}
    for key, preset in PIPELINE_PRESETS.items():
        if "drama_intensity" in preset:
            assert preset["drama_intensity"] in valid, (
                f"Preset '{key}': invalid drama_intensity '{preset['drama_intensity']}'"
            )


# ── apply_preset logic (unit-tests, no ConfigManager singleton side-effects) ──

def _apply_preset_to_pipeline(choice: str, pipeline: PipelineConfig) -> tuple:
    """Mirror of the apply_preset logic in settings_tab, operating on a given PipelineConfig."""
    if not choice or choice == "Tùy chỉnh":
        return False, pipeline  # no-op
    key = choice.split("(")[-1].rstrip(")")
    preset = PIPELINE_PRESETS.get(key)
    if not preset:
        return False, pipeline
    for field_name, value in preset.items():
        if field_name == "label":
            continue
        if hasattr(pipeline, field_name):
            setattr(pipeline, field_name, value)
    return True, pipeline


def test_custom_choice_does_not_modify_pipeline():
    p = PipelineConfig()
    original_self_review = p.enable_self_review
    changed, p2 = _apply_preset_to_pipeline("Tùy chỉnh", p)
    assert not changed
    assert p2.enable_self_review == original_self_review


def test_empty_choice_does_not_modify_pipeline():
    p = PipelineConfig()
    original_self_review = p.enable_self_review
    changed, p2 = _apply_preset_to_pipeline("", p)
    assert not changed
    assert p2.enable_self_review == original_self_review


def test_beginner_preset_applies_correctly():
    p = PipelineConfig()
    # Force non-default values first
    p.enable_self_review = True
    p.enable_agent_debate = True
    p.rag_enabled = True

    label = PIPELINE_PRESETS["beginner"]["label"]
    choice = f"{label} (beginner)"
    changed, p2 = _apply_preset_to_pipeline(choice, p)

    assert changed
    assert p2.enable_self_review is False
    assert p2.enable_agent_debate is False
    assert p2.rag_enabled is False
    assert p2.context_window_chapters == 2
    assert p2.num_simulation_rounds == 3
    assert p2.drama_intensity == "trung bình"


def test_advanced_preset_applies_correctly():
    p = PipelineConfig()
    label = PIPELINE_PRESETS["advanced"]["label"]
    choice = f"{label} (advanced)"
    changed, p2 = _apply_preset_to_pipeline(choice, p)

    assert changed
    assert p2.enable_self_review is True
    assert p2.self_review_threshold == 3.0
    assert p2.enable_agent_debate is True
    assert p2.enable_smart_revision is True
    assert p2.use_long_context is False


def test_pro_preset_applies_correctly():
    p = PipelineConfig()
    label = PIPELINE_PRESETS["pro"]["label"]
    choice = f"{label} (pro)"
    changed, p2 = _apply_preset_to_pipeline(choice, p)

    assert changed
    assert p2.enable_self_review is True
    assert p2.self_review_threshold == 2.5
    assert p2.use_long_context is True
    assert p2.enable_voice_emotion is True
    assert p2.enable_character_consistency is True
    assert p2.rag_enabled is True


def test_unknown_preset_key_is_ignored():
    p = PipelineConfig()
    changed, p2 = _apply_preset_to_pipeline("Some Label (nonexistent)", p)
    assert not changed
