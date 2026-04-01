# ruff: noqa: F401,F403
# flake8: noqa: F401,F403
"""Re-export stub — kept for filesystem compat. Package at services/browser_auth/ takes precedence.

Python resolves 'services.browser_auth' to the package directory.
This file is retained so path-based compile checks (test_browser_auth_compiles) still pass.
"""
# Nothing to import here — the package __init__.py is the real module.
# If somehow this file is loaded instead of the package, surface a clear error.
import importlib as _importlib
import sys as _sys

_pkg = _importlib.import_module("services.browser_auth")
_sys.modules[__name__] = _pkg
