"""Character forms — draw each chapter with a character as they look by then.

A character who changes robes, loses an arm or wakes up with white hair used to
be drawn as their chapter-1 self forever: the profile store held one frozen
prompt and one reference image per character (Batch L, L3).

Forms are stored beside that prompt and image, in CharacterVisualProfileStore,
and derived from the chapter text at comic time. The Library comic path carries
only four character fields, so nothing can ride on the Character model; this
keeps the feature in one place for every path that draws a comic (CEO decision,
2026-09-14).

- ``ensure_forms``: one cheap LLM call per chapter, cached by content digest. A
  change is accepted only when its quoted evidence occurs verbatim in the
  chapter and it names a known character; both checks are deterministic.
- ``prepare_form_references``: option B. Render a form's reference image once,
  from the base reference, on a reference-capable provider. Otherwise the form
  still changes the prompt (option A).
- ``for_chapter``: the profiles and references to draw chapter N with. It is
  pure, so chapters can render concurrently.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re

from services.llm_client import LLMClient  # noqa: F401 — the handler builds it through this module, and tests patch it here

logger = logging.getLogger(__name__)

# Evidence shorter than this is too easy to "find" by accident.
MIN_EVIDENCE_CHARS = 12

# Descriptions (English, per the prompt) that end a character or describe a
# momentary effect rather than a look to keep drawing. A deterministic backstop
# for the prompt's exclusions — the model does not always follow them.
_ENDS_THE_CHARACTER = re.compile(
    r"\b(dead|death|dies|died|deceased|killed|corpse|lifeless|skeleton|bones|"
    r"remains|ashes|shattered|disintegrat\w*|annihilated|obliterated|vanish\w*)\b",
    re.IGNORECASE,
)

_FORMS_PROMPT = """Bạn là biên tập viên hình ảnh cho truyện tranh chuyển thể. Đọc chương dưới đây và tìm những THAY ĐỔI NGOẠI HÌNH LÂU DÀI của các nhân vật trong danh sách — thay đổi mà các chương sau vẫn phải vẽ đúng.

Tính là thay đổi lâu dài: mặc trang phục, đạo bào hay giáp mới và tiếp tục mặc; mất hoặc thay một bộ phận cơ thể; sẹo hay hình xăm mới; đổi màu tóc hoặc kiểu tóc; biến đổi hình dạng sau khi thức tỉnh, đột phá hay trúng độc lâu dài; già đi rõ rệt.
KHÔNG tính:
- nhân vật chết, bị giết, thân thể bị hủy diệt hay tan biến — đó là kết thúc của nhân vật, không phải một ngoại hình để vẽ tiếp;
- khoảnh khắc biến đổi đang diễn ra (phát sáng, tan thành hạt sáng, hào quang bao quanh) — chỉ tính ngoại hình SAU khi biến đổi xong, nếu chương có tả;
- quần áo rách, bẩn, cháy do giao chiến hay tai nạn trong cảnh;
- vật cầm theo hoặc phụ kiện nhỏ (túi, ngọc bội, thư, vũ khí cầm tay);
- mệt mỏi, dính máu, ướt, bẩn, vết thương nhẹ sẽ lành, cảm xúc, tư thế, thay đồ chỉ trong một cảnh.

NHÂN VẬT (dùng đúng tên này):
{names}

Với mỗi thay đổi:
- "name": tên nhân vật, đúng như danh sách trên.
- "description": ngoại hình KẾT QUẢ mà các chương sau phải vẽ, không phải sự kiện gây ra nó — bằng tiếng Anh, ngắn gọn, vẽ được (ví dụ "white Taoist robe with silver trim", không phải "his robe turned white during the ceremony").
- "evidence": một câu TRÍCH NGUYÊN VĂN từ chương cho thấy thay đổi đó. Không diễn đạt lại.

Nếu không có thay đổi lâu dài nào, trả về {{"changes": []}}.

CHƯƠNG {n}:
{content}

Trả về JSON: {{"changes": [{{"name": "...", "description": "...", "evidence": "..."}}]}}"""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _digest(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def detect_changes(llm, chapter, characters) -> list[dict]:
    """The lasting appearance changes one chapter makes, verified against its text."""
    names = [c.name for c in characters or [] if getattr(c, "name", "")]
    content = getattr(chapter, "content", "") or ""
    if not names or not content.strip():
        return []
    raw = llm.generate_json(
        system_prompt="Bạn là biên tập viên hình ảnh truyện tranh. Trả về JSON.",
        user_prompt=_FORMS_PROMPT.format(
            n=chapter.chapter_number,
            names="\n".join(f"- {n}" for n in names),
            content=content,
        ),
        temperature=0.2,
        max_tokens=1200,
        model_tier="cheap",
        expect="dict",
        list_key="changes",
    )
    text = _norm(content)
    accepted: list[dict] = []
    for item in (raw or {}).get("changes") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        evidence = _norm(str(item.get("evidence") or ""))
        if name not in names or not description:
            logger.info("Character forms ch%s: dropped change for unknown %r", chapter.chapter_number, name)
            continue
        if _ENDS_THE_CHARACTER.search(description):
            # Verbatim evidence does not make it a look: a real run accepted
            # "reduced to a pile of bones", which would then be drawn in every
            # later panel the character appears in (flashbacks included).
            logger.info(
                "Character forms ch%s: dropped %s change, it describes an ending, not a look: %r",
                chapter.chapter_number,
                name,
                description,
            )
            continue
        if len(evidence) < MIN_EVIDENCE_CHARS or evidence not in text:
            logger.info(
                "Character forms ch%s: dropped %s change, evidence not found in the chapter",
                chapter.chapter_number,
                name,
            )
            continue
        accepted.append({"name": name, "description": description, "evidence": evidence})
    return accepted


def ensure_forms(store, llm, chapters, characters, upto_chapter: int) -> None:
    """Scan every chapter up to ``upto_chapter`` whose text has not been scanned.

    A chapter is re-scanned when its content changed, and its old forms are
    replaced. A failed scan is not recorded, so the next comic run retries it.
    """
    scanned = store.get_scanned_chapters()
    if not isinstance(scanned, dict):
        return
    for chapter in sorted(chapters or [], key=lambda c: c.chapter_number):
        n = chapter.chapter_number
        if n > upto_chapter:
            break
        digest = _digest(chapter.content)
        if scanned.get(str(n)) == digest:
            continue
        try:
            changes = detect_changes(llm, chapter, characters)
        except Exception as e:
            logger.warning("Character forms: chapter %s not scanned (%s)", n, e)
            continue
        store.remove_forms_from_chapter(n)
        for change in changes:
            store.add_form(
                change["name"],
                {
                    "from_chapter": n,
                    "description": change["description"],
                    "evidence": change["evidence"],
                    "reference_image": "",
                },
            )
        store.mark_chapter_scanned(n, digest)
        scanned[str(n)] = digest


def form_for_chapter(forms, chapter_number: int):
    """The latest form in effect at ``chapter_number``, or None."""
    best = None
    for form in forms if isinstance(forms, list) else []:
        if not isinstance(form, dict):
            continue
        try:
            start = int(form.get("from_chapter"))
        except (TypeError, ValueError):
            continue
        if start <= chapter_number and (best is None or start >= int(best["from_chapter"])):
            best = form
    return best


def prepare_form_references(store, characters, visual_profiles, character_references, image_gen, provider: str) -> dict:
    """Load every character's forms, rendering missing form references (option B).

    Runs before chapters fan out, so each reference is rendered once. Without a
    reference-capable provider or a base reference to derive from, a form keeps
    an empty reference and only changes the prompt (option A).
    """
    from services.media.comic_chapter import REF_CAPABLE

    forms_by_name: dict = {}
    for character in characters or []:
        forms = store.get_forms(character.name)
        if not isinstance(forms, list) or not forms:
            continue
        base_ref = (character_references or {}).get(character.name)
        for form in forms:
            ref = form.get("reference_image") or ""
            if ref and os.path.exists(ref):
                continue
            if image_gen is None or provider not in REF_CAPABLE or not base_ref or not os.path.exists(base_ref):
                continue
            base_prompt = (visual_profiles or {}).get(character.name, "")
            prompt = (
                f"{base_prompt}\n\nThe SAME character as in the reference image — same face "
                f"and identity — now with this lasting change: {form['description']}. "
                "Character reference portrait: head-and-shoulders, front three-quarter "
                "view, neutral expression, even soft lighting, plain flat background, "
                "the whole face clearly visible. No other characters, and no text or "
                "lettering of any kind."
            )
            safe = re.sub(r"[^\w\-]+", "_", character.name).strip("_") or "character"
            try:
                path = image_gen.generate_with_reference(
                    prompt,
                    [base_ref],
                    filename=os.path.join("avatars", f"{safe}_ch{form['from_chapter']}.png"),
                )
            except Exception as e:
                logger.warning(
                    "Form reference for %s (ch%s) failed, drawing from the prompt only: %s",
                    character.name,
                    form["from_chapter"],
                    e,
                )
                path = None
            if path and os.path.exists(path):
                store.set_form_reference(character.name, form["from_chapter"], path)
                form["reference_image"] = path
        forms_by_name[character.name] = forms
    return forms_by_name


def for_chapter(chapter_number: int, visual_profiles, character_references, forms_by_name):
    """(visual_profiles, character_references) to draw ``chapter_number`` with.

    Returns the inputs themselves when no form applies, and never mutates them.
    """
    profiles = dict(visual_profiles or {})
    refs = dict(character_references or {})
    changed = False
    for name, forms in (forms_by_name or {}).items():
        form = form_for_chapter(forms, chapter_number)
        if not form:
            continue
        base = profiles.get(name, "")
        profiles[name] = (
            f"{base}\nCurrent appearance (since chapter {form['from_chapter']}): {form['description']}"
        ).strip()
        ref = form.get("reference_image") or ""
        if ref and os.path.exists(ref):
            refs[name] = ref
        changed = True
    if not changed:
        return visual_profiles, character_references
    return profiles, refs
