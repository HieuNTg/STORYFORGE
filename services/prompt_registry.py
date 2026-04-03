"""Prompt version registry — tracks prompt versions and compares diffs.

Reads version metadata from agent_prompts.yaml `_meta` section.
Version switching is done via STORYFORGE_PROMPTS_FILE env var (requires restart).
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(os.environ.get(
    "STORYFORGE_PROMPTS_DIR",
    Path(__file__).resolve().parents[1] / "data" / "prompts",
))
_DEFAULT_FILE = "agent_prompts.yaml"


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, return empty dict on failure."""
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except ImportError:
        logger.debug("PyYAML not installed — cannot read prompt metadata")
        return {}
    except Exception as exc:
        logger.warning("Failed to load %s: %s", path, exc)
        return {}


def get_prompt_version() -> dict:
    """Return current prompt version metadata.

    Returns:
        dict with version, updated_at, description, changelog
    """
    data = _load_yaml(_PROMPTS_DIR / _DEFAULT_FILE)
    meta = data.get("_meta", {})
    return {
        "version": meta.get("version", "unknown"),
        "updated_at": meta.get("updated_at", ""),
        "description": meta.get("description", ""),
        "changelog": meta.get("changelog", []),
        "file": str(_PROMPTS_DIR / _DEFAULT_FILE),
    }


def list_prompt_versions() -> list[dict]:
    """List all available prompt versions (files in prompts directory).

    Each YAML file in the prompts directory with a `_meta` section is a version.
    The active version is determined by STORYFORGE_PROMPTS_FILE env var.
    """
    versions = []
    active_file = os.environ.get("STORYFORGE_PROMPTS_FILE", str(_PROMPTS_DIR / _DEFAULT_FILE))

    for yaml_file in sorted(_PROMPTS_DIR.glob("*.yaml")):
        data = _load_yaml(yaml_file)
        meta = data.get("_meta", {})
        if not meta:
            continue
        versions.append({
            "version": meta.get("version", "unknown"),
            "updated_at": meta.get("updated_at", ""),
            "description": meta.get("description", ""),
            "file": yaml_file.name,
            "is_active": str(yaml_file) == active_file or yaml_file.name == _DEFAULT_FILE,
            "prompt_count": sum(1 for k in data if k != "_meta"),
        })
    return versions


def get_active_prompts() -> dict:
    """Return all active prompts (excluding _meta) from current version."""
    data = _load_yaml(_PROMPTS_DIR / _DEFAULT_FILE)
    return {k: v for k, v in data.items() if k != "_meta"}


def get_prompt_diff(version_a: str, version_b: str) -> dict:
    """Compare prompt keys between two version files.

    Args:
        version_a: filename of first version (e.g., "agent_prompts.yaml")
        version_b: filename of second version

    Returns:
        dict with added, removed, modified prompt keys
    """
    # Sanitize filenames
    safe_a = Path(version_a).name
    safe_b = Path(version_b).name
    data_a = _load_yaml(_PROMPTS_DIR / safe_a)
    data_b = _load_yaml(_PROMPTS_DIR / safe_b)

    prompts_a = {k: v for k, v in data_a.items() if k != "_meta"}
    prompts_b = {k: v for k, v in data_b.items() if k != "_meta"}

    keys_a = set(prompts_a.keys())
    keys_b = set(prompts_b.keys())

    added = list(keys_b - keys_a)
    removed = list(keys_a - keys_b)
    modified = [k for k in keys_a & keys_b if prompts_a[k] != prompts_b[k]]

    return {
        "version_a": data_a.get("_meta", {}).get("version", "unknown"),
        "version_b": data_b.get("_meta", {}).get("version", "unknown"),
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": list(keys_a & keys_b - set(modified)),
    }


