"""Drama level normalization + pipeline route validator."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.schemas import normalize_drama


class TestNormalizeDrama:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("low", "low"),
            ("medium", "medium"),
            ("high", "high"),
            ("climax", "climax"),
            ("thấp", "low"),
            ("vừa", "medium"),
            ("trung bình", "medium"),
            ("cao", "high"),
            ("đỉnh", "climax"),
            ("  CAO  ", "high"),
            ("High", "high"),
        ],
    )
    def test_aliases(self, raw, expected):
        assert normalize_drama(raw) == expected

    @pytest.mark.parametrize("bad", ["", "extreme", "nope", "   "])
    def test_unknown_raises(self, bad):
        with pytest.raises(ValueError):
            normalize_drama(bad)

    def test_non_string_raises(self):
        with pytest.raises(ValueError):
            normalize_drama(None)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            normalize_drama(3)  # type: ignore[arg-type]


class TestPipelineRouteDramaValidator:
    def test_valid_drama_accepted(self):
        from api.pipeline_routes import PipelineRequest

        req = PipelineRequest(idea="x" * 12, drama_level="cao")
        assert req.drama_level == "cao"

    def test_invalid_drama_rejected(self):
        from api.pipeline_routes import PipelineRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PipelineRequest(idea="x" * 12, drama_level="extreme")

    def test_climax_requires_flag(self):
        from api.pipeline_routes import PipelineRequest
        from config import ConfigManager
        from pydantic import ValidationError

        cfg = ConfigManager()
        original = getattr(cfg.pipeline, "enable_drama_climax", False)
        cfg.pipeline.enable_drama_climax = False
        try:
            with pytest.raises(ValidationError):
                PipelineRequest(idea="x" * 12, drama_level="climax")
        finally:
            cfg.pipeline.enable_drama_climax = original

    def test_climax_accepted_when_flag_on(self):
        from api.pipeline_routes import PipelineRequest
        from config import ConfigManager

        cfg = ConfigManager()
        original = getattr(cfg.pipeline, "enable_drama_climax", False)
        cfg.pipeline.enable_drama_climax = True
        try:
            req = PipelineRequest(idea="x" * 12, drama_level="climax")
            assert req.drama_level == "climax"
        finally:
            cfg.pipeline.enable_drama_climax = original
