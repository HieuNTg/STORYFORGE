"""
tests/test_mutation_smoke.py
============================
Smoke tests that verify mutmut can be invoked and that the critical target
modules are importable.  These tests do NOT run mutation testing themselves —
they just gate the CI pipeline so mutation tests only run when the baseline
is green.

Running mutation tests
----------------------
Full mutation run (slow, ~5-15 min depending on model count):

    mutmut run \\
        --paths-to-mutate services/auth.py,services/token_cost_tracker.py,middleware/rbac.py,pipeline/agents/debate_orchestrator.py \\
        --tests-dir tests

Or use the helper script (also generates HTML report and enforces 60% threshold):

    bash scripts/run-mutation-tests.sh

Viewing results:

    mutmut results       # terminal summary
    mutmut html          # generates html/index.html
    mutmut show <id>     # show diff for a specific surviving mutant

Fixing a surviving mutant:
    1. Identify the mutant with `mutmut show <id>`
    2. Write a test that catches the logical change described in the diff
    3. Re-run `mutmut run` to confirm the mutant is now killed
"""

import subprocess
import sys
import importlib
import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _module_exists(dotted_name: str) -> bool:
    """Return True if a module can be imported without error."""
    try:
        importlib.import_module(dotted_name)
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Smoke: mutmut CLI is available
# ---------------------------------------------------------------------------

def test_mutmut_is_installed():
    """mutmut must be importable / on PATH for mutation CI to work."""
    result = subprocess.run(
        [sys.executable, "-m", "mutmut", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "mutmut is not installed. Run: pip install mutmut\n"
        f"stderr: {result.stderr}"
    )


def test_mutmut_config_is_present(tmp_path):
    """mutmut_config.py should exist at the project root."""
    import pathlib
    root = pathlib.Path(__file__).parent.parent
    config = root / "mutmut_config.py"
    assert config.exists(), "mutmut_config.py not found at project root."


# ---------------------------------------------------------------------------
# Smoke: target modules are importable
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module", [
    "services.auth",
    "services.token_cost_tracker",
])
def test_target_module_importable(module):
    """Critical mutation targets must be importable before mutation tests run."""
    assert _module_exists(module), (
        f"Module '{module}' could not be imported. "
        "Ensure the dev environment is fully set up."
    )


# ---------------------------------------------------------------------------
# Documentation test — always passes, captures how-to in pytest output
# ---------------------------------------------------------------------------

def test_mutation_testing_howto():
    """
    This test always passes.  It exists to surface the mutation testing
    how-to in `pytest -v` output so contributors know where to look.

    To run mutation tests:
        bash scripts/run-mutation-tests.sh

    To view surviving mutants:
        mutmut html && open html/index.html
    """
    assert True
