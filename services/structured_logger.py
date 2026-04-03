# Shim: re-exports from new location for backward compatibility
from services.infra.structured_logger import JSONFormatter, configure_logging

__all__ = ["JSONFormatter", "configure_logging"]
