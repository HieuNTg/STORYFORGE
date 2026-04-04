"""Validation logic for StoryForge configuration."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .defaults import LLMConfig, PipelineConfig


def validate_config(llm: "LLMConfig", pipeline: "PipelineConfig") -> list[str]:
    """Validate config fields. Returns list of warning/error messages."""
    errors = []

    if not llm.api_key:
        errors.append("API key bắt buộc")

    if pipeline.num_chapters < 1:
        errors.append("Số chương phải >= 1")

    if pipeline.words_per_chapter < 100:
        errors.append("Số từ/chương phải >= 100")

    if not (1.0 <= pipeline.self_review_threshold <= 5.0):
        errors.append("self_review_threshold phải từ 1.0 đến 5.0")

    if not (1.0 <= pipeline.smart_revision_threshold <= 5.0):
        errors.append("smart_revision_threshold phải từ 1.0 đến 5.0")

    if not (1.0 <= pipeline.quality_gate_threshold <= 5.0):
        errors.append("quality_gate_threshold phải từ 1.0 đến 5.0")

    # Warn about likely-invalid OpenRouter model IDs
    if "openrouter" in llm.base_url:
        model = llm.model
        if model and "/" not in model:
            errors.append(
                f"Model '{model}' không hợp lệ cho OpenRouter. "
                f"Cần format 'provider/model-name' (ví dụ: deepseek/deepseek-chat-v3-0324:free)"
            )
        elif model and model.startswith("openrouter/"):
            errors.append(
                f"Model '{model}' có thể route random — nên dùng model cụ thể "
                f"(ví dụ: deepseek/deepseek-chat-v3-0324:free)"
            )

    return errors
