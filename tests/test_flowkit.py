"""FlowKit integration tests — Phase 01 covers config defaults + provider registration."""

from config.defaults import PipelineConfig
from services.media.image_generator import ImageGenerator


def test_config_flowkit_defaults():
    cfg = PipelineConfig()
    assert cfg.flowkit_enabled is False
    assert cfg.flowkit_port == 7860
    assert cfg.flowkit_style_reference_path == ""
    assert cfg.flowkit_concurrent_workers == 1
    assert cfg.flowkit_concurrent_workers_max == 4
    assert cfg.flowkit_workers_ramp_threshold == 10
    assert cfg.flowkit_veo_poll_interval == 5.0
    assert cfg.flowkit_account_warning_shown is False
    assert cfg.flowkit_risk_acknowledged is False
    assert cfg.flowkit_image_input_type_split is False
    assert cfg.flowkit_callback_hmac_required is False
    assert cfg.flowkit_use_refiner is True


def test_providers_includes_flowkit():
    assert "flowkit" in ImageGenerator.PROVIDERS
