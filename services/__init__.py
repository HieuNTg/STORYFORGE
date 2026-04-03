"""Services package — register domain sub-package modules under the old flat
names so that ``patch("services.image_generator.requests")`` and similar
mock targets continue to resolve correctly after the directory reorganization.
"""
import importlib
import sys


def _alias(old_name: str, new_name: str) -> None:
    """Register *new_name* module under *old_name* in sys.modules."""
    mod = importlib.import_module(new_name)
    sys.modules[old_name] = mod


# auth domain
_alias("services.auth_revocation", "services.auth.auth_revocation")
_alias("services.jwt_manager", "services.auth.jwt_manager")
_alias("services.user_store", "services.auth.user_store")
_alias("services.user_manager", "services.auth.user_manager")

# export domain
# Note: services.epub_exporter kept as flat file (test_epub_exporter.py uses importlib.reload)
_alias("services.html_exporter", "services.export.html_exporter")
_alias("services.pdf_exporter", "services.export.pdf_exporter")
_alias("services.video_exporter", "services.export.video_exporter")
_alias("services.wattpad_exporter", "services.export.wattpad_exporter")

# media domain
_alias("services.image_generator", "services.media.image_generator")
_alias("services.image_prompt_generator", "services.media.image_prompt_generator")
_alias("services.tts_audio_generator", "services.media.tts_audio_generator")
_alias("services.tts_script_generator", "services.media.tts_script_generator")
_alias("services.video_composer", "services.media.video_composer")

# pipeline domain
_alias("services.quality_scorer", "services.pipeline.quality_scorer")
_alias("services.self_review", "services.pipeline.self_review")
_alias("services.smart_revision", "services.pipeline.smart_revision")
_alias("services.branch_narrative", "services.pipeline.branch_narrative")
_alias("services.quality_gate", "services.pipeline.quality_gate")
_alias("services.eval_pipeline", "services.pipeline.eval_pipeline")
try:
    _alias("services.scoring_calibration_service", "services.pipeline.scoring_calibration_service")
except ImportError:
    pass  # requires tests.benchmarks on sys.path

# security domain
_alias("services.input_sanitizer", "services.security.input_sanitizer")
_alias("services.credit_manager", "services.security.credit_manager")

# infra domain
_alias("services.database", "services.infra.database")
_alias("services.config_repository", "services.infra.config_repository")
_alias("services.structured_logger", "services.infra.structured_logger")
_alias("services.metrics", "services.infra.metrics")
_alias("services.i18n", "services.infra.i18n")
