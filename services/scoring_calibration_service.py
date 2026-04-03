# Shim: re-exports from new location for backward compatibility
from services.pipeline.scoring_calibration_service import ScoringCalibrationService

__all__ = ["ScoringCalibrationService"]
