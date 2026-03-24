"""Test UserManager service."""
import pytest
from services.user_manager import UserManager


def test_register_new_user(tmp_path):
    um = UserManager(storage_path=str(tmp_path))
    profile = um.register("alice", "password123")
    assert profile.username == "alice"
    assert profile.user_id != ""
    assert profile.password_hash != "password123"
    assert profile.password_hash.startswith("$2b$") or profile.password_hash.startswith("$2a$")  # bcrypt format


def test_register_duplicate_raises(tmp_path):
    um = UserManager(storage_path=str(tmp_path))
    um.register("alice", "pass1")
    with pytest.raises(ValueError, match="already exists"):
        um.register("alice", "pass2")


def test_login_valid(tmp_path):
    um = UserManager(storage_path=str(tmp_path))
    um.register("bob", "secret")
    profile = um.login("bob", "secret")
    assert profile is not None
    assert profile.username == "bob"


def test_login_wrong_password(tmp_path):
    um = UserManager(storage_path=str(tmp_path))
    um.register("bob", "secret")
    assert um.login("bob", "wrong") is None


def test_login_nonexistent_user(tmp_path):
    um = UserManager(storage_path=str(tmp_path))
    assert um.login("nobody", "pass") is None


def test_save_and_list_stories(tmp_path):
    um = UserManager(storage_path=str(tmp_path))
    profile = um.register("carol", "pass")
    story_id = um.save_story(profile.user_id, {"title": "Test"}, "My Story")
    assert story_id != ""
    stories = um.list_stories(profile.user_id)
    assert len(stories) == 1
    assert stories[0]["title"] == "My Story"


def test_delete_story(tmp_path):
    um = UserManager(storage_path=str(tmp_path))
    profile = um.register("dave", "pass")
    story_id = um.save_story(profile.user_id, {"data": "test"}, "Story 1")
    assert um.delete_story(profile.user_id, story_id) is True
    assert len(um.list_stories(profile.user_id)) == 0


def test_track_usage(tmp_path):
    um = UserManager(storage_path=str(tmp_path))
    profile = um.register("eve", "pass")
    um.track_usage(profile.user_id)
    um.track_usage(profile.user_id)
    updated = um._load_profile(profile.user_id)
    assert updated.usage_count == 2


def test_password_hash_security(tmp_path):
    um = UserManager(storage_path=str(tmp_path))
    h1 = um._hash_password("password")
    h2 = um._hash_password("password")
    # Different salt each time
    assert h1 != h2
    # Both verify correctly
    assert um._verify_password("password", h1)
    assert um._verify_password("password", h2)
    assert not um._verify_password("wrong", h1)
