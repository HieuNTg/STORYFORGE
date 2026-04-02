# StoryForge Plugin System

Plugins extend StoryForge without modifying core files. The loader auto-discovers
any `StoryForgePlugin` subclass in `.py` files inside the `plugins/` directory.

---

## Quick Start

1. Copy `example-custom-genre.py` to a new file, e.g. `plugins/my-plugin.py`.
2. Subclass `StoryForgePlugin`, set `name` / `version`, and override the hooks you need.
3. Restart the server — the loader imports all `plugins/*.py` files at startup.

---

## Hook Reference

### `on_genre_rules(genre, rules) -> dict | None`

Called before drama rules are applied to a chapter enhancement pass.

- **`genre`** — genre name string, e.g. `"Tiên Hiệp"`.
- **`rules`** — current rule dict (keys: `escalation_pattern`, `key_beats`,
  `tension_curve`, `dialogue_style`, `emotional_peaks`, `pacing_note`).
- Return a **new or modified dict** to replace the rules, or **`None`** to leave them unchanged.

Use this hook to add custom genres or tweak existing ones.

### `on_score(scores) -> dict | None`

Called after `QualityScorer` produces chapter scores.

- **`scores`** — dict with keys `coherence`, `character_consistency`, `drama`,
  `writing_quality`, `overall` (all floats in 1–5 range).
- Return a **modified dict** to override scores, or **`None`** to leave them unchanged.

Use this hook to apply post-hoc adjustments, penalties, or bonuses.

### `on_export(format, data) -> Any | None`

Called before story data is serialised by an exporter.

- **`format`** — export format string: `"epub"`, `"pdf"`, `"html"`, `"wattpad"`, etc.
- **`data`** — format-specific payload (typically a dict or dataclass).
- Return **modified data** or **`None`** to leave it unchanged.

Use this hook to inject metadata, watermarks, or custom formatting.

---

## Plugin Template

```python
# plugins/my-plugin.py
from __future__ import annotations
from typing import Any
from plugins.base import StoryForgePlugin


class MyPlugin(StoryForgePlugin):
    name = "my-plugin"
    version = "1.0.0"
    description = "What this plugin does."

    def register(self) -> None:
        # Validate config, connect to external services, etc.
        pass

    def on_genre_rules(self, genre: str, rules: dict) -> dict | None:
        if genre == "My Custom Genre":
            return {"escalation_pattern": "custom", "key_beats": [...], ...}
        return None

    def on_score(self, scores: dict) -> dict | None:
        # Example: penalise very low coherence
        if scores.get("coherence", 5) < 2.0:
            adjusted = dict(scores)
            adjusted["writing_quality"] = max(1.0, adjusted.get("writing_quality", 3) - 0.5)
            return adjusted
        return None

    def on_export(self, format: str, data: Any) -> Any | None:
        if format == "epub":
            data["metadata"]["publisher"] = "My Studio"
            return data
        return None
```

---

## Custom Genre Rules Schema

```python
{
    "escalation_pattern": str,   # e.g. "power_progression", "revenge_arc"
    "key_beats": list[str],      # exactly 4 plot beat strings
    "tension_curve": str,        # "ascending_steps" | "wave" | "oscillating" | ...
    "dialogue_style": str,       # short description of dialogue register
    "emotional_peaks": list[str],# 3 peak emotion labels
    "pacing_note": str,          # guidance for chapter pacing
}
```

---

## Loading Order

Plugins are loaded in **alphabetical file name order**. Within each plugin,
hooks are called in **registration order** (first registered, first called).
Each hook receives the output of the previous plugin, so order matters when
multiple plugins modify the same data.

---

## Error Handling

If a plugin's `register()` or any hook raises an exception, the error is
logged at `ERROR` level and the pipeline continues with the original data.
A faulty plugin will never crash the generation pipeline.
