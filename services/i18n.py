# Shim: re-exports from new location for backward compatibility
from services.infra.i18n import I18n, SUPPORTED_LANGUAGES

__all__ = ["I18n", "SUPPORTED_LANGUAGES"]
