"""Cheap lane classifier for raw suggestion strings.

P1-4: Simulator emits dramatic suggestions only; debate panel emits craft
critique only. Raw `str` suggestions need keyword-based classification before
they cross the lane boundary, since `LaneSuggestion` typing only catches
already-typed payloads.

Two-tier strategy:
1. Keyword/regex classifier (fast, deterministic, free).
2. Optional LLM classifier on `cheap_model` for ambiguous cases — gated by
   the caller, off by default.

Returns one of "dramatic", "craft", "ambiguous".
"""

from __future__ import annotations

import logging
import re
from typing import Literal

logger = logging.getLogger(__name__)

Lane = Literal["dramatic", "craft", "ambiguous"]

# Craft markers — prose mechanics, style, voice rendering, grammar, POV craft.
_CRAFT_PATTERNS = [
    r"\bvăn phong\b", r"\btừ ngữ\b", r"\bcâu văn\b", r"\bnhịp văn\b",
    r"\bgrammar\b", r"\bsyntax\b", r"\bword choice\b", r"\bdiction\b",
    r"\bprose\b", r"\bsentence structure\b", r"\bsentence length\b",
    r"\btelling not showing\b", r"\bshow.{0,3}don'?t tell\b",
    r"\bshow vs\.? tell\b", r"\bshow,? not tell\b",
    r"\bvăn xuôi\b", r"\bphép so sánh\b", r"\bẩn dụ\b", r"\bmetaphor\b",
    r"\bsimile\b", r"\bdescription quality\b", r"\bmiêu tả\b",
    r"\bvoice consistency\b", r"\btone consistency\b",
    r"\bdialogue tag\b", r"\bdialogue attribution\b",
    r"\bpacing of prose\b", r"\bsentence flow\b", r"\bpunctuation\b",
    r"\bdấu câu\b", r"\bchấm câu\b",
    r"\bperspective shift\b", r"\bpov shift\b", r"\bhead-?hopping\b",
    r"\btense shift\b", r"\bnarrative voice\b",
    r"\brepetitive\b", r"\bredundant\b",
    r"\bclarity\b", r"\bawkward phrasing\b",
]

# Dramatic markers — plot, conflict, stakes, character motivation, drama beats.
_DRAMATIC_PATTERNS = [
    r"\bxung đột\b", r"\bkịch tính\b", r"\bplot twist\b", r"\btwist\b",
    r"\bstakes\b", r"\btension\b", r"\bcăng thẳng\b",
    r"\bbetrayal\b", r"\bphản bội\b", r"\bsecret\b", r"\bbí mật\b",
    r"\bmotivation\b", r"\bđộng lực\b", r"\bgoal\b", r"\bmục tiêu\b",
    r"\bclimax\b", r"\bcao trào\b", r"\breveal\b", r"\btiết lộ\b",
    r"\bantagonist\b", r"\bphản diện\b", r"\bmục đích\b",
    r"\barc\b", r"\barc nhân vật\b", r"\bcharacter arc\b",
    r"\brelationship\b", r"\bquan hệ\b", r"\bconflict\b",
    r"\bambush\b", r"\bphục kích\b", r"\bambition\b", r"\btham vọng\b",
    r"\bstake\b", r"\bdrama\b", r"\bcatalyst\b",
    r"\bforeshadow\b", r"\bgieo mầm\b", r"\bpayoff\b",
    r"\bemotional beat\b", r"\bbeat cảm xúc\b",
]

_CRAFT_RE = re.compile("|".join(_CRAFT_PATTERNS), flags=re.IGNORECASE)
_DRAMATIC_RE = re.compile("|".join(_DRAMATIC_PATTERNS), flags=re.IGNORECASE)


def classify_lane(text: str) -> Lane:
    """Classify a raw suggestion string into "dramatic", "craft", or "ambiguous".

    Deterministic keyword match. Designed for caller filters — callers decide
    what to drop based on lane policy.
    """
    if not text:
        return "ambiguous"
    t = text.strip()
    craft_hit = bool(_CRAFT_RE.search(t))
    dramatic_hit = bool(_DRAMATIC_RE.search(t))
    if craft_hit and not dramatic_hit:
        return "craft"
    if dramatic_hit and not craft_hit:
        return "dramatic"
    if craft_hit and dramatic_hit:
        return "ambiguous"
    return "ambiguous"


def is_craft_drift(text: str) -> bool:
    """True if a raw string looks like clear craft critique that does NOT
    belong in dramatic-lane output (the simulator's emit lane).
    """
    return classify_lane(text) == "craft"
