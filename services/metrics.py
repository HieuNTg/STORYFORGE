# Shim: re-exports from new location for backward compatibility
from services.infra.metrics import format_metrics

__all__ = ["format_metrics"]
