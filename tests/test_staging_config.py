"""Tests for staging environment configuration files."""
import os
import yaml
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGING_COMPOSE = os.path.join(REPO_ROOT, "docker-compose.staging.yml")
ENV_STAGING_EXAMPLE = os.path.join(REPO_ROOT, ".env.staging.example")

REQUIRED_ENV_VARS = [
    "STORYFORGE_API_KEY",
    "STORYFORGE_BASE_URL",
    "STORYFORGE_MODEL",
    "STORYFORGE_BACKEND",
    "STORYFORGE_TEMPERATURE",
    "STORYFORGE_QUALITY_GATE",
    "STORYFORGE_SMART_REVISION",
    "STORYFORGE_AGENT_DEBATE",
]


def load_staging_compose():
    with open(STAGING_COMPOSE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_env_example_lines():
    with open(ENV_STAGING_EXAMPLE, "r", encoding="utf-8") as f:
        return f.read()


# ── File existence ────────────────────────────────────────────────────────────

def test_staging_compose_file_exists():
    assert os.path.isfile(STAGING_COMPOSE), "docker-compose.staging.yml not found"


def test_env_staging_example_exists():
    assert os.path.isfile(ENV_STAGING_EXAMPLE), ".env.staging.example not found"


# ── YAML validity ─────────────────────────────────────────────────────────────

def test_staging_compose_is_valid_yaml():
    data = load_staging_compose()
    assert isinstance(data, dict), "docker-compose.staging.yml did not parse to a dict"


def test_staging_compose_has_services():
    data = load_staging_compose()
    assert "services" in data, "No 'services' key in docker-compose.staging.yml"
    assert len(data["services"]) > 0, "No services defined"


# ── Service configuration ─────────────────────────────────────────────────────

def test_staging_service_name():
    data = load_staging_compose()
    assert "storyforge-staging" in data["services"], (
        "Expected service named 'storyforge-staging'"
    )


def test_staging_port_mapping():
    data = load_staging_compose()
    service = data["services"]["storyforge-staging"]
    ports = service.get("ports", [])
    assert any("7861" in str(p) for p in ports), (
        f"Expected port 7861 mapping, got: {ports}"
    )


def test_staging_port_maps_to_7860_internally():
    data = load_staging_compose()
    service = data["services"]["storyforge-staging"]
    ports = service.get("ports", [])
    # Expect "7861:7860" pattern
    assert any(str(p) == "7861:7860" for p in ports), (
        f"Expected '7861:7860' port mapping, got: {ports}"
    )


def test_staging_does_not_use_production_port():
    data = load_staging_compose()
    service = data["services"]["storyforge-staging"]
    ports = service.get("ports", [])
    for p in ports:
        host_port = str(p).split(":")[0]
        assert host_port != "7860", (
            "Staging must not bind host port 7860 (reserved for production)"
        )


# ── Quality feature flags ─────────────────────────────────────────────────────

def _get_environment_dict(service: dict) -> dict:
    """Parse the environment list into a key→value dict."""
    env_list = service.get("environment", [])
    result = {}
    for item in env_list:
        if "=" in str(item):
            key, _, val = str(item).partition("=")
            result[key.strip()] = val.strip()
    return result


def test_staging_quality_gate_enabled():
    data = load_staging_compose()
    service = data["services"]["storyforge-staging"]
    env = _get_environment_dict(service)
    assert env.get("STORYFORGE_QUALITY_GATE") == "true", (
        "STORYFORGE_QUALITY_GATE must be 'true' in staging"
    )


def test_staging_smart_revision_enabled():
    data = load_staging_compose()
    service = data["services"]["storyforge-staging"]
    env = _get_environment_dict(service)
    assert env.get("STORYFORGE_SMART_REVISION") == "true", (
        "STORYFORGE_SMART_REVISION must be 'true' in staging"
    )


def test_staging_agent_debate_enabled():
    data = load_staging_compose()
    service = data["services"]["storyforge-staging"]
    env = _get_environment_dict(service)
    assert env.get("STORYFORGE_AGENT_DEBATE") == "true", (
        "STORYFORGE_AGENT_DEBATE must be 'true' in staging"
    )


# ── Volumes ───────────────────────────────────────────────────────────────────

def test_staging_has_named_volumes():
    data = load_staging_compose()
    assert "volumes" in data, "No top-level 'volumes' section in staging compose"
    volumes = data["volumes"]
    assert "storyforge-staging-data" in volumes
    assert "storyforge-staging-output" in volumes


def test_staging_service_mounts_named_volumes():
    data = load_staging_compose()
    service = data["services"]["storyforge-staging"]
    service_volumes = service.get("volumes", [])
    volume_strs = [str(v) for v in service_volumes]
    assert any("storyforge-staging-data" in v for v in volume_strs)
    assert any("storyforge-staging-output" in v for v in volume_strs)


# ── Healthcheck ───────────────────────────────────────────────────────────────

def test_staging_has_healthcheck():
    data = load_staging_compose()
    service = data["services"]["storyforge-staging"]
    assert "healthcheck" in service, "Missing healthcheck in staging service"


# ── .env.staging.example contents ────────────────────────────────────────────

def test_env_example_contains_required_vars():
    content = load_env_example_lines()
    missing = [var for var in REQUIRED_ENV_VARS if var not in content]
    assert not missing, f"Missing required vars in .env.staging.example: {missing}"


def test_env_example_no_real_api_keys():
    content = load_env_example_lines()
    # Ensure placeholder, not a real key
    assert "your-api-key-here" in content, (
        "Expected placeholder 'your-api-key-here' for STORYFORGE_API_KEY"
    )
    # Crude check: real OpenAI keys start with sk-
    import re
    real_key_pattern = re.compile(r"STORYFORGE_API_KEY\s*=\s*sk-[A-Za-z0-9]+")
    assert not real_key_pattern.search(content), "Real API key found in example file!"


def test_env_example_staging_features_enabled():
    content = load_env_example_lines()
    assert "STORYFORGE_QUALITY_GATE=true" in content
    assert "STORYFORGE_SMART_REVISION=true" in content
    assert "STORYFORGE_AGENT_DEBATE=true" in content
