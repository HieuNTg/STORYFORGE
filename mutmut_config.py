"""
mutmut_config.py — Mutation testing configuration for StoryForge.

Run mutation tests:
    mutmut run
    mutmut html          # generate HTML report in html/ directory
    mutmut results       # view summary in terminal

Target modules are the critical business-logic files where correctness matters most.
"""

# ---------------------------------------------------------------------------
# Target paths — mutmut will only mutate files under these directories/files
# ---------------------------------------------------------------------------
def pre_mutation(context):
    """Skip mutations in non-target files to keep runs fast."""
    target_paths = (
        "services/auth.py",
        "services/token_cost_tracker.py",
        "middleware/rbac.py",
        "pipeline/agents/debate_orchestrator.py",
    )
    if not any(context.filename.endswith(p) for p in target_paths):
        context.skip = True


# ---------------------------------------------------------------------------
# Paths mutmut scans for test files (used to detect surviving mutants)
# ---------------------------------------------------------------------------
def post_mutation(context):
    pass  # no-op hook required by mutmut's plugin interface


# ---------------------------------------------------------------------------
# CLI defaults — equivalent to: mutmut run --paths-to-mutate=... --tests-dir=tests
# Override via environment or CLI flags as needed.
# ---------------------------------------------------------------------------
MUTMUT_PATHS_TO_MUTATE = ",".join([
    "services/auth.py",
    "services/token_cost_tracker.py",
    "middleware/rbac.py",
    "pipeline/agents/debate_orchestrator.py",
])

MUTMUT_TESTS_DIR = "tests"

# Exclude generated/vendor code and data fixtures
MUTMUT_DICT_SYNONYMS = "xx"  # disable synonym mutations (too noisy)
