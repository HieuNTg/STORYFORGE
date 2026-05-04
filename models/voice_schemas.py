"""Voice-layer schemas for speaker-anchored dialogue revert (Sprint 3 P3)."""

from __future__ import annotations

import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DialogueAnchor(BaseModel):
    """Single dialogue span anchored to a speaker and ordinal."""

    model_config = ConfigDict(extra="forbid")

    speaker_id: str
    ordinal: int
    text: str
    char_offset: int


class DialogueAnchorDiff(BaseModel):
    """A proposed (or applied) revert: replace enhanced span with original at the same anchor."""

    model_config = ConfigDict(extra="forbid")

    speaker_id: str
    ordinal: int
    original_text: str
    enhanced_text: str
    action: Literal["revert", "skip_speaker_mismatch", "skip_no_original"]
    reason: str = ""


class VoicePreservationResult(BaseModel):
    """Result of voice preservation enforcement.

    Replaces the dataclass that lived inside voice_fingerprint.
    Attribute names kept identical so consumers need no body changes.
    """

    model_config = ConfigDict(extra="forbid")

    drifted_characters: list[str] = Field(default_factory=list)
    reverted_count: int = 0
    anchor_mismatch_count: int = 0
    diffs: list[DialogueAnchorDiff] = Field(default_factory=list)
    drift_examples: list[dict] = Field(default_factory=list)
    original_dialogues: list[str] = Field(default_factory=list)
    enhanced_dialogues: list[str] = Field(default_factory=list)
    preserved_dialogues: list[str] = Field(default_factory=list)
    # Backwards-compat fields retained from the old dataclass
    drift_severity: float = 0.0
    violations: list[dict] = Field(default_factory=list)


def resolve_speaker_id(character) -> str:
    """Canonical speaker_id for a Character.

    Precedence:
    1. character.id (UUID-ish string from typed schema)
    2. unicodedata.normalize("NFC", character.name).strip()

    Raises ValueError if both id and name are empty/absent.
    """
    cid = getattr(character, "id", None)
    if cid:
        return str(cid)
    name = getattr(character, "name", None)
    if name:
        return unicodedata.normalize("NFC", str(name)).strip()
    raise ValueError("Character has neither id nor name")
