"""One-off: run the REAL comic image path (codex + bubble bake) on an existing
story checkpoint, chapter 1, and report the panel paths. Faithful production
path: _payload_to_story_draft -> _PayloadOrchWrapper -> handle_generate_images.
"""

import json
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

CHECKPOINT = (
    "output/binh_than_thuc_duoc_pham_nhan_nghich_thien/checkpoints/"
    "Bình_Thần_Thúc_Dược__Phàm_Nhân_layer2_e7c43f15afa9ba50.json"
)

d = json.load(open(CHECKPOINT, encoding="utf-8"))
es = d["enhanced_story"]
sd = d.get("story_draft") or {}
chars = es.get("characters") or sd.get("characters") or []
chapters = es.get("chapters") or []

from api.export_routes import (
    _LibraryStoryPayload,
    _LibraryChapterPayload,
    _LibraryCharacterPayload,
    _payload_to_story_draft,
)
from api.image_routes import _PayloadOrchWrapper
from models.schemas import PipelineOutput
from config import ConfigManager
from services.handlers import handle_generate_images

payload = _LibraryStoryPayload(
    id="eval-codex-comic",
    title="Bình Thần Thúc Dược (codex eval)",
    genre=es.get("genre", "") or "Tiên hiệp",
    characters=[
        _LibraryCharacterPayload(
            name=c.get("name", ""),
            role=c.get("role", "") or "",
            description=c.get("appearance")
            or c.get("personality")
            or c.get("description", "")
            or "",
            backstory=c.get("backstory", "") or "",
        )
        for c in chars
    ],
    chapters=[
        _LibraryChapterPayload(
            title=ch.get("title", ""),
            content=ch.get("content", ""),
            summary=ch.get("summary", "") or "",
            images=[],  # force generation
        )
        for ch in chapters
    ],
)

draft = _payload_to_story_draft(payload)
orch = _PayloadOrchWrapper(PipelineOutput(story_draft=draft, status="complete"))

# Enable the comic shot-list stage (codex skips the compositor anyway).
cfg = ConfigManager().pipeline
cfg.comic_shot_list_enabled = True
cfg.image_provider = "codex"
print(
    f"provider={cfg.image_provider} shot_list={cfg.comic_shot_list_enabled} "
    f"panels={cfg.panels_per_chapter} chars={len(draft.characters)} "
    f"chapters={len(draft.chapters)}",
    flush=True,
)

paths, msg = handle_generate_images(orch, provider="codex", t=None, chapter_number=1)
print("\nMSG:", msg, flush=True)
print(f"PANELS: {len(paths)}", flush=True)
for p in paths:
    print("  ", p, flush=True)
