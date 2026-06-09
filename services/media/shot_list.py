"""Comic Beat→Shot-list extractor (Phase 2).

Inserts an LLM stage between chapter prose and image generation: a chapter is
split into ordered BEATs (≈1 beat per panel), and each beat is assigned a
``shot`` type, a page/layout, dialogue bubbles + speaker, and ``screen_side``
(180° placement). The result is a shot-list JSON matching spec §4.2.

Image prompts still carry NO dialogue text — the dialogue/caption fields here are
consumed only by Phase 3's page compositor. This module owns the *data* stage:
it does not draw bubbles or composite pages.

The LLM is untrustworthy about following the structural rules, so the raw model
output is run through deterministic post-processing (``enforce_rules``) that:

  - prevents two adjacent panels sharing the same ``shot``;
  - caps each panel at ≤2 bubbles and splits a long speaker (> ~20 Vietnamese
    words) into a new panel;
  - forces the first panel of a NEW scene to an establishing shot (EWS/WS) with
    a caption when the location/time changed;
  - tags the single biggest beat of the chapter as ``layout: "SPLASH"``;
  - resolves each ``subject`` to a saved character reference (seed + reference
    image + frozen descriptor) via the same ``character_references`` map that
    ``ImageGenerator.generate_story_images`` consumes.

Vietnamese dialogue must round-trip byte-for-byte (diacritics preserved); none of
the post-processing mutates bubble/caption text.
"""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from models.schemas import Chapter, ImagePrompt
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Shot-type vocabulary (spec §2.3). Establishing shots open a new scene.
ESTABLISHING_SHOTS = ("EWS", "WS")
SHOT_VOCAB = ("EWS", "WS", "MS", "CU", "ECU", "OTS", "INSERT", "REACTION")
# Fallback rotation used when an adjacent-shot clash must be broken.
_SHOT_ROTATION = ("MS", "CU", "OTS", "ECU", "WS", "REACTION", "INSERT", "EWS")

# Layout library (spec §2.2), keyed by panels-per-page. Used to pick a default
# layout when the LLM omits/garbles it.
_LAYOUT_BY_COUNT = {
    1: "SPLASH",
    2: "TWO_TIER",
    3: "THREE_TIER",
    4: "GRID_2x2",
    5: "BIG_PLUS_TWO",
    6: "SIX_GRID",
}

# A speaker line longer than this many Vietnamese words is split into a new panel.
MAX_WORDS_PER_BUBBLE = 20
MAX_BUBBLES_PER_PANEL = 2

# Prompt is self-contained (mirrors image_prompt_generator._SCENE_EXTRACT_PROMPT).
_SHOT_LIST_PROMPT = """Bạn là biên kịch truyện tranh (comic storyboard artist). Cắt văn xuôi chương dưới đây thành các BEAT theo thứ tự, mỗi beat ≈ một khung (panel).

Một BEAT mới bắt đầu khi: đổi địa điểm / có người nói mới / bước ngoặt cảm xúc / nhảy thời gian / một reveal. Mục tiêu ~{num_panels} panel.

Với mỗi panel, gán:
- shot: một trong EWS|WS|MS|CU|ECU|OTS|INSERT|REACTION. KHÔNG để hai panel liền kề trùng shot. Panel đầu của một cảnh MỚI phải là EWS hoặc WS (establishing).
- beat: mô tả ngắn (tiếng Anh) khoảnh khắc.
- subject: tên nhân vật chính trong khung (đúng như NHÂN VẬT bên dưới).
- camera, action, setting, mood: mô tả ngắn (tiếng Anh).
- screen_side: vị trí trái/giữa/phải của từng nhân vật trong khung (giữ luật 180°), ví dụ {{"Kiên": "right"}}.
- captions: hộp narration/chuyển cảnh. Dùng khi đổi địa điểm/thời gian. text giữ NGUYÊN tiếng Việt có dấu.
- bubbles: tối đa 2 bong bóng/panel. Mỗi bong bóng {{"speaker": tên, "type": "speech|thought|shout|whisper", "text": lời thoại}}. text giữ NGUYÊN tiếng Việt có dấu, byte-for-byte như trong văn xuôi.

Beat lớn nhất/quan trọng nhất của chương đặt một mình trên một trang layout SPLASH.

NỘI DUNG:
{content}

NHÂN VẬT:
{characters}

Trả về JSON đúng schema:
{{"pages": [{{"page": 1, "layout": "THREE_TIER", "panels": [{{"n": 1, "shot": "EWS", "beat": "...", "subject": "...", "camera": "...", "action": "...", "setting": "...", "mood": "...", "screen_side": {{}}, "captions": [{{"type": "narration", "text": "..."}}], "bubbles": [{{"speaker": "...", "type": "speech", "text": "..."}}]}}]}}]}}"""


# ---------------------------------------------------------------------------
# Data model (spec §4.2)
# ---------------------------------------------------------------------------
class Bubble(BaseModel):
    """A single dialogue bubble. ``text`` is Vietnamese, preserved verbatim."""
    speaker: str = ""
    type: str = "speech"  # speech|thought|shout|whisper|offscreen
    text: str = ""


class Caption(BaseModel):
    """A narration / scene-transition caption box (no tail)."""
    type: str = "narration"  # narration|transition
    text: str = ""


class Panel(BaseModel):
    """One comic panel ≈ one beat."""
    n: int = 0
    shot: str = "MS"
    beat: str = ""
    subject: str = ""
    subject_ref: str = ""  # resolved character-reference id / image path
    camera: str = ""
    action: str = ""
    setting: str = ""
    mood: str = ""
    screen_side: dict = Field(default_factory=dict)
    captions: list[Caption] = Field(default_factory=list)
    bubbles: list[Bubble] = Field(default_factory=list)


class Page(BaseModel):
    """A page = a layout + its ordered panels."""
    page: int = 1
    layout: str = "THREE_TIER"
    panels: list[Panel] = Field(default_factory=list)


class ShotList(BaseModel):
    """The full shot-list for one chapter."""
    chapter_number: int = 0
    pages: list[Page] = Field(default_factory=list)

    def all_panels(self) -> list[Panel]:
        """Flatten panels across pages in reading order."""
        return [p for page in self.pages for p in page.panels]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _word_count_vi(text: str) -> int:
    """Count Vietnamese words. Diacritics are part of the word, not separators."""
    return len([w for w in re.split(r"\s+", (text or "").strip()) if w])


def _layout_for(panel_count: int) -> str:
    """Pick a finite-library layout for a page of ``panel_count`` panels."""
    if panel_count <= 1:
        return "SPLASH"
    return _LAYOUT_BY_COUNT.get(panel_count, "SIX_GRID")


def _beat_weight(panel: Panel) -> int:
    """Heuristic 'bigness' of a beat — used to pick the SPLASH beat.

    Bigger = more dialogue + richer action/mood text. Deterministic so the
    SPLASH assignment is stable for tests.
    """
    dialogue_chars = sum(len(b.text) for b in panel.bubbles)
    caption_chars = sum(len(c.text) for c in panel.captions)
    descriptive = len(panel.action) + len(panel.beat) + len(panel.mood)
    return dialogue_chars + caption_chars + descriptive


# ---------------------------------------------------------------------------
# Deterministic rule enforcement (spec §4.2 step 3)
# ---------------------------------------------------------------------------
def enforce_rules(
    shot_list: ShotList,
    character_references: dict | None = None,
) -> ShotList:
    """Apply spec §4.2 step-3 rules deterministically on top of LLM output.

    Never trusts the LLM to have followed the rules. Returns a new normalized
    ``ShotList``. Dialogue/caption text is preserved verbatim (no diacritic
    mangling); only structure (shot type, panel splitting, layout, refs) is
    rewritten.
    """
    refs = character_references or {}
    panels = shot_list.all_panels()

    # --- Rule: ≤2 bubbles/panel, and split a long speaker into a new panel. ---
    split_panels: list[Panel] = []
    for panel in panels:
        bubbles = list(panel.bubbles)
        # Find an over-long bubble (> MAX_WORDS_PER_BUBBLE Vietnamese words).
        first_long_idx = next(
            (i for i, b in enumerate(bubbles)
             if _word_count_vi(b.text) > MAX_WORDS_PER_BUBBLE),
            None,
        )
        if first_long_idx is not None and first_long_idx > 0:
            # Carry the long bubble (and everything after) into a new panel.
            head = panel.model_copy(deep=True)
            head.bubbles = bubbles[:first_long_idx]
            tail = panel.model_copy(deep=True)
            tail.bubbles = bubbles[first_long_idx:]
            split_panels.append(head)
            split_panels.append(tail)
            continue
        if len(bubbles) > MAX_BUBBLES_PER_PANEL:
            # Chunk overflow bubbles into additional panels of ≤2 each.
            for start in range(0, len(bubbles), MAX_BUBBLES_PER_PANEL):
                chunk = panel.model_copy(deep=True)
                chunk.bubbles = bubbles[start:start + MAX_BUBBLES_PER_PANEL]
                # Only the first chunk keeps captions to avoid duplicate narration.
                if start > 0:
                    chunk.captions = []
                split_panels.append(chunk)
            continue
        split_panels.append(panel)

    panels = split_panels

    # --- Rule: first panel of a NEW scene = establishing (EWS/WS). ---
    # A new scene = the setting/location text changed from the previous panel.
    prev_setting = None
    for idx, panel in enumerate(panels):
        setting = (panel.setting or "").strip().lower()
        is_new_scene = idx == 0 or (setting and setting != prev_setting)
        if is_new_scene and panel.shot.upper() not in ESTABLISHING_SHOTS:
            panel.shot = "EWS"
            # Caption when location/time changed and none present yet (spec).
            if idx != 0 and not panel.captions and panel.setting:
                panel.captions = [Caption(type="transition", text=panel.setting)]
        if setting:
            prev_setting = setting

    # --- Rule: no two adjacent panels share the same shot. ---
    for idx in range(1, len(panels)):
        cur = panels[idx].shot.upper()
        prev = panels[idx - 1].shot.upper()
        if cur == prev:
            # Pick the first rotation shot that differs from BOTH neighbours,
            # without demoting an establishing shot that a new scene requires.
            nxt = (panels[idx + 1].shot.upper()
                   if idx + 1 < len(panels) else "")
            replacement = next(
                (s for s in _SHOT_ROTATION if s != prev and s != nxt),
                "MS",
            )
            panels[idx].shot = replacement

    # --- Rule: resolve each subject → saved character reference. ---
    for panel in panels:
        ref = refs.get(panel.subject)
        if ref:
            panel.subject_ref = ref

    # --- Rule: biggest beat → its own SPLASH page. ---
    # Renumber panels in reading order first.
    for i, panel in enumerate(panels, 1):
        panel.n = i

    splash_idx = (max(range(len(panels)), key=lambda i: _beat_weight(panels[i]))
                  if panels else None)

    # --- Re-page: SPLASH beat solo; everything else in 3-panel THREE_TIER pages. ---
    pages: list[Page] = []
    page_num = 1
    buffer: list[Panel] = []

    def _flush(buf: list[Panel]) -> None:
        nonlocal page_num
        if not buf:
            return
        # A lone leftover panel must NOT become an incidental SPLASH (SPLASH is
        # reserved for the biggest beat). Fold it into the previous regular page
        # (max 4 → GRID_2x2); only stand alone as a last resort.
        if len(buf) == 1 and pages and pages[-1].layout != "SPLASH" \
                and len(pages[-1].panels) < 4:
            pages[-1].panels.extend(buf)
            pages[-1].layout = _layout_for(len(pages[-1].panels))
            return
        pages.append(Page(
            page=page_num,
            layout=_layout_for(len(buf)) if len(buf) > 1 else "TWO_TIER",
            panels=list(buf),
        ))
        page_num += 1

    for i, panel in enumerate(panels):
        if i == splash_idx:
            _flush(buffer)
            buffer = []
            pages.append(Page(page=page_num, layout="SPLASH", panels=[panel]))
            page_num += 1
            continue
        buffer.append(panel)
        if len(buffer) == 3:
            _flush(buffer)
            buffer = []
    _flush(buffer)

    # Renumber pages sequentially (folding may have left gaps).
    for i, page in enumerate(pages, 1):
        page.page = i

    return ShotList(chapter_number=shot_list.chapter_number, pages=pages)


def _parse_pages(raw: dict, chapter_number: int) -> ShotList:
    """Coerce the raw LLM dict into a ShotList, tolerant of minor shape drift."""
    pages_raw = raw.get("pages")
    if not isinstance(pages_raw, list):
        # Some models emit a bare {"panels": [...]} — wrap it as a single page.
        if isinstance(raw.get("panels"), list):
            pages_raw = [{"page": 1, "panels": raw["panels"]}]
        else:
            pages_raw = []
    pages: list[Page] = []
    for pi, pg in enumerate(pages_raw, 1):
        if not isinstance(pg, dict):
            continue
        panels: list[Panel] = []
        for panel_raw in pg.get("panels", []) or []:
            if not isinstance(panel_raw, dict):
                continue
            bubbles = [
                Bubble(
                    speaker=str(b.get("speaker", "")),
                    type=str(b.get("type", "speech")),
                    text=str(b.get("text", "")),
                )
                for b in panel_raw.get("bubbles", []) or []
                if isinstance(b, dict)
            ]
            captions = [
                Caption(
                    type=str(c.get("type", "narration")),
                    text=str(c.get("text", "")),
                )
                for c in panel_raw.get("captions", []) or []
                if isinstance(c, dict)
            ]
            screen_side = panel_raw.get("screen_side")
            panels.append(Panel(
                n=int(panel_raw.get("n", 0) or 0),
                shot=str(panel_raw.get("shot", "MS")).upper() or "MS",
                beat=str(panel_raw.get("beat", "")),
                subject=str(panel_raw.get("subject", "")),
                subject_ref=str(panel_raw.get("subject_ref", "")),
                camera=str(panel_raw.get("camera", "")),
                action=str(panel_raw.get("action", "")),
                setting=str(panel_raw.get("setting", "")),
                mood=str(panel_raw.get("mood", "")),
                screen_side=screen_side if isinstance(screen_side, dict) else {},
                captions=captions,
                bubbles=bubbles,
            ))
        pages.append(Page(
            page=int(pg.get("page", pi) or pi),
            layout=str(pg.get("layout", "THREE_TIER")),
            panels=panels,
        ))
    return ShotList(chapter_number=chapter_number, pages=pages)


class ShotListExtractor:
    """LLM beat extractor → shot-list (spec §4.2).

    Mirrors ``ImagePromptGenerator``: reuses the project ``LLMClient`` and its
    ``generate_json`` plumbing (cheap tier, JSON-repair, retries). No new LLM
    client is introduced.
    """

    def __init__(self):
        self.llm = LLMClient()

    def extract(
        self,
        chapter: Chapter,
        characters: list | None = None,
        num_panels: int = 8,
        character_references: dict | None = None,
        visual_profiles: dict | None = None,
    ) -> ShotList:
        """Extract a chapter into a rule-enforced shot-list.

        Args:
            chapter: the chapter to storyboard.
            characters: list of Character objects (for the subject roster).
            num_panels: target panels for the chapter (~1 beat each).
            character_references: {name: reference image path} — the SAME map
                ``ImageGenerator.generate_story_images`` consumes. Each subject is
                resolved to its saved reference here.
            visual_profiles: {name: frozen_visual_description} (roster hints only).

        Returns a ``ShotList`` (post-processed); on any failure, an empty
        ``ShotList`` so the pipeline degrades to the legacy image path.
        """
        chars_text = ""
        if characters:
            parts = []
            for c in characters:
                desc = getattr(c, "appearance", None) or getattr(c, "personality", "")
                if visual_profiles and c.name in visual_profiles:
                    desc = visual_profiles[c.name]
                parts.append(f"- {c.name}: {desc}")
            chars_text = "\n".join(parts)

        try:
            raw = self.llm.generate_json(
                system_prompt="Bạn là biên kịch truyện tranh. Trả về JSON.",
                user_prompt=_SHOT_LIST_PROMPT.format(
                    num_panels=num_panels,
                    content=chapter.content[:3000],
                    characters=chars_text or "Không có thông tin",
                ),
                temperature=0.5,
                max_tokens=2500,
                model_tier="cheap",
                expect="dict",
                list_key="pages",
            )
            shot_list = _parse_pages(raw or {}, chapter.chapter_number)
            return enforce_rules(shot_list, character_references=character_references)
        except Exception as e:
            logger.warning(
                "Shot-list extraction failed for ch %s: %s",
                chapter.chapter_number, e,
            )
            return ShotList(chapter_number=chapter.chapter_number, pages=[])


def apply_shot_list_to_prompts(
    prompts: list[ImagePrompt],
    shot_list: ShotList,
) -> list[ImagePrompt]:
    """Thread shot-list panel metadata onto matching ImagePrompt objects.

    Aligns panels to prompts by reading order (panel n → prompt index) and copies
    ``shot_type``, ``dialogue`` and ``screen_side`` onto each ImagePrompt so the
    metadata travels with the prompt into image generation. The image *prompt
    text* is left untouched — it still carries NO dialogue; only the Phase 3
    compositor reads ``dialogue``.

    Mutates and returns ``prompts`` (in place) for caller convenience.
    """
    panels = shot_list.all_panels()
    for ip, panel in zip(prompts, panels):
        ip.shot_type = panel.shot
        ip.dialogue = [b.model_dump() for b in panel.bubbles]
        ip.screen_side = dict(panel.screen_side)
    return prompts


def extract_shot_list(
    chapter: Chapter,
    characters: list | None = None,
    num_panels: int = 8,
    character_references: dict | None = None,
    visual_profiles: dict | None = None,
) -> ShotList:
    """Module-level convenience wrapper around ``ShotListExtractor.extract``."""
    return ShotListExtractor().extract(
        chapter,
        characters=characters,
        num_panels=num_panels,
        character_references=character_references,
        visual_profiles=visual_profiles,
    )
