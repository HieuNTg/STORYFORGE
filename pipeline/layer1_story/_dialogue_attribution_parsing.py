"""Regex-based dialogue parsing for attribution validation.

Internal module for ``dialogue_attribution_validator``: Vietnamese dialogue
pattern constants, the :class:`DialogueLine` dataclass, and the raw-text
extraction/detection helpers. Public names are re-exported from
``dialogue_attribution_validator`` so existing import paths keep working.
"""

import re
from dataclasses import dataclass

# Vietnamese dialogue patterns
DIALOGUE_PATTERN = re.compile(r'[""「『]([^""」』]+)[""」』]')
ATTRIBUTION_PATTERN = re.compile(
    r"(\w+)\s*(?:nói|hỏi|đáp|thì thầm|gào|la|cười|trả lời|thốt|kêu|rên|rít)",
    re.IGNORECASE,
)
# Trailing attribution: "..." - Tên nói
TRAILING_ATTR = re.compile(r'[""」』]\s*[-–—]\s*(\w+)', re.IGNORECASE)


@dataclass
class DialogueLine:
    """A parsed dialogue line."""

    text: str
    speaker: str = ""
    attribution_type: str = ""  # 'prefix' | 'suffix' | 'context' | 'unclear'
    confidence: float = 0.0
    line_number: int = 0


def extract_dialogue_lines(content: str) -> list[DialogueLine]:
    """Extract dialogue lines with basic attribution detection."""
    lines = content.split("\n")
    dialogues = []

    for i, line in enumerate(lines):
        matches = DIALOGUE_PATTERN.findall(line)
        if not matches:
            continue

        for dialogue_text in matches:
            if len(dialogue_text) < 5:
                continue

            dl = DialogueLine(
                text=dialogue_text[:100],
                line_number=i + 1,
            )

            # Check for prefix attribution
            prefix_match = ATTRIBUTION_PATTERN.search(
                line.split(dialogue_text)[0] if dialogue_text in line else ""
            )
            if prefix_match:
                dl.speaker = prefix_match.group(1)
                dl.attribution_type = "prefix"
                dl.confidence = 0.9

            # Check for trailing attribution
            if not dl.speaker:
                trailing_match = TRAILING_ATTR.search(line)
                if trailing_match:
                    dl.speaker = trailing_match.group(1)
                    dl.attribution_type = "suffix"
                    dl.confidence = 0.85

            # Check for name in same line
            if not dl.speaker:
                attr_match = ATTRIBUTION_PATTERN.search(line)
                if attr_match:
                    dl.speaker = attr_match.group(1)
                    dl.attribution_type = "context"
                    dl.confidence = 0.7

            if not dl.speaker:
                dl.attribution_type = "unclear"
                dl.confidence = 0.0

            dialogues.append(dl)

    return dialogues


def detect_rapid_exchange(content: str, threshold: int = 4) -> list[dict]:
    """Detect rapid dialogue exchanges that may confuse readers.

    Returns list of segments with rapid back-and-forth.
    """
    lines = content.split("\n")
    rapid_exchanges = []
    consecutive_dialogue = 0
    start_line = 0

    for i, line in enumerate(lines):
        if DIALOGUE_PATTERN.search(line):
            if consecutive_dialogue == 0:
                start_line = i
            consecutive_dialogue += 1
        else:
            if consecutive_dialogue >= threshold:
                rapid_exchanges.append(
                    {
                        "start_line": start_line + 1,
                        "end_line": i,
                        "dialogue_count": consecutive_dialogue,
                    }
                )
            consecutive_dialogue = 0

    # Check final segment
    if consecutive_dialogue >= threshold:
        rapid_exchanges.append(
            {
                "start_line": start_line + 1,
                "end_line": len(lines),
                "dialogue_count": consecutive_dialogue,
            }
        )

    return rapid_exchanges
