"""The 10 L2 agent prompts ran without Vietnamese diacritics.

`pipeline/agents/agent_prompts._get_prompt` prefers the shipped
`data/prompts/agent_prompts.yaml` over the built-in `_DEFAULTS`. That YAML was
created accent-stripped when the prompts were externalized (59ebffa), was only
partly restored by a later "Vietnamese diacritics" fix (33348e4), and has since
held 287 accented characters against the defaults' 1,482. Ignoring accents, its
text is identical to the defaults — so every review and debate agent received
"Ban la Chuyen Gia Nhan Vat ... Tra ve JSON theo dinh dang sau" instead of the
Vietnamese the defaults were written in.

Two guards: the shipped YAML must not drift from the defaults, and no shipped
agent prompt may contain Vietnamese words written without their diacritics.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from pipeline.agents import agent_prompts as ap

_YAML = Path(ap.__file__).resolve().parents[2] / "data" / "prompts" / "agent_prompts.yaml"

# Vietnamese words that are never correct without a diacritic, and are not
# English words. ("theo", "trong", "gia", "quan"... are correct unaccented and
# are deliberately absent.)
_UNACCENTED = {
    "khong", "duoc", "nguoi", "chuong", "truyen", "nhan", "vat", "cua", "nhung",
    "mot", "cac", "nhieu", "phai", "viet", "tieng", "doan", "noi", "boi", "canh",
    "kien", "voi", "hoac", "neu", "ve", "dieu", "giong", "thoai", "nguyen",
    "khac", "biet", "chinh", "xac", "nhat", "bat", "buoc", "doi", "dua",
    "nhien", "phan", "tich", "loi", "thuan", "gioi", "diem", "thoi", "thuc",
    "dau", "trao", "yeu", "cau", "nhiem", "vu", "kiem", "sach", "hop",
}  # not "danh": "danh sách" is correct unaccented
_WORD = re.compile(r"[A-Za-zÀ-ỹĐđ]+")


def _shipped_yaml() -> dict:
    data = yaml.safe_load(_YAML.read_text(encoding="utf-8")) or {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _unaccented_words(text: str) -> list[str]:
    # Strip placeholders and JSON keys: `{own_score}`, `"stance"` are identifiers.
    text = re.sub(r"\{[^{}]*\}", " ", text)
    return sorted({w.lower() for w in _WORD.findall(text)} & _UNACCENTED)


def test_shipped_yaml_covers_exactly_the_defaults():
    assert set(_shipped_yaml()) == set(ap._DEFAULTS)


@pytest.mark.parametrize("key", sorted(ap._DEFAULTS))
def test_shipped_yaml_matches_builtin_default(key):
    """The YAML wins at runtime, so it must say what the defaults say."""
    shipped = " ".join(str(_shipped_yaml()[key]).split())
    default = " ".join(ap._DEFAULTS[key].split())
    assert shipped == default


@pytest.mark.parametrize("key", sorted(ap._DEFAULTS))
def test_runtime_prompt_keeps_its_diacritics(key):
    """What the agent actually receives — through the same lookup it uses."""
    prompt = ap._get_prompt(key)
    assert _unaccented_words(prompt) == [], prompt[:300]


def test_the_word_guard_itself_catches_stripped_text():
    assert _unaccented_words("Ban la Chuyen Gia Nhan Vat, Tra ve JSON khong co markdown") != []
    assert _unaccented_words("Bạn là Chuyên Gia Nhân Vật, trả về JSON theo định dạng {own_score}") == []
