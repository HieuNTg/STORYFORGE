"""Read-only data shipped with the code (prompts, templates, evals) is read
from ``bundled_data_dir()``, which ``STORYFORGE_BUNDLED_DATA_DIR`` overrides.

In Docker, /app/data is the storyforge-data volume. If the bundled files lived
there too, the volume would keep serving the copies from the first image after
an upgrade or a branch switch, so the image ships them in /app/bundled.
"""

import json
from pathlib import Path

import pytest

from services.infra.bundled_data import bundled_data_dir

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bundled(tmp_path, monkeypatch):
    root = tmp_path / "bundled"
    (root / "prompts" / "v9").mkdir(parents=True)
    (root / "templates").mkdir()
    (root / "evals").mkdir()
    (root / "prompts" / "agent_prompts.yaml").write_text(
        '_meta:\n  version: "marker-9"\nEDITOR_REVIEW: "marker editor prompt"\n',
        encoding="utf-8",
    )
    (root / "prompts" / "v9" / "write_chapter.yaml").write_text(
        'version: "marker"\ntemplate: "marker chapter template"\n', encoding="utf-8"
    )
    (root / "templates" / "story_templates.json").write_text(
        json.dumps({"marker-genre": []}), encoding="utf-8"
    )
    (root / "evals" / "golden_dataset.json").write_text(
        json.dumps({"entries": [{"id": "marker-entry", "chapters": []}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("STORYFORGE_BUNDLED_DATA_DIR", str(root))
    monkeypatch.delenv("STORYFORGE_PROMPTS_FILE", raising=False)
    monkeypatch.delenv("STORYFORGE_PROMPTS_DIR", raising=False)
    return root


def test_default_is_repo_data_dir(monkeypatch):
    monkeypatch.delenv("STORYFORGE_BUNDLED_DATA_DIR", raising=False)
    assert bundled_data_dir() == REPO_ROOT / "data"


def test_env_overrides_bundled_dir(bundled):
    assert bundled_data_dir() == bundled


def test_agent_prompts_read_bundled_yaml(bundled):
    from pipeline.agents import agent_prompts

    assert agent_prompts._get_prompt("EDITOR_REVIEW") == "marker editor prompt"


def test_agent_prompts_file_env_still_wins(bundled, tmp_path, monkeypatch):
    from pipeline.agents import agent_prompts

    custom = tmp_path / "custom.yaml"
    custom.write_text('EDITOR_REVIEW: "custom file prompt"\n', encoding="utf-8")
    monkeypatch.setenv("STORYFORGE_PROMPTS_FILE", str(custom))

    assert agent_prompts._get_prompt("EDITOR_REVIEW") == "custom file prompt"


def test_prompt_registry_reads_bundled_dir(bundled):
    from services.prompt_registry import get_prompt_version

    assert get_prompt_version()["version"] == "marker-9"


def test_prompt_registry_dir_env_still_wins(bundled, tmp_path, monkeypatch):
    from services.prompt_registry import get_prompt_version

    other = tmp_path / "other_prompts"
    other.mkdir()
    (other / "agent_prompts.yaml").write_text(
        '_meta:\n  version: "other-dir"\n', encoding="utf-8"
    )
    monkeypatch.setenv("STORYFORGE_PROMPTS_DIR", str(other))

    assert get_prompt_version()["version"] == "other-dir"


def test_prompt_manager_reads_bundled_versions(bundled):
    from services.prompt_manager import PromptManager

    assert PromptManager().get_raw("write_chapter") == "marker chapter template"


def test_story_templates_route_reads_bundled_file(bundled):
    from api.pipeline_routes import get_templates

    assert get_templates() == {"marker-genre": []}


def test_golden_eval_reads_bundled_dataset(bundled, tmp_path):
    from services.pipeline.eval_pipeline import EvalPipeline

    result = EvalPipeline(evals_dir=str(tmp_path / "user_evals")).run_golden_eval()

    assert [r["id"] for r in result["results"]] == ["marker-entry"]


def test_human_evals_are_not_written_to_bundled_dir(bundled):
    from services.pipeline.eval_pipeline import EvalPipeline

    assert Path(EvalPipeline()._evals_dir).resolve() != (bundled / "evals").resolve()
