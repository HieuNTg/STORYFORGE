"""Voice profile alias canonicalisation shim (Sprint 1, Phase 2).

Maps legacy voice profile field names to the canonical Sprint 1 form
(`verbal_tics`, `dialogue_examples`). Pure function, no I/O, idempotent.

`DeprecationWarning` is emitted at most once per process per legacy alias
to avoid log floods on bulk runs. See `plans/260503-2317-l1-l2-handoff-envelope/schema.md`.
"""

from __future__ import annotations

import warnings


_DEPRECATED_ALIASES: dict[str, str] = {
    "speech_quirks": "verbal_tics",
    "dialogue_example": "dialogue_examples",
    "dialogue_samples": "dialogue_examples",
}

_warned: set[str] = set()


def canonicalise_voice_profile(raw: dict) -> dict:
    """Map legacy voice profile keys onto canonical names.

    - Idempotent: calling twice on the same dict yields the same result.
    - Emits `DeprecationWarning` at most once per process per legacy alias.
    - Returns a shallow copy; never mutates `raw`.
    """
    if not isinstance(raw, dict):
        return raw
    out = dict(raw)
    for old, new in _DEPRECATED_ALIASES.items():
        if old in out and new not in out:
            if old not in _warned:
                _warned.add(old)
                warnings.warn(
                    f"voice profile alias '{old}' deprecated, use '{new}'",
                    DeprecationWarning,
                    stacklevel=2,
                )
            out[new] = out.pop(old)
        elif old in out:
            # Both legacy and canonical present — drop legacy silently after first warn
            if old not in _warned:
                _warned.add(old)
                warnings.warn(
                    f"voice profile alias '{old}' deprecated, use '{new}'",
                    DeprecationWarning,
                    stacklevel=2,
                )
            out.pop(old)
    return out
