# -*- coding: utf-8 -*-
"""Phase 3 — Page Compositor tests (comic-real-paneling spec §7).

Runs the REAL compositor (no mocks — it's pure Pillow) on synthesised solid-color
panel PNGs, then asserts structural properties rather than pixel-exact equality:

  * golden / perceptual-hash stability of a fixed layout + fixed inputs,
  * the §2.2 layout library maps each layout name to the right cell count,
  * Vietnamese diacritics survive text wrapping byte-for-byte,
  * a bubble tail points toward the speaker's ``screen_side``,
  * lettering stays high-contrast (white bubble) over a dark panel,
  * the VN comic font renders diacritics as non-blank glyph boxes (font golden),
  * a missing/non-VN font is refused (no silent fallback).

We assert on a downsampled average-hash + ink/paper pixel statistics, which are
robust to harmless font-rendering jitter across platforms while still catching a
layout regression (a moved/missing panel changes the hash decisively).
"""
import os
import tempfile

import pytest
from PIL import Image, ImageDraw, ImageFont

from services.media.shot_list import Page, Panel, Bubble, Caption, ShotList
from services.media.page_compositor import (
    compose_page,
    compose_chapter,
    layout_cells,
    wrap_vietnamese,
    PageGeometry,
    FontUnavailableError,
    LAYOUT_LIBRARY,
    _resolve_font_path,
    _speaker_side,
    _tail_polygon,
)

# Vietnamese battery (matches the Phase 2 test brief).
VI_CAPTION = "Làng Đông đã không còn."
VI_LINE_OLD = "Cậu... cậu là người sống sót cuối cùng sao?"
VI_LINE_KIEN = "Không. Ta là kẻ sẽ báo thù — ữ ạ ọ ậ ỹ ề."

FONT_PATH = _resolve_font_path(None)  # vendored Be Vietnam Pro


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

def _solid_panel(tmpdir, name, color, size=(800, 1000)):
    p = os.path.join(tmpdir, name)
    Image.new("RGB", size, color).save(p)
    return p


def _three_tier_page():
    return Page(
        page=1,
        layout="THREE_TIER",
        panels=[
            Panel(
                n=1, shot="EWS", subject="Kiên",
                screen_side={"Kiên": "center"},
                captions=[Caption(type="narration", text=VI_CAPTION)],
            ),
            Panel(
                n=2, shot="MS", subject="Bà lão",
                screen_side={"Bà lão": "left", "Kiên": "right"},
                bubbles=[Bubble(speaker="Bà lão", type="speech", text=VI_LINE_OLD)],
            ),
            Panel(
                n=3, shot="CU", subject="Kiên",
                screen_side={"Kiên": "right"},
                bubbles=[Bubble(speaker="Kiên", type="speech", text=VI_LINE_KIEN)],
            ),
        ],
    )


def _avg_hash(img, n=16):
    """64*... bit average hash of a downsampled grayscale image."""
    small = img.convert("L").resize((n, n), Image.LANCZOS)
    px = list(small.getdata())
    avg = sum(px) / len(px)
    return tuple(1 if p >= avg else 0 for p in px)


def _hamming(a, b):
    return sum(x != y for x, y in zip(a, b))


# --------------------------------------------------------------------------- #
# Layout library coverage (§2.2)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "name,count",
    [
        ("SPLASH", 1),
        ("TWO_TIER", 2),
        ("THREE_TIER", 3),
        ("GRID_2x2", 4),
        ("BIG_PLUS_TWO", 3),
        ("SIX_GRID", 6),
    ],
)
def test_layout_library_cell_counts(name, count):
    geom = PageGeometry()
    page = Page(page=1, layout=name, panels=[Panel(n=i) for i in range(count)])
    cells = layout_cells(page, geom, "shot_list")
    assert len(cells) == count
    # Every cell is inside the safe margin and non-degenerate.
    l0, t0, r0, b0 = geom.content_box
    for (left, t, r, b) in cells:
        assert left >= l0 - 1 and t >= t0 - 1 and r <= r0 + 1 and b <= b0 + 1
        assert r > left and b > t


def test_layout_library_covers_spec():
    # All six spec §2.2 layouts present.
    assert set(LAYOUT_LIBRARY) == {
        "SPLASH", "TWO_TIER", "THREE_TIER", "GRID_2x2", "BIG_PLUS_TWO", "SIX_GRID",
    }


def test_unknown_layout_falls_back_by_count():
    geom = PageGeometry()
    page = Page(page=1, layout="NONSENSE", panels=[Panel(n=i) for i in range(4)])
    # 4 panels -> GRID_2x2 (4 cells)
    assert len(layout_cells(page, geom, "shot_list")) == 4


def test_cells_are_reading_order_z_ltr():
    # GRID_2x2 cells must read top-left, top-right, bottom-left, bottom-right.
    geom = PageGeometry()
    page = Page(page=1, layout="GRID_2x2", panels=[Panel(n=i) for i in range(4)])
    c = layout_cells(page, geom, "shot_list")
    # cell0 above cell2; cell0 left of cell1
    assert c[0][1] < c[2][1]      # top row above bottom row
    assert c[0][0] < c[1][0]      # left col before right col (LTR, not manga RTL)
    assert c[2][0] < c[3][0]


# --------------------------------------------------------------------------- #
# Vietnamese text wrap (diacritics preserved)
# --------------------------------------------------------------------------- #

def test_wrap_preserves_vietnamese_diacritics():
    lines = wrap_vietnamese(VI_LINE_KIEN, 20)
    assert lines, "wrap produced no lines"
    joined = " ".join(lines)
    # Every diacritic char from the source survives the round-trip.
    for ch in "ữạọậỹềảẻ":
        if ch in VI_LINE_KIEN:
            assert ch in joined, f"diacritic {ch!r} lost in wrap"
    # The re-joined words equal the source words (only spaces re-flow).
    assert joined.split() == VI_LINE_KIEN.split()


def test_wrap_respects_char_cap():
    for line in wrap_vietnamese(VI_LINE_OLD, 18):
        assert len(line) <= 18


def test_wrap_hard_cuts_overlong_token():
    out = wrap_vietnamese("X" * 50, 18)
    assert all(len(line) <= 18 for line in out)
    assert "".join(out) == "X" * 50


# --------------------------------------------------------------------------- #
# Font golden — VN diacritics render to non-blank glyph boxes (§4 font)
# --------------------------------------------------------------------------- #

def test_vn_font_renders_diacritics_nonblank():
    font = ImageFont.truetype(FONT_PATH, 64)
    img = Image.new("L", (900, 160), 0)
    d = ImageDraw.Draw(img)
    d.text((10, 20), "ề ữ ạ ọ ậ ỹ Đông", font=font, fill=255)
    bbox = img.getbbox()
    assert bbox is not None, "diacritic string rendered completely blank"
    ink = sum(1 for p in img.getdata() if p > 0)
    assert ink > 500, "too few inked pixels — diacritics likely missing glyphs"


def test_missing_font_is_refused_no_silent_fallback():
    with pytest.raises(FontUnavailableError):
        _resolve_font_path("does/not/exist/NoSuchFont.ttf")


# --------------------------------------------------------------------------- #
# Bubble tail direction (§4 — tail points at speaker's screen_side)
# --------------------------------------------------------------------------- #

def test_tail_polygon_points_left_for_left_speaker():
    bbox = (700, 100, 1100, 300)  # centered-ish bubble
    left_tip = _tail_polygon(bbox, "left")[2]
    right_tip = _tail_polygon(bbox, "right")[2]
    center_tip = _tail_polygon(bbox, "center")[2]
    cx = (bbox[0] + bbox[2]) / 2
    assert left_tip[0] < cx, "left-speaker tail must point left of bubble center"
    assert right_tip[0] > cx, "right-speaker tail must point right of bubble center"
    assert abs(center_tip[0] - cx) <= 2, "center tail should drop straight down"
    # Tails drop below the bubble toward the speaker (panel art is below the bubble).
    assert left_tip[1] > bbox[3] - 1
    assert right_tip[1] > bbox[3] - 1


def test_speaker_side_resolution_prefers_panel_then_override():
    panel = Panel(n=1, subject="Kiên", screen_side={"Bà lão": "left"})
    b = Bubble(speaker="Bà lão", type="speech", text="x")
    assert _speaker_side(panel, b, None) == "left"
    # falls back to chapter-wide override when panel has no entry
    b2 = Bubble(speaker="Mai", type="speech", text="y")
    assert _speaker_side(panel, b2, {"Mai": "right"}) == "right"
    # defaults to center when unknown
    assert _speaker_side(panel, Bubble(speaker="Ai", text="z"), None) == "center"


# --------------------------------------------------------------------------- #
# Text contrast on a DARK panel (§4 — white bubble + halo so text reads)
# --------------------------------------------------------------------------- #

def test_bubble_is_high_contrast_over_dark_panel():
    with tempfile.TemporaryDirectory() as d:
        # near-black panel everywhere
        dark = _solid_panel(d, "dark.png", (8, 8, 10))
        page = Page(
            page=1, layout="SPLASH",
            panels=[Panel(
                n=1, subject="Kiên", screen_side={"Kiên": "center"},
                bubbles=[Bubble(speaker="Kiên", type="speech", text=VI_LINE_KIEN)],
            )],
        )
        out = os.path.join(d, "dark_page.png")
        compose_page(page, [dark], out, font_path=FONT_PATH)
        im = Image.open(out).convert("RGB")
        # The bubble introduces a substantial block of near-white pixels that a
        # bare dark panel would never have.
        white = sum(1 for (r, g, b) in im.getdata() if r > 230 and g > 230 and b > 230)
        assert white > 3000, "no high-contrast white bubble region found over dark art"


# --------------------------------------------------------------------------- #
# Golden / perceptual-hash stability of a fixed layout + fixed inputs (§7)
# --------------------------------------------------------------------------- #

def test_compose_page_is_deterministic_perceptual_hash():
    with tempfile.TemporaryDirectory() as d:
        panels = [
            _solid_panel(d, "p0.png", (180, 60, 60)),
            _solid_panel(d, "p1.png", (60, 120, 180)),
            _solid_panel(d, "p2.png", (40, 40, 48)),
        ]
        page = _three_tier_page()
        out_a = os.path.join(d, "a.png")
        out_b = os.path.join(d, "b.png")
        compose_page(page, panels, out_a, font_path=FONT_PATH)
        compose_page(page, panels, out_b, font_path=FONT_PATH)

        ia, ib = Image.open(out_a), Image.open(out_b)
        # Fixed canvas geometry (§2.1).
        assert ia.size == (1600, 2263)
        # Bit-identical run-to-run (pure function, no randomness).
        assert _avg_hash(ia) == _avg_hash(ib)

        # A layout change (SPLASH vs THREE_TIER) must perceptibly differ — proves
        # the hash actually discriminates structure, not a constant.
        splash = Page(page=1, layout="SPLASH", panels=[page.panels[0]])
        out_c = os.path.join(d, "c.png")
        compose_page(splash, [panels[0]], out_c, font_path=FONT_PATH)
        assert _hamming(_avg_hash(ia), _avg_hash(Image.open(out_c))) > 8


def test_compose_chapter_returns_pages_in_reading_order():
    with tempfile.TemporaryDirectory() as d:
        # 2 pages: page1 THREE_TIER (3 panels), page2 SPLASH (1 panel) = 4 panels.
        panels = [_solid_panel(d, f"p{i}.png", (50 + i * 40, 80, 160)) for i in range(4)]
        sl = ShotList(
            chapter_number=3,
            pages=[
                _three_tier_page(),
                Page(page=2, layout="SPLASH", panels=[Panel(n=4, shot="EWS", subject="Kiên")]),
            ],
        )
        out = compose_chapter(sl, panels, d, chapter_number=3, font_path=FONT_PATH)
        assert len(out) == 2
        assert os.path.basename(out[0]) == "ch03_page01.png"
        assert os.path.basename(out[1]) == "ch03_page02.png"
        for p in out:
            assert Image.open(p).size == (1600, 2263)


def test_compose_chapter_accepts_persisted_dict_shotlist():
    # The handler persists ch.shot_list as a plain dict (model_dump); the chapter
    # composer must accept that shape too.
    with tempfile.TemporaryDirectory() as d:
        panels = [_solid_panel(d, f"p{i}.png", (90, 90, 90)) for i in range(3)]
        sl_dict = ShotList(chapter_number=1, pages=[_three_tier_page()]).model_dump()
        out = compose_chapter(sl_dict, panels, d, chapter_number=1, font_path=FONT_PATH)
        assert len(out) == 1
        assert Image.open(out[0]).size == (1600, 2263)
