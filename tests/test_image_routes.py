"""Tests for /api/images/{session_id}/generate endpoint."""

import time

import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.image_routes import router as image_router, _in_flight, _jobs
from models.schemas import Chapter, Character, StoryDraft, PipelineOutput


def _build_orch(num_chapters: int = 2, characters=None):
    chapters = [
        Chapter(chapter_number=i, title=f"Ch{i}", content=f"Body {i}", word_count=2)
        for i in range(1, num_chapters + 1)
    ]
    draft = StoryDraft(
        title="T", genre="g", synopsis="s",
        chapters=chapters,
        characters=list(characters or []),
    )
    output = PipelineOutput(story_draft=draft, status="complete")

    class _Wrap:
        def __init__(self, out):
            self.output = out
    return _Wrap(output)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(image_router)
    _in_flight.clear()
    _jobs.clear()
    return TestClient(app)


@pytest.fixture
def inline_jobs():
    """Run the async comic-job worker's ``asyncio.to_thread`` calls inline.

    Phase B generation runs in a detached ``asyncio.Task`` whose per-chapter
    ``await asyncio.to_thread(handle_generate_images, …)`` is normally driven to
    completion by the continuously-running uvicorn event loop. Starlette's
    ``TestClient`` portal, however, parks its loop between requests, so the
    executor done-callback never wakes the task and the job is stuck at
    ``running`` forever (a harness artifact — verified the same code resumes on a
    real running loop). Patching ``asyncio.to_thread`` to run the function inline
    lets the worker finish within a single loop turn so polling observes a
    terminal state. Production behaviour is unchanged (it uses the real loop).
    """
    async def _inline(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("asyncio.to_thread", side_effect=_inline):
        yield


def test_generate_404_when_session_missing(client):
    with patch("api.image_routes._get_story_data", return_value=None):
        r = client.post("/images/missing/generate", json={})
    assert r.status_code == 404


def test_generate_provider_none_short_circuits(client):
    orch = _build_orch(2)
    with patch("api.image_routes._get_story_data", return_value=orch), \
         patch("services.handlers.handle_generate_images", return_value=([], "no provider")):
        r = client.post("/images/sess-1/generate", json={"provider": "none"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["chapter_images"] == {}


def test_generate_persists_chapter_images(client, tmp_path, monkeypatch):
    # Simulate handler writing image filenames onto chapter.images
    orch = _build_orch(3)

    def fake_handler(orch_state, provider="none", t=None, chapter_number=None):
        # Mirror the real handler: when chapter_number is set, only that chapter
        # is touched (incremental mode loops one call per missing chapter).
        targets = [
            ch for ch in orch_state.output.story_draft.chapters
            if chapter_number is None or ch.chapter_number == chapter_number
        ]
        for ch in targets:
            ch.images = [f"ch{ch.chapter_number:02d}_panel01.png"]
        return [ch.images[0] for ch in targets], "ok"

    with patch("api.image_routes._get_story_data", return_value=orch), \
         patch("services.handlers.handle_generate_images", side_effect=fake_handler):
        r = client.post("/images/sess-2/generate", json={"provider": "dalle"})

    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert body["chapter_images"] == {
        "1": ["ch01_panel01.png"],
        "2": ["ch02_panel01.png"],
        "3": ["ch03_panel01.png"],
    }


def test_generate_in_flight_guard(client):
    orch = _build_orch(1)
    _in_flight.add("locked-sess")
    try:
        with patch("api.image_routes._get_story_data", return_value=orch):
            r = client.post("/images/locked-sess/generate", json={})
        assert r.status_code == 409
    finally:
        _in_flight.discard("locked-sess")


def test_generate_single_chapter_scope(client):
    """When `chapter` is supplied, only that chapter's images are regenerated."""
    orch = _build_orch(3)
    captured = {}

    def fake_handler(orch_state, provider="none", t=None, chapter_number=None):
        captured["chapter_number"] = chapter_number
        # Simulate the handler only touching the requested chapter
        for ch in orch_state.output.story_draft.chapters:
            if chapter_number is None or ch.chapter_number == chapter_number:
                ch.images = [f"ch{ch.chapter_number:02d}_panel01.png"]
        return ["ch02_panel01.png"], "ok"

    with patch("api.image_routes._get_story_data", return_value=orch), \
         patch("services.handlers.handle_generate_images", side_effect=fake_handler):
        r = client.post("/images/sess-3/generate", json={"chapter": 2, "provider": "dalle"})

    assert r.status_code == 200
    assert captured["chapter_number"] == 2
    body = r.json()
    # Only chapter 2 should have images in the response map
    assert body["chapter_images"] == {"2": ["ch02_panel01.png"]}


def test_auto_builds_visual_profiles_on_first_call(client, tmp_path, monkeypatch):
    """First call on checkpoint with no profiles → extractor invoked & profiles persisted."""
    char = Character(name="Hero", role="chính", appearance="tall, dark hair", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])

    # Isolate the on-disk profile store to a temp dir
    monkeypatch.chdir(tmp_path)

    # Mock extractor so we don't hit the LLM
    fake_extractor = MagicMock()
    fake_extractor.extract_and_generate.return_value = (
        {"hair": {"color": "dark"}}, "FROZEN_PROMPT_HERO"
    )
    extractor_cls = MagicMock(return_value=fake_extractor)

    # Mock the image generation pipeline (provider/prompt/gen) so the handler
    # focuses on the profile auto-build path.
    image_gen = MagicMock()
    image_gen.generate_story_images.return_value = ["output/images/ch01_panel01.png"]
    prompt_gen = MagicMock()
    prompt_gen.generate_from_chapter.return_value = ["a prompt"]

    with patch("api.image_routes._get_story_data", return_value=orch), \
         patch("services.character_visual_extractor.CharacterVisualExtractor", extractor_cls), \
         patch("services.image_generator.ImageGenerator", return_value=image_gen), \
         patch("services.image_prompt_generator.ImagePromptGenerator", return_value=prompt_gen):
        r = client.post("/images/sess-auto/generate", json={"provider": "dalle"})

    assert r.status_code == 200, r.text
    # Extractor was invoked once for the missing profile
    assert fake_extractor.extract_and_generate.call_count == 1
    # Frozen prompt was injected into the prompt generator call
    _, kwargs = prompt_gen.generate_from_chapter.call_args
    assert kwargs.get("visual_profiles") == {"Hero": "FROZEN_PROMPT_HERO"}
    # Profile persisted under the per-story characters dir (title-scoped to "T").
    from services.output_paths import characters_dir
    assert (tmp_path / characters_dir("T") / "Hero" / "profile.json").exists()


def test_auto_build_skipped_when_profile_exists(client, tmp_path, monkeypatch):
    """Second call with cached profile → extractor NOT invoked."""
    from services.character_visual_profile import CharacterVisualProfileStore

    char = Character(name="Hero", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])

    monkeypatch.chdir(tmp_path)
    # Pre-seed the profile store scoped to the same story title ("T") the
    # handler reads from, so the cached profile is actually found.
    store = CharacterVisualProfileStore(story_title="T")
    store.save_enhanced_profile(
        "Hero", "tall", {"hair": {"color": "dark"}}, "CACHED_PROMPT", ""
    )

    fake_extractor = MagicMock()
    extractor_cls = MagicMock(return_value=fake_extractor)
    image_gen = MagicMock()
    image_gen.generate_story_images.return_value = ["output/images/ch01_panel01.png"]
    prompt_gen = MagicMock()
    prompt_gen.generate_from_chapter.return_value = ["a prompt"]

    with patch("api.image_routes._get_story_data", return_value=orch), \
         patch("services.character_visual_extractor.CharacterVisualExtractor", extractor_cls), \
         patch("services.image_generator.ImageGenerator", return_value=image_gen), \
         patch("services.image_prompt_generator.ImagePromptGenerator", return_value=prompt_gen):
        r = client.post("/images/sess-cached/generate", json={"provider": "dalle"})

    assert r.status_code == 200, r.text
    # Extractor was NOT instantiated (no missing profiles to build)
    extractor_cls.assert_not_called()
    _, kwargs = prompt_gen.generate_from_chapter.call_args
    assert kwargs.get("visual_profiles") == {"Hero": "CACHED_PROMPT"}


def test_profiles_404_when_session_missing(client):
    with patch("api.image_routes._get_story_data", return_value=None):
        r = client.get("/images/missing/profiles")
    assert r.status_code == 404


def test_profiles_returns_stored_profiles(client):
    char = Character(name="Hero", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])

    fake_store = MagicMock()
    fake_store.load_profile.return_value = {
        "name": "Hero",
        "description": "tall",
        "frozen_prompt": "FROZEN_HERO",
        "prompt_version": 2,
        "reference_image": "",
    }
    with patch("api.image_routes._get_story_data", return_value=orch), \
         patch("services.character_visual_profile.CharacterVisualProfileStore", return_value=fake_store):
        r = client.get("/images/sess-p1/profiles")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profiles"] == [
        {
            "name": "Hero",
            "frozen_prompt": "FROZEN_HERO",
            "prompt_version": 2,
            "has_reference_image": False,
            "reference_url": None,
        }
    ]


def test_profiles_empty_when_no_profiles_stored(client):
    char = Character(name="Hero", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])

    fake_store = MagicMock()
    fake_store.load_profile.return_value = None
    with patch("api.image_routes._get_story_data", return_value=orch), \
         patch("services.character_visual_profile.CharacterVisualProfileStore", return_value=fake_store):
        r = client.get("/images/sess-p2/profiles")

    assert r.status_code == 200
    assert r.json() == {"profiles": []}


def test_rebuild_profile_404_when_session_missing(client):
    with patch("api.image_routes._get_story_data", return_value=None):
        r = client.post("/images/missing/profiles/Hero/rebuild")
    assert r.status_code == 404


def test_rebuild_profile_404_when_character_not_found(client):
    char = Character(name="Hero", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])
    with patch("api.image_routes._get_story_data", return_value=orch):
        r = client.post("/images/sess-r1/profiles/Ghost/rebuild")
    assert r.status_code == 404
    assert "Ghost" in r.json()["detail"]


def test_rebuild_profile_success(client, tmp_path, monkeypatch):
    char = Character(name="Hero", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])
    monkeypatch.chdir(tmp_path)

    fake_extractor = MagicMock()
    fake_extractor.extract_and_generate.return_value = (
        {"hair": {"color": "dark"}}, "REBUILT_PROMPT"
    )
    extractor_cls = MagicMock(return_value=fake_extractor)

    with patch("api.image_routes._get_story_data", return_value=orch), \
         patch("services.character_visual_extractor.CharacterVisualExtractor", extractor_cls):
        r = client.post("/images/sess-r2/profiles/Hero/rebuild")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Hero"
    assert body["frozen_prompt"] == "REBUILT_PROMPT"
    assert body["rebuilt"] is True
    assert body["has_reference_image"] is False
    # Extractor invoked exactly once for the requested character
    assert fake_extractor.extract_and_generate.call_count == 1
    # Profile persisted under the per-story characters dir (title-scoped to "T").
    from services.output_paths import characters_dir
    assert (tmp_path / characters_dir("T") / "Hero" / "profile.json").exists()


def test_rebuild_profile_case_insensitive_match(client, tmp_path, monkeypatch):
    char = Character(name="Hero", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])
    monkeypatch.chdir(tmp_path)

    fake_extractor = MagicMock()
    fake_extractor.extract_and_generate.return_value = ({}, "P")
    extractor_cls = MagicMock(return_value=fake_extractor)

    with patch("api.image_routes._get_story_data", return_value=orch), \
         patch("services.character_visual_extractor.CharacterVisualExtractor", extractor_cls):
        r = client.post("/images/sess-r3/profiles/hero/rebuild")
    assert r.status_code == 200
    # Response uses canonical character name from the story
    assert r.json()["name"] == "Hero"


def test_rebuild_profile_in_flight_guard_same_character(client):
    char = Character(name="Hero", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])
    _in_flight.add("sess-r4::profile::Hero")
    try:
        with patch("api.image_routes._get_story_data", return_value=orch):
            r = client.post("/images/sess-r4/profiles/Hero/rebuild")
        assert r.status_code == 409
    finally:
        _in_flight.discard("sess-r4::profile::Hero")


def test_rebuild_profile_concurrent_different_characters(client, tmp_path, monkeypatch):
    """An in-flight rebuild for one character must NOT block another character."""
    chars = [
        Character(name="Hero", role="chính", appearance="tall", personality="brave"),
        Character(name="Villain", role="phản diện", appearance="dark", personality="cruel"),
    ]
    orch = _build_orch(num_chapters=1, characters=chars)
    monkeypatch.chdir(tmp_path)

    fake_extractor = MagicMock()
    fake_extractor.extract_and_generate.return_value = ({}, "P")
    extractor_cls = MagicMock(return_value=fake_extractor)

    # Pretend Hero is already being rebuilt — Villain should still succeed
    _in_flight.add("sess-r5::profile::Hero")
    try:
        with patch("api.image_routes._get_story_data", return_value=orch), \
             patch("services.character_visual_extractor.CharacterVisualExtractor", extractor_cls):
            r = client.post("/images/sess-r5/profiles/Villain/rebuild")
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Villain"
    finally:
        _in_flight.discard("sess-r5::profile::Hero")


def test_rebuild_profile_url_decoded_name(client, tmp_path, monkeypatch):
    """Character names with spaces/unicode arrive URL-encoded — must decode."""
    char = Character(name="Anh Hùng", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])
    monkeypatch.chdir(tmp_path)

    fake_extractor = MagicMock()
    fake_extractor.extract_and_generate.return_value = ({}, "P")
    extractor_cls = MagicMock(return_value=fake_extractor)

    encoded = "Anh%20H%C3%B9ng"
    with patch("api.image_routes._get_story_data", return_value=orch), \
         patch("services.character_visual_extractor.CharacterVisualExtractor", extractor_cls):
        r = client.post(f"/images/sess-r6/profiles/{encoded}/rebuild")
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Anh Hùng"


def _png_bytes(size_bytes: int = 128) -> bytes:
    """Return a tiny PNG-ish blob of `size_bytes` total length."""
    header = b"\x89PNG\r\n\x1a\n"
    pad = b"\x00" * max(0, size_bytes - len(header))
    return header + pad


def test_upload_reference_404_when_session_missing(client):
    with patch("api.image_routes._get_story_data", return_value=None):
        r = client.post(
            "/images/missing/profiles/Hero/reference",
            files={"file": ("hero.png", _png_bytes(), "image/png")},
        )
    assert r.status_code == 404


def test_upload_reference_404_when_character_not_found(client):
    char = Character(name="Hero", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])
    with patch("api.image_routes._get_story_data", return_value=orch):
        r = client.post(
            "/images/sess-u1/profiles/Ghost/reference",
            files={"file": ("g.png", _png_bytes(), "image/png")},
        )
    assert r.status_code == 404
    assert "Ghost" in r.json()["detail"]


def test_upload_reference_400_wrong_content_type(client):
    char = Character(name="Hero", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])
    with patch("api.image_routes._get_story_data", return_value=orch):
        r = client.post(
            "/images/sess-u2/profiles/Hero/reference",
            files={"file": ("hero.gif", b"GIF89a", "image/gif")},
        )
    assert r.status_code == 400


def test_upload_reference_413_oversized(client, tmp_path, monkeypatch):
    char = Character(name="Hero", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])
    monkeypatch.chdir(tmp_path)
    # Patch _PROJECT_ROOT so writes (if reached) stay in tmp_path
    monkeypatch.setattr("api.image_routes._PROJECT_ROOT", tmp_path)

    big = _png_bytes(8 * 1024 * 1024 + 100)
    with patch("api.image_routes._get_story_data", return_value=orch):
        r = client.post(
            "/images/sess-u3/profiles/Hero/reference",
            files={"file": ("big.png", big, "image/png")},
        )
    assert r.status_code == 413


def test_upload_reference_success_writes_file_and_updates_profile(
    client, tmp_path, monkeypatch
):
    char = Character(name="Hero", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("api.image_routes._PROJECT_ROOT", tmp_path)

    payload = _png_bytes(256)
    with patch("api.image_routes._get_story_data", return_value=orch):
        r = client.post(
            "/images/sess-u4/profiles/Hero/reference",
            files={"file": ("hero.png", payload, "image/png")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Hero"
    from services.output_paths import characters_dir, images_dir

    assert body["has_reference_image"] is True
    # Per-story layout: /media/<story-slug>/images/references/<session>/<char>.
    assert body["reference_url"].startswith("/media/t/images/references/sess-u4/Hero")

    # File written to expected path under the per-story images dir (title "T").
    expected = tmp_path / images_dir("T") / "references" / "sess-u4" / "Hero.png"
    assert expected.exists()
    assert expected.read_bytes() == payload

    # Profile updated with reference_image (relative path)
    profile_path = tmp_path / characters_dir("T") / "Hero" / "profile.json"
    assert profile_path.exists()
    import json as _json
    profile = _json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["reference_image"].endswith("Hero.png")


def test_upload_reference_in_flight_guard(client):
    char = Character(name="Hero", role="chính", appearance="tall", personality="brave")
    orch = _build_orch(num_chapters=1, characters=[char])
    _in_flight.add("sess-u5::ref::Hero")
    try:
        with patch("api.image_routes._get_story_data", return_value=orch):
            r = client.post(
                "/images/sess-u5/profiles/Hero/reference",
                files={"file": ("h.png", _png_bytes(), "image/png")},
            )
        assert r.status_code == 409
    finally:
        _in_flight.discard("sess-u5::ref::Hero")


def test_generate_single_chapter_in_flight_isolated_from_full(client):
    """In-flight key for a single chapter must not collide with full-story key."""
    orch = _build_orch(2)
    # Pretend a full-story regen is already running for sess-4
    _in_flight.add("sess-4")
    try:
        def fake_handler(orch_state, provider="none", t=None, chapter_number=None):
            for ch in orch_state.output.story_draft.chapters:
                if ch.chapter_number == chapter_number:
                    ch.images = ["ch01_panel01.png"]
            return ["ch01_panel01.png"], "ok"

        with patch("api.image_routes._get_story_data", return_value=orch), \
             patch("services.handlers.handle_generate_images", side_effect=fake_handler):
            r = client.post("/images/sess-4/generate", json={"chapter": 1})
        # Single-chapter request should NOT be blocked by full-story in-flight key
        assert r.status_code == 200
    finally:
        _in_flight.discard("sess-4")


# ---------------------------------------------------------------------------
# POST /images/library/generate — payload-based path for localStorage stories
# (no backend checkpoint). Mirrors the session endpoint's semantics.
# ---------------------------------------------------------------------------


def _library_payload(num_chapters: int = 2, *, chapters_with_images=None, characters=None):
    """Build a localStorage-shape Story payload for the library image endpoint.

    ``chapters_with_images`` is a set of 1-based chapter numbers that should
    arrive already illustrated (so incremental mode skips them).
    """
    with_images = chapters_with_images or set()
    chapters = []
    for i in range(1, num_chapters + 1):
        chapters.append(
            {
                "title": f"Ch{i}",
                "content": f"Body {i}",
                "summary": "",
                # Already-illustrated chapters carry the /media URLs a prior
                # response returned (what the client stores + re-sends).
                "images": ([f"/media/t/images/ch{i:02d}_panel01.png"] if i in with_images else []),
            }
        )
    return {
        "id": "story-abc",
        "title": "T",
        "genre": "g",
        "setting": "",
        "tone": "",
        "description": "s",
        "characters": list(characters or []),
        "chapters": chapters,
    }


def _poll_library_job(client, job_id: str, timeout: float = 5.0) -> dict:
    """Drive the async job to a terminal state and return its final status body.

    Phase B: POST returns 202 + job_id immediately; generation runs off the
    request thread (``asyncio.create_task`` → ``asyncio.to_thread`` for the
    mocked handler). Polling ``GET .../jobs/{id}`` lets the TestClient portal's
    event loop make progress between requests until the worker finishes.
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f"/images/library/jobs/{job_id}")
        assert r.status_code == 200, r.text
        last = r.json()
        if last["state"] in ("done", "error", "cancelled"):
            return last
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach a terminal state: {last}")


def test_library_generate_400_when_no_chapters(client):
    r = client.post(
        "/images/library/generate",
        json={"story": _library_payload(0), "provider": "none"},
    )
    assert r.status_code == 400


def test_library_generate_provider_none_completes_with_no_images(client, inline_jobs):
    """provider=none → job still runs to `done` but produces zero panels."""
    with patch("services.handlers.handle_generate_images", return_value=([], "no provider")):
        r = client.post(
            "/images/library/generate",
            json={"story": _library_payload(2), "provider": "none"},
        )
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]
        final = _poll_library_job(client, job_id)

    assert final["state"] == "done"
    assert final["count"] == 0
    # The FE keys "no provider configured" off provider=="none".
    assert final["provider"] == "none"


def test_library_generate_incremental_skips_chapters_with_images(client, inline_jobs):
    """only_missing (default) must generate ONLY chapters the payload shows empty."""
    called_for = []

    def fake_handler(orch_state, provider="none", t=None, chapter_number=None):
        called_for.append(chapter_number)
        for ch in orch_state.output.story_draft.chapters:
            if ch.chapter_number == chapter_number:
                ch.images = [f"t/images/ch{ch.chapter_number:02d}_panel01.png"]
        return [f"t/images/ch{chapter_number:02d}_panel01.png"], "ok"

    # 3 chapters; ch1 already illustrated → only ch2, ch3 should generate.
    with patch("services.handlers.handle_generate_images", side_effect=fake_handler):
        r = client.post(
            "/images/library/generate",
            json={"story": _library_payload(3, chapters_with_images={1}), "provider": "dalle"},
        )
        assert r.status_code == 202, r.text
        accepted = r.json()
        # The 202 reports the resolved scope up front.
        assert accepted["target_chapters"] == [2, 3]
        assert accepted["total_chapters"] == 3
        final = _poll_library_job(client, accepted["job_id"])

    assert final["state"] == "done"
    assert sorted(called_for) == [2, 3]
    assert final["skipped_chapters"] == [1]
    # Only the regenerated chapters accrete into chapter_images; the skipped ch1
    # is NOT echoed — the FE keeps it from localStorage (skipped_chapters tells
    # it which to preserve).
    assert "1" not in final["chapter_images"]
    assert final["chapter_images"]["2"] == ["/media/t/images/ch02_panel01.png"]
    assert final["chapter_images"]["3"] == ["/media/t/images/ch03_panel01.png"]


def test_library_generate_nothing_to_do_when_all_illustrated(client, inline_jobs):
    """only_missing with every chapter illustrated → empty scope, handler never runs.

    Regression guard: an empty target list must NOT be treated as "all chapters"
    by the worker (that bug would regenerate the whole story on a no-op call).
    """
    with patch("services.handlers.handle_generate_images") as handler:
        r = client.post(
            "/images/library/generate",
            json={"story": _library_payload(2, chapters_with_images={1, 2})},
        )
        assert r.status_code == 202, r.text
        accepted = r.json()
        assert accepted["target_chapters"] == []
        final = _poll_library_job(client, accepted["job_id"])

    handler.assert_not_called()
    assert final["state"] == "done"
    assert final["count"] == 0
    assert final["skipped_chapters"] == [1, 2]


def test_library_generate_single_chapter_scope(client, inline_jobs):
    captured = {}

    def fake_handler(orch_state, provider="none", t=None, chapter_number=None):
        captured["chapter_number"] = chapter_number
        for ch in orch_state.output.story_draft.chapters:
            if ch.chapter_number == chapter_number:
                ch.images = [f"t/images/ch{ch.chapter_number:02d}_panel01.png"]
        return ["t/images/ch02_panel01.png"], "ok"

    with patch("services.handlers.handle_generate_images", side_effect=fake_handler):
        r = client.post(
            "/images/library/generate",
            json={"story": _library_payload(3), "chapter": 2, "provider": "dalle"},
        )
        assert r.status_code == 202, r.text
        accepted = r.json()
        assert accepted["target_chapters"] == [2]
        final = _poll_library_job(client, accepted["job_id"])

    assert captured["chapter_number"] == 2
    assert final["state"] == "done"
    assert final["chapter_images"] == {"2": ["/media/t/images/ch02_panel01.png"]}


def test_library_generate_full_regenerate_cap(client):
    """only_missing=false beyond MAX_CHAPTERS_PER_IMAGE_CALL → 400."""
    from api.image_routes import MAX_CHAPTERS_PER_IMAGE_CALL

    r = client.post(
        "/images/library/generate",
        json={
            "story": _library_payload(MAX_CHAPTERS_PER_IMAGE_CALL + 1),
            "only_missing": False,
        },
    )
    assert r.status_code == 400


def test_library_generate_dedup_returns_existing_and_conflicts(client):
    """While a whole-story job is active: identical scope → 200 + already_running
    (reattach to the same job_id); overlapping-but-different scope → 409.

    Inject the active job directly so the dedup/conflict branches are exercised
    deterministically, without depending on worker scheduling or threading.
    """
    from api.image_routes import _LibraryJob

    _jobs["existing-job"] = _LibraryJob(
        job_id="existing-job",
        title_key="T",
        state="running",
        provider="dalle",
        panels_per_chapter=8,
        target_numbers=[1, 2],
        in_flight_key="library::T",  # whole-story scope
    )
    _in_flight.add("library::T")

    # Identical whole-story scope while active → 200, same job, reattached.
    dup = client.post(
        "/images/library/generate",
        json={"story": _library_payload(2), "only_missing": False},
    )
    assert dup.status_code == 200, dup.text
    assert dup.json()["already_running"] is True
    assert dup.json()["job_id"] == "existing-job"
    assert dup.json()["target_chapters"] == [1, 2]

    # Single-chapter request while the whole-story job runs → conflict (409).
    conflict = client.post(
        "/images/library/generate",
        json={"story": _library_payload(2), "chapter": 1},
    )
    assert conflict.status_code == 409


def test_library_generate_consistency_profile_scoped_to_title(client, tmp_path, monkeypatch, inline_jobs):
    """The payload path must auto-build profiles under the TITLE-scoped store —
    the same slug the checkpoint path uses — so Continue chapters stay consistent."""
    monkeypatch.chdir(tmp_path)

    fake_extractor = MagicMock()
    fake_extractor.extract_and_generate.return_value = ({"hair": {"color": "dark"}}, "FROZEN_HERO")
    extractor_cls = MagicMock(return_value=fake_extractor)
    image_gen = MagicMock()
    image_gen.generate_story_images.return_value = ["output/t/images/ch01_panel01.png"]
    prompt_gen = MagicMock()
    prompt_gen.generate_from_chapter.return_value = ["a prompt"]

    payload = _library_payload(
        1, characters=[{"name": "Hero", "role": "protagonist", "traits": {"strength": 50, "wisdom": 50, "agility": 50, "scheme": 50}, "description": "brave", "backstory": "", "secret": "", "conflict": ""}]
    )

    with patch("services.character_visual_extractor.CharacterVisualExtractor", extractor_cls), \
         patch("services.image_generator.ImageGenerator", return_value=image_gen), \
         patch("services.image_prompt_generator.ImagePromptGenerator", return_value=prompt_gen):
        r = client.post("/images/library/generate", json={"story": payload, "provider": "dalle"})
        assert r.status_code == 202, r.text
        final = _poll_library_job(client, r.json()["job_id"])

    assert final["state"] == "done"
    # Profile persisted under the per-story characters dir, title-scoped to "T" —
    # identical slug to the checkpoint path (no session suffix).
    from services.output_paths import characters_dir
    assert (tmp_path / characters_dir("T") / "Hero" / "profile.json").exists()
    _, kwargs = prompt_gen.generate_from_chapter.call_args
    assert kwargs.get("visual_profiles") == {"Hero": "FROZEN_HERO"}
