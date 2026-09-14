"""Batch L, step L0 finding: validate_character_names flagged 18 of 18 real names.

Measured on every saved story (scripts/measure_entity_gaps.py, 2026-09-14): all
18 "Có thể sai tên" warnings were false, and none was an alias or a real
misspelling. Two causes, both in how capitalized words were grouped:

1. Groups ran across punctuation. Words were extracted with the punctuation
   stripped, so `"Ai?" Lâm Phong` became the group "Ai Lâm Phong", and
   `Dạ Sát.\\n\\n"Kẻ` became "Dạ Sát Kẻ" — each "almost" a character name.
2. Sentence-initial words are capitalized by grammar, not because they are names.
   "Thân là rồng…" and "Ông ho…" were edit-distance matched against the given
   names "Chân" and "Không".

These warnings are not cosmetic: they are a scored finding source in the Batch K
repair loop, so each one can trigger a chapter rewrite. Every sentence below is
taken verbatim from a generated story.
"""

from __future__ import annotations

import pytest

from pipeline.layer1_story.consistency_validators import validate_character_names


class _C:
    def __init__(self, name: str):
        self.name = name


WUXIA = [_C(n) for n in ("Lâm Phong", "Thẩm Nguyệt", "Dạ Sát", "Vân Tuyết Dao", "Mạc Ngôn Chân", "Lục Huyền Không")]


@pytest.mark.parametrize(
    "text",
    [
        '"Ai?" Lâm Phong lộn người đứng dậy, thanh kiếm trong tay chĩa ra.',
        'trực tiếp đối đầu với ma khí của Dạ Sát.\n\n"Kẻ tàn sát đồng môn... đều phải... chết!"',
        "nhìn chằm chằm vào Mạc Ngôn Chân và Vân Tuyết Dao. Đó là đòn dốc toàn lực của hắn!",
        "Lục Huyền Không. Sự im lặng kéo dài.",
        '"Xì!" Thẩm Nguyệt quay mặt đi.',
    ],
)
def test_group_does_not_run_across_punctuation(text):
    assert validate_character_names(text, WUXIA) == []


@pytest.mark.parametrize(
    "text",
    [
        # Each sentence carries the same word in lowercase elsewhere, as every
        # real chapter did: a 5–8k-char chapter uses "thân", "ông", "nhân" as
        # ordinary words. A misspelled name ("Minnh") never appears lowercase —
        # that is the distinction, and it needs no dictionary.
        "khí sắc hôm nay có vẻ kém quá nhỉ? Thân là rồng trong loài người, chớ để tổn thương thân thể.",
        "bình rượu trên tay rơi bộp xuống đất, nát vụn. Ông ho húng hắng vài tiếng, ông già mệt mỏi.",
        "Khung cửa sổ bật mở, gió lùa qua khung gỗ mục.",
        "Nhân lúc hỗn loạn, hắn rút lui. Chủ nhân của thanh kiếm đã biến mất.",
    ],
)
def test_sentence_initial_common_word_is_not_a_name(text):
    assert validate_character_names(text, WUXIA) == []


def test_sentence_initial_misspelled_name_is_still_caught():
    """A misspelling never occurs in lowercase, so position alone must not hide it."""
    warnings = validate_character_names("Minnh nói rằng hắn không thể.", [_C("Nguyễn Văn Minh")])
    assert any("Minnh" in w for w in warnings), warnings


class TestRealMisspellingsStillCaught:
    """The fix narrows grouping; it must not blind the detector."""

    def test_misspelled_full_name_mid_sentence(self):
        warnings = validate_character_names("Hắn quay sang nhìn Lâm Phog một lúc lâu.", WUXIA)
        assert any("Lâm Phog" in w for w in warnings), warnings

    def test_misspelled_name_after_punctuation_is_still_its_own_group(self):
        warnings = validate_character_names('"Đi thôi," Thẩm Nguyêt nói.', WUXIA)
        assert any("Thẩm Nguyêt" in w for w in warnings), warnings

    def test_correct_names_produce_nothing(self):
        text = "Lâm Phong gật đầu. Thẩm Nguyệt mỉm cười với Vân Tuyết Dao."
        assert validate_character_names(text, WUXIA) == []
