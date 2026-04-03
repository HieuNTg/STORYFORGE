# Shim: re-exports from new location for backward compatibility
from services.infra.config_repository import get_config_repository

__all__ = ["get_config_repository"]
