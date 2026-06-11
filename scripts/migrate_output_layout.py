#!/usr/bin/env python3
"""Migrate StoryForge's ``output/`` tree from type-grouped to per-story layout.

Old layout (grouped by file type)::

    output/
      characters/<CharName>/profile.json
      images/<slug_title>_<session>/...        # scene / chapter panels
      images/avatars/[<story-id>/]<char>.png    # portraits (scoped or not)
      images/ch01_panel01.png                   # loose, unattributable
      checkpoints/<slug>_layer<N>_<hash>.json   # + .usage.json / .bak sidecars
      checkpoints/per_chapter/...
      library/<slug>-<hash>.{pdf,epub,docx}     # exports
      story.epub / story.pdf / test_book.pdf    # root junk
      *.png                                     # stray screenshots

New layout (grouped by story, owned by services.output_paths)::

    output/<story-slug>/
      characters/<CharName>/profile.json
      images/...
      images/avatars/...
      checkpoints/<...>.json (+ per_chapter/)
      exports/...

Attribution strategy
---------------------
* **Checkpoints** carry the story title inside the JSON
  (``story_draft.title`` / ``enhanced_story.title``); we read it and resolve the
  new slug via :func:`services.output_paths.story_slug`. Sidecars
  (``.usage.json`` / ``.history.json``) and ``.bak`` files travel with their
  checkpoint by basename. Per-chapter files move under ``checkpoints/per_chapter``.
* **Scene-image subdirs** (``images/<slug>_<session>``) are already a
  ``slug_session_dir`` token, so the directory name *is* the story slug — moved
  as-is under ``output/<slug>/images/``.
* **Avatars** scoped as ``images/avatars/<story-id>/<char>.png`` resolve to that
  story's slug. Unscoped avatars (``images/avatars/<char>.png``) are
  unattributable → ``_unsorted``.
* **Character profile folders, library exports, loose panels** have no reliable
  story handle and go to ``output/_unsorted/{characters,exports,images}/``.
* **Root junk** (``story.epub``, ``story.pdf``, ``test_book.pdf``, stray
  top-level ``*.png``) is deleted.

The script is **idempotent** (re-running after a successful migration is a
no-op: per-story folders are skipped, junk is already gone) and **dry-run by
default**. Pass ``--apply`` to actually move/delete. ``STORYFORGE_OUTPUT_ROOT``
is honoured (defaults to ``output``).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Allow running as a bare script (python scripts/migrate_output_layout.py).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from services.output_paths import (  # noqa: E402
    OUTPUT_ROOT,
    UNSORTED_SLUG,
    story_slug,
)

# Type-grouped subdirs that the OLD layout owned at the root of output/.
# Anything else that is already a directory at the root is treated as an
# existing per-story folder and left untouched (idempotency).
_LEGACY_GROUP_DIRS = {"characters", "images", "checkpoints", "library"}

# Root-level files to delete outright (junk from manual exports / screenshots).
_ROOT_JUNK_NAMES = {"story.epub", "story.pdf", "test_book.pdf"}

# Sidecar / backup suffixes that ride along with their checkpoint by basename.
_CHECKPOINT_SIDECAR_RE = re.compile(
    r"^(?P<stem>.+?)(?:\.usage|\.history)?\.json(?:\.bak)?$"
)

# Layer checkpoints are named ``<slug>_layer<N>_<hash16>.json`` while their
# sidecars are ``<slug>_layer<N>.usage.json`` (no hash). Normalise both to the
# hash-free ``<slug>_layer<N>`` key so a sidecar co-locates with its checkpoint.
_LAYER_HASH_RE = re.compile(r"^(?P<base>.+_layer\d+)_[0-9a-f]{8,}$")

# A scene-image subdir name looks like ``<slug>_<uuid-or-session>``; we move it
# verbatim because the directory name is already the resolver's story slug.
_PER_CHAPTER = "per_chapter"


@dataclass
class Plan:
    """Accumulated migration actions (printed as the summary)."""

    moves: list[tuple[Path, Path]] = field(default_factory=list)
    deletes: list[Path] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)

    def move(self, src: Path, dst: Path) -> None:
        self.moves.append((src, dst))

    def delete(self, p: Path) -> None:
        self.deletes.append(p)

    def skip(self, p: Path, why: str) -> None:
        self.skipped.append((p, why))


def _output_root() -> Path:
    root = Path(OUTPUT_ROOT)
    if not root.is_absolute():
        root = (_PROJECT_ROOT / root).resolve()
    return root


def _unsorted_root(root: Path) -> Path:
    return root / UNSORTED_SLUG


def _title_from_checkpoint(path: Path) -> str | None:
    """Best-effort read of the story title from a checkpoint JSON."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    draft = data.get("story_draft") or {}
    enhanced = data.get("enhanced_story") or {}
    title = (draft.get("title") if isinstance(draft, dict) else None) or (
        enhanced.get("title") if isinstance(enhanced, dict) else None
    )
    return title or None


def _checkpoint_stem(filename: str) -> str:
    """Hash-free key tying a checkpoint and its sidecars together.

    ``Foo_layer1_<hash>.json`` and ``Foo_layer1.usage.json`` both reduce to the
    key ``Foo_layer1`` so the sidecar follows its checkpoint to the same story.
    """
    m = _CHECKPOINT_SIDECAR_RE.match(filename)
    stem = m.group("stem") if m else filename
    h = _LAYER_HASH_RE.match(stem)
    return h.group("base") if h else stem


def _plan_checkpoints(root: Path, plan: Plan) -> None:
    """Move ``output/checkpoints/*`` into ``output/<slug>/checkpoints/``.

    Title is resolved from the matching ``*.json`` checkpoint; sidecars/.bak
    follow their checkpoint by basename. Files whose title can't be resolved go
    to ``_unsorted``.
    """
    src_dir = root / "checkpoints"
    if not src_dir.is_dir():
        return

    # Pass 1: resolve a target slug per checkpoint *stem* from the real .json.
    stem_slug: dict[str, str] = {}
    for entry in sorted(src_dir.iterdir()):
        if (
            entry.is_file()
            and entry.name.endswith(".json")
            and not entry.name.endswith((".usage.json", ".history.json"))
        ):
            title = _title_from_checkpoint(entry)
            slug = story_slug(title) if title else UNSORTED_SLUG
            stem_slug[_checkpoint_stem(entry.name)] = slug

    def _target_dir(slug: str, *, per_chapter: bool) -> Path:
        base = root / slug / "checkpoints"
        return base / _PER_CHAPTER if per_chapter else base

    # Pass 2: move every file/dir, mapping sidecars via their stem.
    for entry in sorted(src_dir.iterdir()):
        if entry.is_dir() and entry.name == _PER_CHAPTER:
            for f in sorted(entry.iterdir()):
                if not f.is_file():
                    continue
                slug = stem_slug.get(_checkpoint_stem(f.name), UNSORTED_SLUG)
                plan.move(f, _target_dir(slug, per_chapter=True) / f.name)
            continue
        if not entry.is_file():
            plan.skip(entry, "unexpected non-file in checkpoints/")
            continue
        slug = stem_slug.get(_checkpoint_stem(entry.name), UNSORTED_SLUG)
        plan.move(entry, _target_dir(slug, per_chapter=False) / entry.name)


def _plan_images(root: Path, plan: Plan) -> None:
    """Move scene-image subdirs and avatars into per-story ``images/``."""
    src_dir = root / "images"
    if not src_dir.is_dir():
        return

    for entry in sorted(src_dir.iterdir()):
        if entry.name == "avatars" and entry.is_dir():
            _plan_avatars(root, entry, plan)
            continue
        if entry.is_dir():
            # ``<slug>_<session>`` subdir: the name already IS the story slug.
            plan.move(entry, root / entry.name / "images" / entry.name)
            continue
        # Loose panel file at images/ root — unattributable.
        plan.move(entry, _unsorted_root(root) / "images" / entry.name)


def _plan_avatars(root: Path, avatars_dir: Path, plan: Plan) -> None:
    """Move ``images/avatars/[<story-id>/]<char>.png`` into per-story avatars."""
    for entry in sorted(avatars_dir.iterdir()):
        if entry.is_dir():
            # Scoped: directory name is the frontend story_id.
            slug = story_slug(story_id=entry.name)
            for f in sorted(entry.iterdir()):
                if f.is_file():
                    plan.move(f, root / slug / "images" / "avatars" / f.name)
            continue
        # Unscoped avatar — no story handle.
        plan.move(entry, _unsorted_root(root) / "images" / "avatars" / entry.name)


def _plan_characters(root: Path, plan: Plan) -> None:
    """Move ``output/characters/<CharName>/`` → ``_unsorted/characters/``.

    Legacy character profiles were never story-scoped on disk, so there is no
    reliable handle to attribute them; they land in ``_unsorted`` where the
    title-scoped store will simply regenerate fresh ones on next run.
    """
    src_dir = root / "characters"
    if not src_dir.is_dir():
        return
    for entry in sorted(src_dir.iterdir()):
        plan.move(entry, _unsorted_root(root) / "characters" / entry.name)


def _plan_library(root: Path, plan: Plan) -> None:
    """Move ``output/library/*`` → ``_unsorted/exports/`` (no story handle)."""
    src_dir = root / "library"
    if not src_dir.is_dir():
        return
    for entry in sorted(src_dir.iterdir()):
        plan.move(entry, _unsorted_root(root) / "exports" / entry.name)


def _plan_root_junk(root: Path, plan: Plan) -> None:
    """Delete known junk + stray top-level ``*.png`` at the output root."""
    for entry in sorted(root.iterdir()):
        if not entry.is_file():
            continue
        if entry.name in _ROOT_JUNK_NAMES or entry.suffix.lower() == ".png":
            plan.delete(entry)
        else:
            plan.skip(entry, "unrecognised root file (left in place)")


def build_plan(root: Path) -> Plan:
    plan = Plan()
    if not root.is_dir():
        return plan
    # Order matters: images/ before characters/ etc. is irrelevant since each
    # planner only touches its own subtree; root junk last so it doesn't race
    # with the group dirs.
    _plan_checkpoints(root, plan)
    _plan_images(root, plan)
    _plan_characters(root, plan)
    _plan_library(root, plan)
    _plan_root_junk(root, plan)
    return plan


def _safe_move(src: Path, dst: Path) -> None:
    """Move ``src`` to ``dst``, creating parents and avoiding clobber."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    final = dst
    if final.exists():
        # Collision (e.g. two stories slugged the same): suffix to preserve both.
        stem, suffix = final.stem, final.suffix
        i = 1
        while final.exists():
            final = final.with_name(f"{stem}__dup{i}{suffix}")
            i += 1
    shutil.move(str(src), str(final))


def _prune_empty(root: Path) -> list[Path]:
    """Remove now-empty legacy group dirs. Returns the dirs removed."""
    removed: list[Path] = []
    for name in _LEGACY_GROUP_DIRS:
        d = root / name
        if d.is_dir():
            # Remove nested empties bottom-up.
            for sub in sorted(d.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if sub.is_dir() and not any(sub.iterdir()):
                    sub.rmdir()
            if not any(d.iterdir()):
                d.rmdir()
                removed.append(d)
    return removed


def apply_plan(plan: Plan, root: Path) -> list[Path]:
    for src, dst in plan.moves:
        if src.exists():
            _safe_move(src, dst)
    for p in plan.deletes:
        if p.exists():
            p.unlink()
    return _prune_empty(root)


def _rel(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root.parent))
    except ValueError:
        return str(p)


def print_summary(plan: Plan, root: Path, *, applied: bool, pruned: list[Path]) -> None:
    mode = "APPLIED" if applied else "DRY-RUN (no changes written)"
    print(f"\n=== StoryForge output migration — {mode} ===")
    print(f"output root: {root}\n")

    print(f"MOVES ({len(plan.moves)}):")
    for src, dst in plan.moves:
        print(f"  {_rel(src, root)}  ->  {_rel(dst, root)}")
    if not plan.moves:
        print("  (none)")

    print(f"\nDELETES ({len(plan.deletes)}):")
    for p in plan.deletes:
        print(f"  {_rel(p, root)}")
    if not plan.deletes:
        print("  (none)")

    if plan.skipped:
        print(f"\nSKIPPED ({len(plan.skipped)}):")
        for p, why in plan.skipped:
            print(f"  {_rel(p, root)}  — {why}")

    if applied and pruned:
        print(f"\nPRUNED EMPTY DIRS ({len(pruned)}):")
        for p in pruned:
            print(f"  {_rel(p, root)}")

    print(
        f"\nSummary: {len(plan.moves)} move(s), {len(plan.deletes)} delete(s), "
        f"{len(plan.skipped)} skipped."
    )
    if not applied:
        print("Re-run with --apply to perform these actions.")


def main(argv: list[str] | None = None) -> int:
    # Vietnamese story slugs contain non-cp1252 chars; force UTF-8 on the
    # Windows console so the summary never dies on an encode error.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move/delete files (default is a dry-run).",
    )
    args = parser.parse_args(argv)

    root = _output_root()
    plan = build_plan(root)
    pruned: list[Path] = []
    if args.apply:
        pruned = apply_plan(plan, root)
    print_summary(plan, root, applied=args.apply, pruned=pruned)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
