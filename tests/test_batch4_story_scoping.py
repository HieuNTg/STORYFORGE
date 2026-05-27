"""Batch 4 Step 9 smoke test: prove story_id scoping prevents
cross-contamination between two stories that share character names.

The pre-Batch-3 bug: avatar files were keyed only by `safe_character_name`,
so if Story A and Story B both featured a character "Lan", running Story B
overwrote Story A's avatar (different visual) on disk. Same for scene
images dropped under `output/images/scenes/`.

These tests run without a live backend — they exercise the same code
paths the production pipeline uses (`find_existing_avatar` for the avatar
hit-check, `slug_session_dir` for the scene output directory) and assert
that two stories with identical character names land in *different*
filesystem locations.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from services.character_avatar import find_existing_avatar
from services.media._util import slug_session_dir
from services.safe_name import safe_character_name


def _drop_avatar(root: str, story_id: str | None, name: str, size_bytes: int = 4096) -> str:
    """Write a >1KB placeholder avatar (find_existing_avatar's threshold)."""
    safe = safe_character_name(name)
    if story_id:
        scoped = os.path.join(root, "output", "images", "avatars", safe_character_name(story_id))
    else:
        scoped = os.path.join(root, "output", "images", "avatars")
    os.makedirs(scoped, exist_ok=True)
    path = os.path.join(scoped, f"{safe}.png")
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG" + b"\x00" * (size_bytes - 4))
    return path


class AvatarStoryScopingSmoke(unittest.TestCase):
    """find_existing_avatar must honor story_id so two stories with the
    same character name don't collide on disk."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="storyforge_batch4_")
        # find_existing_avatar resolves paths relative to CWD, so cd into
        # the temp dir for the duration of each test.
        self._old_cwd = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self._old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_two_stories_same_character_resolve_to_different_files(self):
        """Story A and Story B both have a "Lan" — finder must return the
        per-story avatar, not the other story's file."""
        story_a = "story-aaaaaaaa"
        story_b = "story-bbbbbbbb"
        path_a = _drop_avatar(self.tmp, story_a, "Lan")
        path_b = _drop_avatar(self.tmp, story_b, "Lan")

        # Both files exist on disk, in different scoped directories.
        self.assertNotEqual(path_a, path_b)
        self.assertTrue(os.path.exists(path_a))
        self.assertTrue(os.path.exists(path_b))

        hit_a = find_existing_avatar("Lan", story_id=story_a)
        hit_b = find_existing_avatar("Lan", story_id=story_b)

        self.assertIsNotNone(hit_a)
        self.assertIsNotNone(hit_b)
        self.assertIn(safe_character_name(story_a), hit_a.replace("\\", "/"))
        self.assertIn(safe_character_name(story_b), hit_b.replace("\\", "/"))
        # Crucial: the two stories DO NOT return the same path.
        self.assertNotEqual(os.path.normpath(hit_a), os.path.normpath(hit_b))

    def test_legacy_unscoped_avatar_still_found_when_story_id_missing(self):
        """Pre-Batch-3 avatars dropped at the unscoped legacy path must
        still be discoverable for backward compatibility."""
        legacy = _drop_avatar(self.tmp, None, "Minh")
        hit = find_existing_avatar("Minh", story_id="any-new-story")
        # When the scoped path is missing, the legacy unscoped path acts
        # as a fallback so existing stories keep rendering. The finder
        # returns a CWD-relative path, so compare the tail against the
        # legacy file we just wrote.
        self.assertIsNotNone(hit)
        self.assertTrue(
            os.path.normpath(legacy).endswith(os.path.normpath(hit)),
            f"legacy fallback miss: hit={hit!r} legacy={legacy!r}",
        )

    def test_zero_byte_avatar_treated_as_missing(self):
        """A 0-byte avatar (FlowService crashed mid-write) must not be
        returned — downstream callers need a chance to regenerate."""
        story_id = "story-corrupt"
        safe = safe_character_name("Hùng")
        scoped = os.path.join(self.tmp, "output", "images", "avatars", safe_character_name(story_id))
        os.makedirs(scoped, exist_ok=True)
        bad = os.path.join(scoped, f"{safe}.png")
        with open(bad, "wb"):
            pass  # 0 bytes
        hit = find_existing_avatar("Hùng", story_id=story_id)
        self.assertIsNone(hit)


class SceneOutputScopingSmoke(unittest.TestCase):
    """slug_session_dir must produce a unique directory per session so
    scene images for Story A and Story B never overwrite each other."""

    def test_same_title_different_session_yields_different_dirs(self):
        """Two stories called "Ánh Trăng" with different session_ids
        must NOT share a scene-image directory."""
        d1 = slug_session_dir("Ánh Trăng", "session-aaa-111")
        d2 = slug_session_dir("Ánh Trăng", "session-bbb-222")
        self.assertNotEqual(d1, d2)
        # Sanity: both share the slugified title prefix.
        self.assertTrue(d1.startswith("anh_trang_"))
        self.assertTrue(d2.startswith("anh_trang_"))

    def test_vietnamese_diacritics_stripped(self):
        """Vietnamese is the default naming convention — title slugs must
        NFKD-normalize so combining-mark diacritics (á, ế, ư, etc.) get
        flattened to ASCII for cross-platform filesystem safety.

        Known limitation: "Đ" (U+0110 LATIN CAPITAL LETTER D WITH STROKE)
        is not decomposable under NFKD — it's a standalone letter, not a
        base+combining-mark sequence — so it currently disappears from
        the slug instead of mapping to "D". Tracked separately; not a
        collision risk because the session_id suffix still uniques the
        directory name.
        """
        d = slug_session_dir("Ánh Trăng Tiên Hiệp", "sess-xyz")
        self.assertTrue(d.startswith("anh_trang_tien_hiep_"))
        # No non-ASCII survives into the directory name.
        for ch in d:
            self.assertTrue(ch.isascii(), f"non-ascii char survived: {ch!r}")

    def test_empty_title_falls_back_to_story(self):
        """Empty / whitespace title must not produce a bare _sid dir."""
        d = slug_session_dir("", "sess-1")
        self.assertEqual(d, "story_sess-1")

    def test_empty_session_id_falls_back_to_session(self):
        """Missing session_id is a programmer bug — fail loudly with a
        deterministic stub instead of producing a colliding bare-title
        directory."""
        d = slug_session_dir("Mộng", "")
        self.assertEqual(d, "mong_session")


if __name__ == "__main__":
    unittest.main()
