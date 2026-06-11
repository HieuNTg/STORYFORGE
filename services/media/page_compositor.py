"""Phase 3 — Page Compositor (comic-real-paneling spec §4 PHASE 3).

Turns the clean, dialogue-free panel PNGs produced by image generation plus the
Phase 2 shot-list (:mod:`services.media.shot_list`) into finished COMIC PAGE PNGs:

  * a page canvas per spec §2.1 (1600×2263 px, 60 px safe margin, 24–32 px gutter),
  * panels placed into the grid for the page's ``layout`` (§2.2 layout library),
    cropped/fit to each cell with a black border + gutter between cells,
  * vector speech bubbles (drawn with Pillow — ellipse + polygon tail) whose tail
    points toward the speaker's ``screen_side`` (§5 bubble shapes),
  * Vietnamese lettering wrapped at ≤18–22 chars/line with a black outline + white
    halo so it reads on dark panels,
  * caption boxes (rectangle, no tail) for narration / scene-transitions.

Pure Python — Pillow only, no native/SVG dependency. Reading order is **Z / LTR**
(NOT manga RTL): panel 1 = top-left, bubbles flow top-left → bottom-right.

Public API:
  * :func:`compose_page` — one :class:`~services.media.shot_list.Page` → one PNG.
  * :func:`compose_chapter` — a whole shot-list → page PNGs in reading order.

Both degrade-by-raising; callers (the handler) wrap in try/except and fall back to
loose panels. The compositor itself never silently substitutes a non-VN font: if
the configured font cannot be loaded it raises :class:`FontUnavailableError`.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional, Sequence

from PIL import Image, ImageDraw, ImageFont

from services.media.shot_list import Bubble, Caption, Page, Panel

logger = logging.getLogger(__name__)

__all__ = [
    "FontUnavailableError",
    "PageGeometry",
    "compose_page",
    "compose_chapter",
    "layout_cells",
    "wrap_vietnamese",
    "LAYOUT_LIBRARY",
]


# ---------------------------------------------------------------------------
# Geometry / style constants (spec §2.1, §2.4, §4 style guide)
# ---------------------------------------------------------------------------

DEFAULT_CANVAS = (1600, 2263)          # ISO 1:√2 (§2.1)
SAFE_MARGIN = 60                       # px (§2.1)
GUTTER = 28                            # px, within the 24–32 band (§2.1)
PANEL_BORDER = 6                       # px black panel frame
PAGE_BG = (250, 248, 244)             # warm paper white behind gutters

# Lettering (§2.4 / §4): cap-height ≥ 28 px @1600. Be Vietnam Pro's cap-height is
# ~0.7 of the em, so an em of 44 px yields ~31 px caps — safely above the floor.
FONT_SIZE_MAX = 46
FONT_SIZE_MIN = 30                     # auto-shrink floor before the bubble grows
CAPTION_FONT_SIZE = 34
LINE_SPACING = 6
BUBBLE_PAD_X = 26
BUBBLE_PAD_Y = 20
BUBBLE_OUTLINE = 4                     # black outline 3–4 px (§4)
TEXT_HALO = 3                          # white halo radius so text reads on dark art
MAX_BUBBLES_PER_FRAME = 2              # §4
MAX_CHARS_PER_LINE = 20                # ≤18–22 VN chars/line (§4 step 3)

# Bubble fills/strokes
INK = (20, 20, 20)
PAPER = (255, 255, 255)
CAPTION_FILL = (255, 243, 198)         # pale cream — classic narration-box color
CAPTION_FONT_MIN = 26                  # captions auto-shrink down to this
WHISPER_INK = (96, 96, 96)             # whispers letter lighter
THOUGHT_PUFF = 7                       # cloud lobes for thought bubbles
SHOUT_SPIKES = 14                      # spikes for shout bubbles (10–16 reads best)
SUPERSAMPLE = 2                        # lettering overlay drawn at 2× then LANCZOS-downscaled


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class FontUnavailableError(RuntimeError):
    """Raised when the Vietnamese comic font cannot be loaded.

    We deliberately do NOT fall back to a non-VN font: silently dropping diacritics
    would defeat the whole point (Vietnamese lettering). Callers degrade to loose
    panels instead.
    """


# ---------------------------------------------------------------------------
# Page geometry
# ---------------------------------------------------------------------------

@dataclass
class PageGeometry:
    """Resolved page canvas + spacing for one composition run."""
    width: int = DEFAULT_CANVAS[0]
    height: int = DEFAULT_CANVAS[1]
    margin: int = SAFE_MARGIN
    gutter: int = GUTTER
    border: int = PANEL_BORDER

    @property
    def content_box(self) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) inside the safe margin."""
        return (self.margin, self.margin, self.width - self.margin, self.height - self.margin)

    @classmethod
    def from_canvas_spec(cls, spec: Optional[str]) -> "PageGeometry":
        """Parse ``"1600x2263"`` → geometry; fall back to default on garbage."""
        if not spec:
            return cls()
        try:
            w_s, h_s = spec.lower().replace(" ", "").split("x", 1)
            w, h = int(w_s), int(h_s)
            if w < 200 or h < 200:
                raise ValueError("canvas too small")
            return cls(width=w, height=h)
        except Exception:
            logger.warning("Bad comic_page_canvas %r; using default %sx%s", spec, *DEFAULT_CANVAS)
            return cls()


# A grid cell, in absolute page pixels: (left, top, right, bottom).
Cell = tuple[int, int, int, int]


# ---------------------------------------------------------------------------
# §2.2 Layout library — each entry maps a panel COUNT request to grid cells.
# Reading order is Z/LTR: cells are emitted top→bottom, left→right.
# ---------------------------------------------------------------------------

def _rows(box: Cell, gutter: int, weights: Sequence[float]) -> list[Cell]:
    """Split ``box`` vertically into rows sized by ``weights`` (full-width)."""
    left, t, r, b = box
    inner_h = (b - t) - gutter * (len(weights) - 1)
    total = float(sum(weights)) or 1.0
    cells: list[Cell] = []
    y = t
    for w in weights:
        h = int(round(inner_h * (w / total)))
        cells.append((left, y, r, y + h))
        y += h + gutter
    return cells


def _split_cols(cell: Cell, gutter: int, n: int) -> list[Cell]:
    """Split one row ``cell`` horizontally into ``n`` equal columns (LTR)."""
    left, t, r, b = cell
    inner_w = (r - left) - gutter * (n - 1)
    cw = inner_w // n
    out: list[Cell] = []
    x = left
    for i in range(n):
        x2 = r if i == n - 1 else x + cw
        out.append((x, t, x2, b))
        x = x2 + gutter
    return out


def _layout_splash(box: Cell, g: int) -> list[Cell]:
    return [box]


def _layout_two_tier(box: Cell, g: int) -> list[Cell]:
    return _rows(box, g, [1, 1])


def _layout_three_tier(box: Cell, g: int) -> list[Cell]:
    return _rows(box, g, [1, 1, 1])


def _layout_grid_2x2(box: Cell, g: int) -> list[Cell]:
    top, bot = _rows(box, g, [1, 1])
    return _split_cols(top, g, 2) + _split_cols(bot, g, 2)


def _layout_big_plus_two(box: Cell, g: int) -> list[Cell]:
    # One dominant top panel (≈60% height) + two small side-by-side below.
    big, small_row = _rows(box, g, [1.6, 1])
    return [big] + _split_cols(small_row, g, 2)


def _layout_six_grid(box: Cell, g: int) -> list[Cell]:
    cells: list[Cell] = []
    for row in _rows(box, g, [1, 1, 1]):
        cells.extend(_split_cols(row, g, 2))
    return cells


# name -> (builder, declared panel count)
LAYOUT_LIBRARY: dict[str, tuple] = {
    "SPLASH": (_layout_splash, 1),
    "TWO_TIER": (_layout_two_tier, 2),
    "THREE_TIER": (_layout_three_tier, 3),
    "GRID_2x2": (_layout_grid_2x2, 4),
    "BIG_PLUS_TWO": (_layout_big_plus_two, 3),
    "SIX_GRID": (_layout_six_grid, 6),
}

# Fallback chooser by panel count when layout is unknown / mode == "auto".
_AUTO_BY_COUNT: dict[int, str] = {
    1: "SPLASH",
    2: "TWO_TIER",
    3: "THREE_TIER",
    4: "GRID_2x2",
    5: "BIG_PLUS_TWO",  # 3 cells; extra panels overflow into the last cell
    6: "SIX_GRID",
}


def _resolve_layout_name(page: Page, mode: str) -> str:
    n = max(1, len(page.panels))
    if mode == "auto":
        return _AUTO_BY_COUNT.get(min(n, 6), "SIX_GRID")
    name = (page.layout or "").upper()
    if name in LAYOUT_LIBRARY:
        return name
    logger.debug("Unknown layout %r on page %s; deriving from %d panels", page.layout, page.page, n)
    return _AUTO_BY_COUNT.get(min(n, 6), "SIX_GRID")


def layout_cells(page: Page, geom: PageGeometry, mode: str = "shot_list") -> list[Cell]:
    """Return grid cells (absolute page px) for ``page`` in Z/LTR reading order.

    The cell count matches the layout's declared count. If the page carries MORE
    panels than the layout has cells, the surplus panels are dropped from this page
    (the shot-list extractor is responsible for not over-filling a layout); if it
    carries FEWER, the trailing cells stay empty.
    """
    name = _resolve_layout_name(page, mode)
    builder, _count = LAYOUT_LIBRARY[name]
    return builder(geom.content_box, geom.gutter)


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

def _project_root() -> str:
    # services/media/page_compositor.py -> project root is two levels up.
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resolve_font_path(font_path: Optional[str]) -> str:
    """Resolve the configured font to an existing .ttf or raise.

    A relative path is resolved against the project root (so the vendored
    ``assets/fonts/BeVietnamPro-Bold.ttf`` default works regardless of cwd).
    """
    if not font_path:
        font_path = "assets/fonts/BeVietnamPro-Bold.ttf"
    candidate = font_path
    if not os.path.isabs(candidate):
        candidate = os.path.join(_project_root(), font_path)
    if not os.path.exists(candidate):
        raise FontUnavailableError(
            f"Comic font not found at {candidate!r}. Vendor a Vietnamese-capable "
            f"comic font (Be Vietnam Pro) into assets/fonts/ or set comic_font. "
            f"Refusing to fall back to a non-VN font."
        )
    return candidate


@dataclass
class _FontCache:
    path: str
    _sizes: dict[int, ImageFont.FreeTypeFont] = field(default_factory=dict)

    def at(self, size: int) -> ImageFont.FreeTypeFont:
        f = self._sizes.get(size)
        if f is None:
            try:
                f = ImageFont.truetype(self.path, size)
            except Exception as e:  # pragma: no cover - corrupt font file
                raise FontUnavailableError(f"Cannot load font {self.path!r}: {e}") from e
            self._sizes[size] = f
        return f


# ---------------------------------------------------------------------------
# Text wrapping (Vietnamese; word-aware, char-capped)
# ---------------------------------------------------------------------------

def wrap_vietnamese(text: str, max_chars: int = MAX_CHARS_PER_LINE) -> list[str]:
    """Greedy word wrap at ≤``max_chars`` Vietnamese characters per line.

    Vietnamese is space-delimited (Latin script with diacritics), so wrapping on
    word boundaries is correct. A single word longer than ``max_chars`` is hard-cut
    rather than overflowing the bubble.
    """
    text = (text or "").strip()
    if not text:
        return []
    lines: list[str] = []
    cur = ""
    for word in text.split():
        # Hard-cut an over-long single token.
        while len(word) > max_chars:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:max_chars])
            word = word[max_chars:]
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= max_chars:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _measure_lines(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[str],
    font: ImageFont.FreeTypeFont,
    spacing: int,
) -> tuple[int, int]:
    """Return (text_width, text_height) for a block of lines."""
    w = 0
    h = 0
    for i, ln in enumerate(lines):
        box = draw.textbbox((0, 0), ln or " ", font=font)
        w = max(w, box[2] - box[0])
        lh = box[3] - box[1]
        h += lh + (spacing if i < len(lines) - 1 else 0)
    return w, h


def _shape_lines(text: str, max_chars: int) -> list[str]:
    """Wrap like :func:`wrap_vietnamese`, then shape the block like a letterer.

    Professional balloon text is oval/diamond shaped — the middle line is the
    widest so the block fills an ellipse instead of leaving empty crescents at
    the top and bottom. Re-wraps with a convex per-line char budget when there
    are ≥3 lines, then fixes a widow (a lone word on the last line) by pulling
    the previous line's last word down to join it.
    """
    import math

    flat = wrap_vietnamese(text, max_chars)
    n = len(flat)
    if n >= 3:
        words = text.split()
        # Only shape when every word fits even the tightest (first/last) line
        # budget — over-long tokens keep the plain greedy wrap + hard cuts.
        if words and all(len(w) <= int(max_chars * 0.70) for w in words):
            caps = [
                max(8, int(max_chars * (0.70 + 0.30 * math.sin(math.pi * (i + 0.5) / n))))
                for i in range(n)
            ]
            shaped: list[str] = []
            cur = ""
            li = 0
            for word in words:
                cap = caps[li] if li < n else max_chars
                if not cur:
                    cur = word
                elif len(cur) + 1 + len(word) <= cap:
                    cur += " " + word
                else:
                    shaped.append(cur)
                    li += 1
                    cur = word
            if cur:
                shaped.append(cur)
            if n <= len(shaped) <= n + 1:
                flat = shaped
    # Widow fix: never leave a single word alone on the last line.
    if len(flat) >= 2 and " " not in flat[-1]:
        prev_words = flat[-2].split()
        if len(prev_words) >= 2:
            moved = prev_words[-1] + " " + flat[-1]
            if len(moved) <= max_chars:
                flat[-2] = " ".join(prev_words[:-1])
                flat[-1] = moved
    return flat


# ---------------------------------------------------------------------------
# Panel placement
# ---------------------------------------------------------------------------

def _fit_cover(img: Image.Image, cell: Cell) -> Image.Image:
    """Resize+center-crop ``img`` to exactly fill ``cell`` (object-fit: cover)."""
    cw = max(1, cell[2] - cell[0])
    ch = max(1, cell[3] - cell[1])
    iw, ih = img.size
    if iw == 0 or ih == 0:
        return Image.new("RGB", (cw, ch), (40, 40, 48))
    scale = max(cw / iw, ch / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    resized = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - cw) // 2
    top = (nh - ch) // 2
    return resized.crop((left, top, left + cw, top + ch))


def _place_panel(canvas: Image.Image, draw: ImageDraw.ImageDraw, panel_path: str, cell: Cell, border: int) -> None:
    """Composite one panel image into ``cell`` with a black border."""
    try:
        with Image.open(panel_path) as im:
            im = im.convert("RGB")
            fitted = _fit_cover(im, cell)
    except Exception as e:
        logger.warning("Panel image unreadable (%s): %s — drawing placeholder", panel_path, e)
        fitted = Image.new("RGB", (cell[2] - cell[0], cell[3] - cell[1]), (40, 40, 48))
    canvas.paste(fitted, (cell[0], cell[1]))
    draw.rectangle(cell, outline=INK, width=border)


# ---------------------------------------------------------------------------
# Speaker side resolution
# ---------------------------------------------------------------------------

def _speaker_side(panel: Panel, bubble: Bubble, char_screen_sides: Optional[dict]) -> str:
    """Resolve which side of the frame the speaker is on: 'left'|'right'|'center'.

    Prefers the panel's own ``screen_side`` map, then any chapter-wide override,
    defaulting to 'center'. Normalised to one of the three known values.
    """
    name = bubble.speaker or panel.subject or ""
    side = ""
    if name and isinstance(panel.screen_side, dict):
        side = str(panel.screen_side.get(name, "")).lower()
    if not side and char_screen_sides and name in char_screen_sides:
        side = str(char_screen_sides[name]).lower()
    if side not in ("left", "right", "center"):
        side = "center"
    return side


# ---------------------------------------------------------------------------
# Bubble + caption rendering
# ---------------------------------------------------------------------------

def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[str],
    font: ImageFont.FreeTypeFont,
    cx: int,
    top: int,
    spacing: int,
    fill=INK,
    halo: int = 0,
) -> None:
    """Draw center-aligned lines starting at vertical ``top``; optional white halo."""
    y = top
    for ln in lines:
        box = draw.textbbox((0, 0), ln or " ", font=font)
        lw = box[2] - box[0]
        x = cx - lw // 2 - box[0]
        if halo:
            # Cheap halo: stroke_width on the same glyphs in white.
            draw.text((x, y - box[1]), ln, font=font, fill=PAPER, stroke_width=halo, stroke_fill=PAPER)
        draw.text((x, y - box[1]), ln, font=font, fill=fill)
        y += (box[3] - box[1]) + spacing


def _tail_polygon(bbox: tuple[int, int, int, int], side: str) -> list[tuple[int, int]]:
    """Triangle tail from the bubble edge toward ``side`` (the speaker)."""
    left, t, r, b = bbox
    cx = (left + r) // 2
    by = b  # tails drop from the bottom of the bubble toward the speaker below
    base = max(18, (r - left) // 8)
    drop = max(28, (b - t) // 3)
    if side == "left":
        ax = left + (r - left) // 4
        tip = (max(left - drop // 2, left - 60), by + drop)
    elif side == "right":
        ax = r - (r - left) // 4
        tip = (min(r + drop // 2, r + 60), by + drop)
    else:  # center
        ax = cx
        tip = (cx, by + drop)
    return [(ax - base // 2, by - 2), (ax + base // 2, by - 2), tip]


def _bubble_outline_shape(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    btype: str,
    ow: int = BUBBLE_OUTLINE,
) -> None:
    """Stroke the bubble body according to ``type`` (§5 shapes)."""
    if btype == "narration":
        draw.rectangle(bbox, fill=PAPER, outline=INK, width=ow)
        return
    if btype == "whisper":
        # Dashed ellipse outline.
        draw.ellipse(bbox, fill=PAPER)
        _dashed_ellipse(draw, bbox, INK, ow)
        return
    if btype == "shout":
        _spiky(draw, bbox, ow)
        return
    if btype == "thought":
        _cloud(draw, bbox, ow)
        return
    # speech / offscreen / default: smooth oval.
    draw.ellipse(bbox, fill=PAPER, outline=INK, width=ow)


def _dashed_ellipse(draw, bbox, color, width) -> None:
    import math
    left, t, r, b = bbox
    cx, cy = (left + r) / 2, (t + b) / 2
    rx, ry = (r - left) / 2, (b - t) / 2
    # Dense, even dash rhythm (dash ≈ gap) reads as "whisper" at page size;
    # the old sparse 8-dash ring was barely distinguishable from speech.
    seg = 6
    n = 120
    for i in range(n):
        if (i // seg) % 2:
            continue
        a0 = 2 * math.pi * i / n
        a1 = 2 * math.pi * (i + 1) / n
        p0 = (cx + rx * math.cos(a0), cy + ry * math.sin(a0))
        p1 = (cx + rx * math.cos(a1), cy + ry * math.sin(a1))
        draw.line([p0, p1], fill=color, width=width)


def _spiky(draw, bbox, ow: int = BUBBLE_OUTLINE) -> None:
    import math
    left, t, r, b = bbox
    cx, cy = (left + r) / 2, (t + b) / 2
    rx, ry = (r - left) / 2, (b - t) / 2
    pts = []
    n = SHOUT_SPIKES * 2
    for i in range(n):
        ang = 2 * math.pi * i / n
        if i % 2 == 0:
            # Outer spike tip with deterministic ±8% length jitter — uniform
            # spikes look mechanical, irregular ones read as a real scream.
            rad = 1.0 + 0.08 * math.sin(i * 2.39996)
        else:
            rad = 0.74
        pts.append((cx + rx * rad * math.cos(ang), cy + ry * rad * math.sin(ang)))
    draw.polygon(pts, fill=PAPER, outline=INK)
    # thicken outline
    draw.line(pts + [pts[0]], fill=INK, width=ow, joint="curve")


def _cloud(draw, bbox, ow: int = BUBBLE_OUTLINE) -> None:
    import math
    left, t, r, b = bbox
    cx, cy = (left + r) / 2, (t + b) / 2
    rx, ry = (r - left) / 2, (b - t) / 2
    # Base body
    draw.ellipse(bbox, fill=PAPER)
    lobe = max(14, int(min(rx, ry) * 0.42))
    n = THOUGHT_PUFF + 4
    for i in range(n):
        ang = 2 * math.pi * i / n
        px = cx + (rx - lobe * 0.4) * math.cos(ang)
        py = cy + (ry - lobe * 0.4) * math.sin(ang)
        draw.ellipse((px - lobe, py - lobe, px + lobe, py + lobe), fill=PAPER, outline=INK, width=ow)
    # redraw center to clean interior strokes
    draw.ellipse((left + lobe, t + lobe, r - lobe, b - lobe), fill=PAPER)


def _draw_thought_dots(draw, bbox, side, ow: int = BUBBLE_OUTLINE, scale: int = 1) -> None:
    """Trailing puffs from a thought bubble toward the speaker."""
    left, t, r, b = bbox
    cx = (left + r) // 2
    if side == "left":
        x = left + (r - left) // 4
    elif side == "right":
        x = r - (r - left) // 4
    else:
        x = cx
    y = b
    rad = 14 * scale
    for _ in range(3):
        draw.ellipse((x - rad, y - rad, x + rad, y + rad), fill=PAPER, outline=INK, width=ow)
        y += rad + 8 * scale
        rad = max(5 * scale, rad - 4 * scale)


def _tail_curves(
    base1: tuple[int, int],
    base2: tuple[int, int],
    tip: tuple[int, int],
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Two quadratic-Bézier sides turning the straight triangle tail into a
    tapered, slightly bowed wedge (straight wedges read as clip-art)."""
    def quad(p0, p1, p2, steps=10):
        pts = []
        for s in range(steps + 1):
            u = s / steps
            pts.append((
                (1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u ** 2 * p2[0],
                (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u ** 2 * p2[1],
            ))
        return pts

    mx = (base1[0] + base2[0]) / 2
    # Control points bow each side toward the tail's centerline.
    c1 = ((base1[0] + tip[0]) / 2 + (mx - base1[0]) * 0.45, (base1[1] + tip[1]) / 2)
    c2 = ((base2[0] + tip[0]) / 2 + (mx - base2[0]) * 0.45, (base2[1] + tip[1]) / 2)
    return quad(base1, c1, tip), quad(tip, c2, base2)


def _render_bubble(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    bubble: Bubble,
    cell: Cell,
    slot: int,
    n_slots: int,
    side: str,
    fonts: _FontCache,
    scale: int = 1,
    top_floor: int = 0,
) -> None:
    """Render one speech/thought/etc. bubble into ``cell``.

    Placement: bubbles occupy the top ~⅓ of the frame (so they don't cover faces),
    laid out left→right across ``n_slots`` (Z reading order), the later bubble
    staggered slightly lower (reading order is top-left → bottom-right). Text
    auto-shrinks from FONT_SIZE_MAX down to FONT_SIZE_MIN; only then does the
    bubble grow. ``cell`` must already be in overlay coordinates (×``scale``).
    """
    cl, ct, cr, cb = cell
    cw = cr - cl
    ch = cb - ct
    btype = (bubble.type or "speech").lower()

    pad_x = BUBBLE_PAD_X * scale
    pad_y = BUBBLE_PAD_Y * scale
    spacing = LINE_SPACING * scale
    ow = BUBBLE_OUTLINE * scale
    size_max, size_min = FONT_SIZE_MAX, FONT_SIZE_MIN
    text_fill = INK
    if btype == "shout":
        ow = int(ow * 1.5)        # screams get a heavier stroke…
        size_max += 6             # …and larger lettering
    elif btype == "whisper":
        size_max -= 8             # whispers letter smaller and lighter
        size_min = max(24, size_min - 6)
        text_fill = WHISPER_INK

    # Horizontal slot for this bubble (LTR).
    slot_w = cw // max(1, n_slots)
    slot_cx = cl + slot_w * slot + slot_w // 2
    max_text_w = int(slot_w * 0.82) - 2 * pad_x
    max_text_w = max(80 * scale, max_text_w)

    # Auto-shrink font to fit width.
    size = size_max
    lines: list[str] = []
    while size >= size_min:
        font = fonts.at(size * scale)
        # char cap scales slightly with font so smaller text packs more.
        cap = MAX_CHARS_PER_LINE if size <= 38 else 18
        lines = _shape_lines(bubble.text, cap)
        tw, _th = _measure_lines(draw, lines, font, spacing)
        if tw <= max_text_w:
            break
        size -= 2
    font = fonts.at(max(size, size_min) * scale)
    tw, th = _measure_lines(draw, lines, font, spacing)

    # Bubble box. Round/irregular shapes inscribe the text rectangle, so their
    # bbox must be inflated beyond the text+padding or the lettering spills past the
    # visible outline (ellipse/cloud ≈ √2; spiky shapes a touch more). Rectangles
    # (narration) need no inflation.
    if btype == "narration":
        infl_x = infl_y = 1.0
    elif btype == "shout":
        infl_x, infl_y = 1.7, 1.7
    else:  # speech / thought / whisper / offscreen — oval/cloud bodies
        infl_x, infl_y = 1.45, 1.5
    bw = min(int((tw + 2 * pad_x) * infl_x), slot_w - 8 * scale)
    bh = int((th + 2 * pad_y) * infl_y)
    bcx = max(cl + bw // 2 + 4 * scale, min(slot_cx, cr - bw // 2 - 4 * scale))
    btop = ct + max(10 * scale, int(ch * 0.04))
    if top_floor:
        # Don't overlap the caption box above us.
        btop = max(btop, top_floor + 8 * scale)
    if n_slots > 1:
        # Stagger later bubbles slightly lower — proximity + diagonal flow makes
        # the reading order unambiguous.
        btop += int(ch * 0.05) * slot
    bl = int(bcx - bw / 2)
    br = int(bcx + bw / 2)
    bb_ = btop + bh
    bbox = (bl, btop, br, bb_)

    # Tail first (so the body outline sits over the tail base) for tailed types.
    has_tail = btype in ("speech", "shout", "offscreen", "whisper")
    if btype == "offscreen":
        # Tail points to the frame edge on the speaker's side rather than a point
        # inside the frame.
        edge_side = side if side in ("left", "right") else "left"
        tail = _tail_polygon(bbox, edge_side)
        # extend tip to the cell edge
        tip = (cl if edge_side == "left" else cr, tail[2][1])
        tail = [tail[0], tail[1], tip]
        draw.polygon(tail, fill=PAPER, outline=INK)
        draw.line([tail[0], tail[2], tail[1]], fill=INK, width=ow)
    elif has_tail:
        base1, base2, tip = _tail_polygon(bbox, side)
        side_a, side_b = _tail_curves(base1, base2, tip)
        draw.polygon(side_a + side_b[1:], fill=PAPER)
        draw.line(side_a, fill=INK, width=ow, joint="curve")
        draw.line(side_b, fill=INK, width=ow, joint="curve")

    _bubble_outline_shape(draw, bbox, btype, ow)
    if btype == "thought":
        _draw_thought_dots(draw, bbox, side, ow, scale)

    # Text — centered (both axes) inside the bubble, black on the white body.
    text_top = btop + (bh - th) // 2
    _draw_text_block(draw, lines, font, (bl + br) // 2, text_top, spacing, fill=text_fill)


def _render_caption(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    caption: Caption,
    cell: Cell,
    fonts: _FontCache,
    scale: int = 1,
) -> int:
    """Render a narration/transition caption box (rounded rectangle, no tail).

    Captions sit at the TOP-LEFT of the frame (Z order start) on the classic
    pale-cream narration background, so they're instantly distinguishable from
    white dialogue balloons. The font auto-shrinks down to CAPTION_FONT_MIN so a
    long transition line doesn't overflow the panel. ``cell`` must already be in
    overlay coordinates (×``scale``).

    Returns the bottom y of the caption box (overlay coords) so bubbles can be
    pushed below it instead of overlapping.
    """
    cl, ct, cr, _cb = cell
    cw = cr - cl
    spacing = LINE_SPACING * scale
    pad = 16 * scale
    max_w = cw - 20 * scale
    size = CAPTION_FONT_SIZE
    lines: list[str] = []
    while True:
        font = fonts.at(size * scale)
        lines = wrap_vietnamese(caption.text, MAX_CHARS_PER_LINE + 6)
        tw, th = _measure_lines(draw, lines, font, spacing)
        if tw + 2 * pad <= max_w or size <= CAPTION_FONT_MIN:
            break
        size -= 2
    if not lines:
        return ct
    bw = min(tw + 2 * pad, max_w)
    bh = th + 2 * pad
    bl = cl + 8 * scale
    bt = ct + 8 * scale
    box = (bl, bt, bl + bw, bt + bh)
    draw.rounded_rectangle(box, radius=6 * scale, fill=CAPTION_FILL, outline=INK, width=3 * scale)
    _draw_text_block(draw, lines, font, bl + bw // 2, bt + pad, spacing, fill=INK)
    return bt + bh


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compose_page(
    page: Page,
    panel_images: list[str],
    out_path: str,
    *,
    char_screen_sides: Optional[dict] = None,
    geometry: Optional[PageGeometry] = None,
    font_path: Optional[str] = None,
    layout_mode: str = "shot_list",
) -> str:
    """Composite one comic page → write a PNG at ``out_path``, return ``out_path``.

    Args:
      page: the Phase 2 :class:`~services.media.shot_list.Page` (layout + panels).
      panel_images: filesystem paths to the clean panel PNGs for this page, in the
        same order as ``page.panels``. Extra paths are ignored; missing ones draw a
        neutral placeholder cell.
      out_path: where to write the composed page PNG.
      char_screen_sides: optional chapter-wide ``{name: 'left'|'right'|'center'}``
        fallback used when a panel doesn't declare a speaker's side.
      geometry / font_path / layout_mode: overrides (defaults from spec §2.1 +
        vendored Be Vietnam Pro + honour the page's authored layout).

    Raises:
      FontUnavailableError: if the VN comic font can't be loaded (no silent
        non-VN fallback).
    """
    geom = geometry or PageGeometry()
    fonts = _FontCache(_resolve_font_path(font_path))
    # Touch the font once up-front so a missing/corrupt font fails fast (before we
    # do any raster work).
    fonts.at(FONT_SIZE_MAX)

    canvas = Image.new("RGB", (geom.width, geom.height), PAGE_BG)
    draw = ImageDraw.Draw(canvas)

    # Lettering (bubbles + captions) is drawn on a transparent overlay at
    # SUPERSAMPLE× resolution, then LANCZOS-downscaled onto the page — Pillow's
    # shape primitives aren't anti-aliased, and jagged balloon outlines are the
    # single biggest "programmatic" tell.
    ss = max(1, int(SUPERSAMPLE))
    overlay = Image.new("RGBA", (geom.width * ss, geom.height * ss), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    cells = layout_cells(page, geom, layout_mode)
    panels = list(page.panels)

    for idx, cell in enumerate(cells):
        if idx >= len(panels):
            break
        panel = panels[idx]
        img_path = panel_images[idx] if idx < len(panel_images) else ""
        _place_panel(canvas, draw, img_path, cell, geom.border)

        scell = (cell[0] * ss, cell[1] * ss, cell[2] * ss, cell[3] * ss)

        # Captions first (top-left, Z-order start), then bubbles pushed below
        # the lowest caption so the two never overlap.
        cap_bottom = 0
        for cap in (panel.captions or []):
            try:
                cap_bottom = max(cap_bottom, _render_caption(overlay, odraw, cap, scell, fonts, scale=ss))
            except Exception as e:  # one bad caption shouldn't kill the page
                logger.warning("Caption render skipped: %s", e)

        bubbles = list(panel.bubbles or [])[:MAX_BUBBLES_PER_FRAME]
        n_slots = max(1, len(bubbles))
        for slot, bubble in enumerate(bubbles):
            side = _speaker_side(panel, bubble, char_screen_sides)
            try:
                _render_bubble(
                    overlay, odraw, bubble, scell, slot, n_slots, side, fonts,
                    scale=ss, top_floor=cap_bottom,
                )
            except Exception as e:
                logger.warning("Bubble render skipped: %s", e)

    if ss > 1:
        overlay = overlay.resize((geom.width, geom.height), Image.LANCZOS)
    composed = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    composed.save(out_path, "PNG")
    return out_path


def compose_chapter(shot_list, panel_paths: list[str], out_dir: str, **kwargs) -> list[str]:
    """Composite a whole chapter shot-list → page PNGs in reading order.

    Args:
      shot_list: a :class:`~services.media.shot_list.ShotList` (or anything with a
        ``pages`` attribute / a dict carrying ``pages``). ``panel_paths`` are the
        clean panel PNGs for the chapter in flat reading order (one per panel across
        all pages), exactly as ``ImageGenerator.generate_story_images`` returns them.
      panel_paths: flat list of panel image paths in reading order.
      out_dir: directory to write the composed page PNGs into.
      **kwargs: forwarded to :func:`compose_page` (char_screen_sides, geometry,
        font_path, layout_mode, plus an optional ``chapter_number`` for filenames).

    Returns:
      The composed page PNG paths in reading order.
    """
    chapter_number = int(kwargs.pop("chapter_number", 0) or 0)
    pages = _coerce_pages(shot_list)
    os.makedirs(out_dir, exist_ok=True)

    out_paths: list[str] = []
    cursor = 0
    for page in pages:
        n = len(page.panels)
        page_imgs = panel_paths[cursor:cursor + n]
        cursor += n
        if not page_imgs:
            # No panels generated for this page (e.g. image gen produced fewer
            # images than the shot-list expected) — skip rather than emit a blank.
            continue
        fname = f"ch{chapter_number:02d}_page{page.page:02d}.png"
        out_path = os.path.join(out_dir, fname)
        compose_page(page, page_imgs, out_path, **kwargs)
        out_paths.append(out_path)
    return out_paths


def _coerce_pages(shot_list) -> list[Page]:
    """Accept a ShotList, a list[Page], or the persisted dict and yield Pages."""
    if shot_list is None:
        return []
    pages = getattr(shot_list, "pages", None)
    if pages is None and isinstance(shot_list, dict):
        pages = shot_list.get("pages")
    if pages is None and isinstance(shot_list, list):
        pages = shot_list
    out: list[Page] = []
    for p in (pages or []):
        if isinstance(p, Page):
            out.append(p)
        elif isinstance(p, dict):
            out.append(Page(**p))
    return out
