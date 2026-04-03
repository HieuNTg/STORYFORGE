# Shim: re-exports from new location for backward compatibility
from services.pipeline.eval_pipeline import EvalPipeline

__all__ = ["EvalPipeline"]
