# Shim: re-exports from new location for backward compatibility
from services.security.credit_manager import CreditManager, CREDIT_COSTS, TIER_LIMITS

__all__ = ["CreditManager", "CREDIT_COSTS", "TIER_LIMITS"]
