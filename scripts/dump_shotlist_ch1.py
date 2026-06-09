"""Dump the shot-list for chapter 1 — per-panel dialogue/caption — to confirm
which panels are SILENT (codex invents English text there)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

CHECKPOINT = ("output/binh_than_thuc_duoc_pham_nhan_nghich_thien/checkpoints/"
              "Bình_Thần_Thúc_Dược__Phàm_Nhân_layer2_e7c43f15afa9ba50.json")
d = json.load(open(CHECKPOINT, encoding="utf-8"))
es = d["enhanced_story"]; sd = d.get("story_draft") or {}
chars = es.get("characters") or sd.get("characters") or []
ch = es["chapters"][0]

from models.schemas import Chapter, Character
chapter = Chapter(chapter_number=1, title=ch.get("title", ""), content=ch.get("content", ""),
                  summary=ch.get("summary", ""))
characters = [Character(name=c.get("name", ""), role=c.get("role", "") or "nhân vật",
                        appearance=c.get("appearance", "") or c.get("personality", ""),
                        personality=c.get("personality", "")) for c in chars]

from services.shot_list import ShotListExtractor
sl = ShotListExtractor().extract(chapter, characters=characters, num_panels=8)
n = 0
for page in sl.pages:
    for panel in page.panels:
        n += 1
        bubs = [b for b in (panel.bubbles or []) if (b.text or "").strip()]
        caps = getattr(panel, "captions", None) or []
        tag = "SILENT" if not bubs else f"{len(bubs)} bubble(s)"
        print(f"panel {n:02d} [{panel.shot}] {tag}  captions={caps}")
        for b in bubs:
            print(f"    - {b.speaker} ({b.type}): {b.text!r}")
