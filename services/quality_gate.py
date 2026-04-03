# Shim: re-exports from new location for backward compatibility
from services.pipeline.quality_gate import QualityGateResult, QualityGate, DEFAULT_GATE_THRESHOLD, DEFAULT_CHAPTER_THRESHOLD

__all__ = ["QualityGateResult", "QualityGate", "DEFAULT_GATE_THRESHOLD", "DEFAULT_CHAPTER_THRESHOLD"]
