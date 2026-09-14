"""Batch L, step L0 — measure the entity and shot-list gaps before fixing them.

usage: python scripts/measure_entity_gaps.py [output_root]

Reads saved checkpoints under output/*/checkpoints (no LLM calls) and reports,
per story text (draft and, when present, the enhanced story):

1. Chapter length against shot_list.CONTENT_WINDOW: how often the storyboard
   extractor never sees the end of a chapter, and how much it misses.
2. Every validate_character_names warning, split into
   - "variant of a real name token": the flagged group CONTAINS a character's
     full or given name (e.g. 'Hạnh Cô' for Nguyễn Thị Hạnh) — an address form
     or title, which an alias table would clear;
   - "edit distance": no whole name token inside — a genuine misspelling
     candidate the detector should keep flagging.
   Both lists are printed so a person can label a sample.
3. Chapters where a character is referred to only by a partial name, which
   CharacterStateRegistry's `full_name in content` check treats as absent.

Saved shot lists are not persisted to disk, so the "subject without reference"
rate cannot be measured from checkpoints; it is reported as not measurable.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import Counter

from pipeline.layer1_story.consistency_validators import validate_character_names
from services.media.shot_list import CONTENT_WINDOW

MIN_REAL_CHAPTER_CHARS = 1000  # below this the checkpoint is a test fixture

_WARN_RE = re.compile(r"'(?P<found>[^']+)' \(giống '(?P<valid>[^']+)'\)")


class _Char:
    def __init__(self, name: str):
        self.name = name


def _word_in(needle: str, haystack: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack, re.IGNORECASE) is not None


def _stories(root: str):
    """One entry per story directory: its largest content checkpoint."""
    by_story: dict[str, str] = {}
    for path in glob.glob(os.path.join(root, "*", "checkpoints", "*.json")):
        if path.endswith((".usage.json", ".history.json")):
            continue
        story = path.split(os.sep)[-3]
        if story not in by_story or os.path.getsize(path) > os.path.getsize(by_story[story]):
            by_story[story] = path
    for story, path in sorted(by_story.items()):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        yield story, data


def _texts(data: dict):
    draft = data.get("story_draft") or {}
    characters = [c.get("name", "") for c in draft.get("characters") or [] if isinstance(c, dict)]
    for label in ("story_draft", "enhanced_story"):
        chapters = (data.get(label) or {}).get("chapters") or []
        contents = [(c.get("chapter_number"), c.get("content") or "") for c in chapters if isinstance(c, dict)]
        if contents and max(len(t) for _, t in contents) >= MIN_REAL_CHAPTER_CHARS:
            yield label, characters, contents


def main() -> None:
    root = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("STORYFORGE_OUTPUT_ROOT", "output")
    totals = Counter()
    variant_samples: list[str] = []
    distance_samples: list[str] = []
    partial_only: list[str] = []

    print(f"# L0 measurement — CONTENT_WINDOW={CONTENT_WINDOW} chars\n")
    print("| story | text | chapters | over window | chars never storyboarded | name warnings (variant / edit-distance) |")
    print("| --- | --- | --- | --- | --- | --- |")

    for story, data in _stories(root):
        for label, names, contents in _texts(data):
            chars = [_Char(n) for n in names if n]
            tokens = {n: {n, n.split()[-1]} for n in names if n}
            over = [len(t) for _, t in contents if len(t) > CONTENT_WINDOW]
            lost = sum(n - CONTENT_WINDOW for n in over)
            n_var = n_dist = 0
            for num, text in contents:
                for w in validate_character_names(text, chars):
                    m = _WARN_RE.search(w)
                    found = m.group("found") if m else w
                    is_variant = any(
                        _word_in(tok, found) for toks in tokens.values() for tok in toks
                    )
                    line = f"{story}/{label} ch{num}: {w}"
                    if is_variant:
                        n_var += 1
                        variant_samples.append(line)
                    else:
                        n_dist += 1
                        distance_samples.append(line)
                for full, toks in tokens.items():
                    if full.lower() not in text.lower() and any(
                        _word_in(t, text) for t in toks - {full}
                    ):
                        partial_only.append(f"{story}/{label} ch{num}: {full}")
            totals.update(
                texts=1, chapters=len(contents), over=len(over), lost=lost, variant=n_var, distance=n_dist
            )
            print(
                f"| {story} | {label} | {len(contents)} | {len(over)} | {lost} | {n_var} / {n_dist} |"
            )

    ch = totals["chapters"] or 1
    warn = (totals["variant"] + totals["distance"]) or 1
    print("\n## Totals\n")
    print(f"- texts measured: {totals['texts']}, chapters: {totals['chapters']}")
    print(f"- chapters longer than the window: {totals['over']} ({100 * totals['over'] / ch:.0f}%), "
          f"{totals['lost']} chars never shown to the storyboard extractor")
    print(f"- name warnings: {totals['variant'] + totals['distance']} — "
          f"{totals['variant']} contain a real name token ({100 * totals['variant'] / warn:.0f}%), "
          f"{totals['distance']} are edit-distance only")
    print(f"- character referred to only by a partial name (registry counts them absent): {len(partial_only)} chapter-character pairs")
    print("- shot-list subjects without a reference: not measurable (shot lists are not persisted)")

    for title, rows in (
        ("Warnings containing a real name token (label: alias/title vs misspelling)", variant_samples),
        ("Edit-distance-only warnings", distance_samples),
        ("Partial-name-only presence", partial_only),
    ):
        print(f"\n## {title}\n")
        for row in rows[:40] or ["(none)"]:
            print(f"- {row}")


if __name__ == "__main__":
    main()
