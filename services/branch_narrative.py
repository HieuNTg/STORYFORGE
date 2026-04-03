# Shim: re-exports from new location for backward compatibility
from services.pipeline.branch_narrative import BranchManager, manager

__all__ = ["BranchManager", "manager"]
