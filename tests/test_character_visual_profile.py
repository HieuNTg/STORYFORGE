"""Tests for CharacterVisualProfileStore."""
import os
import json
import pytest
from services.character_visual_profile import CharacterVisualProfileStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def store(tmp_path):
    return CharacterVisualProfileStore(base_dir=str(tmp_path / "characters"))


@pytest.fixture()
def ref_image(tmp_path):
    path = tmp_path / "portrait.png"
    path.write_bytes(b"PNGDATA")
    return str(path)


class FakeCharacter:
    def __init__(self, name, appearance="", personality=""):
        self.name = name
        self.appearance = appearance
        self.personality = personality


# ---------------------------------------------------------------------------
# _safe_name
# ---------------------------------------------------------------------------

def test_safe_name_basic(store):
    assert store._safe_name("Minh") == "Minh"


def test_safe_name_special_chars(store):
    result = store._safe_name("Lý Minh Hào")
    # Spaces become underscores, Vietnamese chars become underscores
    assert " " not in result
    assert result.strip("_") == result  # no leading/trailing underscores


def test_safe_name_only_specials(store):
    result = store._safe_name("---")
    # All dashes → kept (dash is allowed) or stripped
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# has_profile
# ---------------------------------------------------------------------------

def test_has_profile_false_when_absent(store):
    assert store.has_profile("Nobody") is False


def test_has_profile_true_after_save(store):
    store.save_profile("Hero", "tall dark handsome")
    assert store.has_profile("Hero") is True


# ---------------------------------------------------------------------------
# save_profile + load_profile roundtrip
# ---------------------------------------------------------------------------

def test_save_load_roundtrip_no_image(store):
    store.save_profile("Alice", "short blonde hair, blue eyes")
    profile = store.load_profile("Alice")
    assert profile is not None
    assert profile["name"] == "Alice"
    assert profile["description"] == "short blonde hair, blue eyes"
    assert profile["reference_image"] == ""
    assert "created_at" in profile


def test_save_load_roundtrip_with_image(store, ref_image):
    store.save_profile("Bob", "tall, dark hair", reference_image_path=ref_image)
    profile = store.load_profile("Bob")
    assert profile is not None
    assert os.path.exists(profile["reference_image"])
    # Original file content preserved
    with open(profile["reference_image"], "rb") as f:
        assert f.read() == b"PNGDATA"


def test_load_profile_missing_returns_none(store):
    result = store.load_profile("Ghost")
    assert result is None


# ---------------------------------------------------------------------------
# get_reference_image
# ---------------------------------------------------------------------------

def test_get_reference_image_with_image(store, ref_image):
    store.save_profile("Carol", "red hair", reference_image_path=ref_image)
    ref = store.get_reference_image("Carol")
    assert ref is not None
    assert os.path.exists(ref)


def test_get_reference_image_without_image(store):
    store.save_profile("Dave", "brown hair")
    ref = store.get_reference_image("Dave")
    assert ref is None


def test_get_reference_image_nonexistent_char(store):
    assert store.get_reference_image("Unknown") is None


# ---------------------------------------------------------------------------
# get_visual_description
# ---------------------------------------------------------------------------

def test_get_visual_description(store):
    store.save_profile("Eve", "tall with green eyes")
    desc = store.get_visual_description("Eve")
    assert desc == "tall with green eyes"


def test_get_visual_description_missing_returns_empty(store):
    assert store.get_visual_description("Nobody") == ""


# ---------------------------------------------------------------------------
# build_visual_description
# ---------------------------------------------------------------------------

def test_build_visual_description_appearance_only(store):
    char = FakeCharacter("Frank", appearance="muscular build, scar on left cheek")
    desc = store.build_visual_description(char)
    assert "muscular build" in desc


def test_build_visual_description_appearance_and_personality(store):
    char = FakeCharacter("Grace", appearance="petite frame", personality="stern expression")
    desc = store.build_visual_description(char)
    assert "petite frame" in desc
    assert "stern expression" in desc


def test_build_visual_description_fallback_to_name(store):
    char = FakeCharacter("Henry")
    desc = store.build_visual_description(char)
    assert "Henry" in desc


def test_build_visual_description_non_character_object(store):
    class Minimal:
        name = "Ivy"
    desc = store.build_visual_description(Minimal())
    assert "Ivy" in desc


# ---------------------------------------------------------------------------
# list_profiles
# ---------------------------------------------------------------------------

def test_list_profiles_empty(store):
    assert store.list_profiles() == []


def test_list_profiles_multiple(store):
    store.save_profile("Alpha", "desc A")
    store.save_profile("Beta", "desc B")
    store.save_profile("Gamma", "desc C")
    profiles = store.list_profiles()
    assert len(profiles) == 3
    names = {p["name"] for p in profiles}
    assert names == {"Alpha", "Beta", "Gamma"}


# ---------------------------------------------------------------------------
# delete_profile
# ---------------------------------------------------------------------------

def test_delete_profile(store):
    store.save_profile("Zara", "tall")
    assert store.has_profile("Zara") is True
    result = store.delete_profile("Zara")
    assert result is True
    assert store.has_profile("Zara") is False


def test_delete_profile_nonexistent_returns_false(store):
    result = store.delete_profile("Nobody")
    assert result is False


# ---------------------------------------------------------------------------
# save_profile idempotent (overwrite)
# ---------------------------------------------------------------------------

def test_save_profile_overwrite(store):
    store.save_profile("Nora", "old description")
    store.save_profile("Nora", "new description")
    profile = store.load_profile("Nora")
    assert profile["description"] == "new description"
