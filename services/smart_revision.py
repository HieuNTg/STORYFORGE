# Shim: re-exports from new location for backward compatibility
from services.pipeline.smart_revision import SmartRevisionService

__all__ = ["SmartRevisionService"]
