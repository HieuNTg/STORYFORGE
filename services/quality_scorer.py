# Shim: re-exports from new location for backward compatibility
from services.pipeline.quality_scorer import QualityScorer

__all__ = ["QualityScorer"]
