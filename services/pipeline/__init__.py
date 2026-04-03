# Backward-compatible re-exports for services.pipeline.*
from .quality_scorer import QualityScorer
from .quality_gate import (
    QualityGateResult,
    QualityGate,
    DEFAULT_GATE_THRESHOLD,
    DEFAULT_CHAPTER_THRESHOLD,
)
from .self_review import SelfReviewer, get_genre_threshold
from .smart_revision import SmartRevisionService
from .branch_narrative import BranchManager, manager
from .eval_pipeline import EvalPipeline
try:
    from .scoring_calibration_service import ScoringCalibrationService
except ImportError:
    pass  # requires tests.benchmarks on sys.path

__all__ = [
    "QualityScorer",
    "QualityGateResult",
    "QualityGate",
    "DEFAULT_GATE_THRESHOLD",
    "DEFAULT_CHAPTER_THRESHOLD",
    "SelfReviewer",
    "get_genre_threshold",
    "SmartRevisionService",
    "BranchManager",
    "manager",
    "EvalPipeline",
    "ScoringCalibrationService",
]
