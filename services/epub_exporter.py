# Shim: re-exports from new location for backward compatibility
from services.export.epub_exporter import EPUBExporter, _html_escape

__all__ = ["EPUBExporter", "_html_escape"]
