"""Character secret tracker — monitors when character secrets are revealed.

Feature #14: Prevent premature secret reveals and track revelation timing.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.llm_client import LLMClient
    from models.schemas import Character

logger = logging.getLogger(__name__)


@dataclass
class SecretEntry:
    """A character secret to track."""
    character: str
    secret: str
    reveal_chapter: int | None = None  # Planned reveal chapter
    actual_reveal: int | None = None   # When actually revealed
    revealed_to: list[str] = field(default_factory=list)
    partial_hints: list[dict] = field(default_factory=list)  # [{chapter, hint}]


@dataclass
class SecretRegistry:
    """Track all character secrets across story."""
    secrets: list[SecretEntry] = field(default_factory=list)

    def add_secret(
        self,
        character: str,
        secret: str,
        reveal_chapter: int | None = None,
    ) -> None:
        """Register a character secret."""
        self.secrets.append(SecretEntry(
            character=character,
            secret=secret,
            reveal_chapter=reveal_chapter,
        ))

    def get_unrevealed(self, by_chapter: int | None = None) -> list[SecretEntry]:
        """Get secrets not yet revealed, optionally filtered by deadline."""
        unrevealed = [s for s in self.secrets if s.actual_reveal is None]
        if by_chapter:
            unrevealed = [
                s for s in unrevealed
                if s.reveal_chapter is None or s.reveal_chapter >= by_chapter
            ]
        return unrevealed

    def get_overdue(self, current_chapter: int) -> list[SecretEntry]:
        """Get secrets past their planned reveal chapter."""
        return [
            s for s in self.secrets
            if s.reveal_chapter
            and s.reveal_chapter < current_chapter
            and s.actual_reveal is None
        ]

    def mark_revealed(
        self,
        character: str,
        chapter: int,
        revealed_to: list[str] | None = None,
    ) -> bool:
        """Mark a character's secret as revealed."""
        for s in self.secrets:
            if s.character == character and s.actual_reveal is None:
                s.actual_reveal = chapter
                s.revealed_to = revealed_to or []
                return True
        return False

    def add_hint(self, character: str, chapter: int, hint: str) -> None:
        """Record a partial hint about a secret."""
        for s in self.secrets:
            if s.character == character:
                s.partial_hints.append({"chapter": chapter, "hint": hint})
                break


def initialize_secrets(characters: list["Character"]) -> SecretRegistry:
    """Initialize secret registry from character definitions."""
    registry = SecretRegistry()

    for char in characters:
        secret = getattr(char, "secret", "") or ""
        if secret:
            # Parse reveal chapter from secret if format "secret (reveal ch X)"
            reveal_ch = None
            if "(reveal ch" in secret.lower() or "(tiết lộ ch" in secret.lower():
                import re
                match = re.search(r'ch(?:apter)?\s*(\d+)', secret, re.IGNORECASE)
                if match:
                    reveal_ch = int(match.group(1))

            registry.add_secret(
                character=char.name,
                secret=secret,
                reveal_chapter=reveal_ch,
            )

    return registry


def check_secret_reveal(
    llm: "LLMClient",
    chapter_content: str,
    chapter_number: int,
    registry: SecretRegistry,
    model: str | None = None,
) -> dict:
    """Check if any secrets are revealed in this chapter.

    Returns: {
        'reveals': [{character, secret, revealed_to}],
        'hints': [{character, hint}],
        'premature': [{character, secret, planned_chapter}]
    }
    """
    unrevealed = registry.get_unrevealed()
    if not unrevealed:
        return {"reveals": [], "hints": [], "premature": []}

    # Build prompt with secrets to check
    secrets_text = "\n".join(
        f"- {s.character}: {s.secret[:100]}"
        for s in unrevealed[:5]
    )

    result = llm.generate_json(
        system_prompt="Phân tích tiết lộ bí mật. Trả JSON.",
        user_prompt=f"""Chương {chapter_number}:
{chapter_content[:3000]}

Bí mật cần theo dõi:
{secrets_text}

Kiểm tra:
1. Bí mật nào được tiết lộ hoàn toàn?
2. Bí mật nào có hint/gợi ý?
3. Tiết lộ cho ai?

{{"reveals": [{{"character": "tên", "revealed_to": ["tên khác"]}}], "hints": [{{"character": "tên", "hint": "mô tả gợi ý"}}]}}""",
        temperature=0.1,
        max_tokens=400,
        model_tier="cheap",
    )

    reveals = result.get("reveals", [])
    hints = result.get("hints", [])
    premature = []

    # Process reveals
    for r in reveals:
        char = r.get("character", "")
        if not char:
            continue

        # Check if premature
        for s in unrevealed:
            if s.character == char:
                if s.reveal_chapter and chapter_number < s.reveal_chapter:
                    premature.append({
                        "character": char,
                        "secret": s.secret[:50],
                        "planned_chapter": s.reveal_chapter,
                        "actual_chapter": chapter_number,
                    })
                registry.mark_revealed(
                    char, chapter_number,
                    r.get("revealed_to", []),
                )
                break

    # Record hints
    for h in hints:
        char = h.get("character", "")
        hint = h.get("hint", "")
        if char and hint:
            registry.add_hint(char, chapter_number, hint)

    return {
        "reveals": reveals,
        "hints": hints,
        "premature": premature,
    }


def format_secret_warning(check_result: dict, chapter_number: int) -> str:
    """Format secret tracking as warning/info text."""
    lines = []

    if check_result.get("premature"):
        lines.append("## ⚠️ TIẾT LỘ SỚM:")
        for p in check_result["premature"]:
            lines.append(
                f"- {p['character']}: tiết lộ ch{p['actual_chapter']} "
                f"(kế hoạch ch{p['planned_chapter']})"
            )

    if check_result.get("reveals"):
        if not lines:
            lines.append(f"## 🔓 TIẾT LỘ CHƯƠNG {chapter_number}:")
        for r in check_result["reveals"]:
            to_whom = ", ".join(r.get("revealed_to", [])) or "độc giả"
            lines.append(f"- {r['character']} → {to_whom}")

    return "\n".join(lines)


def get_secret_enforcement_prompt(
    registry: SecretRegistry,
    chapter_number: int,
) -> str:
    """Build prompt text to prevent premature reveals.

    Inject into chapter writing prompt.
    """
    unrevealed = registry.get_unrevealed(by_chapter=chapter_number)
    if not unrevealed:
        return ""

    lines = ["## BÍ MẬT CHƯA TIẾT LỘ (KHÔNG được reveal):"]
    for s in unrevealed[:5]:
        deadline = f" (reveal ch{s.reveal_chapter})" if s.reveal_chapter else ""
        lines.append(f"- {s.character}: {s.secret[:60]}...{deadline}")

    lines.append("\nCHỈ được gợi ý mơ hồ, KHÔNG tiết lộ trực tiếp.")
    return "\n".join(lines)


def audit_secrets(
    registry: SecretRegistry,
    final_chapter: int,
) -> dict:
    """Audit secret reveals at story end.

    Returns: {
        'total': int,
        'revealed': int,
        'unrevealed': int,
        'overdue': int,
        'premature': int,
        'details': list
    }
    """
    revealed = [s for s in registry.secrets if s.actual_reveal is not None]
    unrevealed = [s for s in registry.secrets if s.actual_reveal is None]
    overdue = registry.get_overdue(final_chapter + 1)
    premature = [
        s for s in revealed
        if s.reveal_chapter and s.actual_reveal and s.actual_reveal < s.reveal_chapter
    ]

    return {
        "total": len(registry.secrets),
        "revealed": len(revealed),
        "unrevealed": len(unrevealed),
        "overdue": len(overdue),
        "premature": len(premature),
        "details": [
            {
                "character": s.character,
                "secret": s.secret[:50],
                "planned": s.reveal_chapter,
                "actual": s.actual_reveal,
                "hints_count": len(s.partial_hints),
            }
            for s in registry.secrets
        ],
    }
