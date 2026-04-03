# Shim: re-exports from new location for backward compatibility
from services.export.wattpad_exporter import PlatformExporter

__all__ = ["PlatformExporter"]
