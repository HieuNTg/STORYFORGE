"""One chapter → finished comic pages. The single comic path.

Why this module exists: the same work used to live only inside
``services.handlers.handle_generate_images`` (the Reader's on-demand button),
while the pipeline's media stage (``pipeline/orchestrator_media.py``) ran its
own, much older routine — no shot list, no dialogue, no page composition. A
story generated end-to-end therefore came out as loose illustrations, and only
pressing "regenerate" in the Reader produced an actual comic. Both callers now
run this function, so a chapter looks the same however it was produced.

The stage order is fixed:

1. panel count for the chapter (``panels_for_chapter``)
2. beat → shot list (gated by ``comic_shot_list_enabled``; falls back to the
   legacy prose-scene extractor when off or on failure)
3. one image prompt per panel, 1:1 in reading order
4. panel metadata threaded onto the prompts + per-panel target size derived from
   the page cell each panel lands in
5. image generation (references attached for character consistency)
6. page composition (gated by ``comic_compositor_enabled``) — the composed pages
   REPLACE the loose panels in the returned paths; panels stay on disk

Every optional stage degrades instead of raising: a failed shot list falls back
to prose scenes, a failed compositor returns the loose panels.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: Providers that can condition on a reference image (character consistency).
REF_CAPABLE = {"flowkit", "codex", "seedream", "replicate", "qwen-local"}


class ComicSettings:
    """The comic-related config, resolved once per run."""

    def __init__(self, cfg: Any, provider: str = ""):
        self.shot_list_enabled = bool(
            getattr(cfg, "comic_shot_list_enabled", False)
        )
        self.compositor_enabled = bool(
            getattr(cfg, "comic_compositor_enabled", False)
        )
        self.coverage_check = bool(
            getattr(cfg, "comic_coverage_check_enabled", True)
        )
        self.canvas = getattr(cfg, "comic_page_canvas", None)
        self.font = getattr(cfg, "comic_font", None) or None
        self.layout_mode = getattr(cfg, "comic_layout_mode", "shot_list")
        # Codex renders in-image Vietnamese text well, so it draws its own
        # balloons and skips the vector compositor.
        self.is_codex = str(provider or "").strip().lower() == "codex"
        self.cfg = cfg

    @property
    def compose_pages(self) -> bool:
        return (
            self.compositor_enabled and self.shot_list_enabled and not self.is_codex
        )


def make_shot_extractor(settings: ComicSettings):
    """The shot-list extractor, or None when the stage is off/unavailable."""
    if not settings.shot_list_enabled:
        return None
    try:
        from services.media.shot_list import ShotListExtractor

        return ShotListExtractor()
    except Exception as e:  # pragma: no cover - import-time environment issue
        logger.warning("Shot-list stage unavailable, skipping: %s", e)
        return None


def generate_chapter_comic(
    chapter,
    *,
    prompt_gen,
    image_gen,
    settings: ComicSettings,
    shot_extractor=None,
    characters: Optional[list] = None,
    character_references: Optional[dict] = None,
    visual_profiles: Optional[dict] = None,
) -> list[str]:
    """Produce one chapter's comic pages (or loose panels) and return the paths.

    ``chapter.shot_list`` is populated as a side effect when the shot-list stage
    succeeds, because the compositor and the Reader both read it back later.
    """

    from services.media.shot_list import panels_for_chapter

    num_panels = panels_for_chapter(chapter, settings.cfg)
    prompts: list = []
    shot_list = None

    if shot_extractor is not None:
        try:
            extracted = shot_extractor.extract(
                chapter,
                characters=characters or None,
                num_panels=num_panels,
                character_references=character_references or None,
                visual_profiles=visual_profiles or None,
                coverage_check=settings.coverage_check,
            )
            if extracted.pages:
                chapter.shot_list = extracted.model_dump()
                shot_list = extracted
                prompts = prompt_gen.generate_from_shot_list(
                    extracted,
                    chapter,
                    characters=characters or None,
                    visual_profiles=visual_profiles or None,
                )
        except Exception as e:
            logger.warning(
                "Shot-list extraction failed for ch %s, continuing without: %s",
                getattr(chapter, "chapter_number", "?"),
                e,
            )

    if not prompts:
        # Legacy path: scenes extracted from prose, independent of any shot list.
        prompts = prompt_gen.generate_from_chapter(
            chapter,
            characters=characters or None,
            num_images=num_panels,
            visual_profiles=visual_profiles or None,
        )
    if not prompts:
        return []

    if shot_list is not None:
        _thread_shot_list(prompts, shot_list, settings, chapter)

    paths = image_gen.generate_story_images(
        prompts,
        chapter_number=getattr(chapter, "chapter_number", 0),
        character_references=character_references or None,
    )
    if not paths:
        return []

    if settings.compose_pages and shot_list is not None:
        paths = _compose(paths, shot_list, settings, image_gen, chapter) or paths
    return paths


def _thread_shot_list(prompts: list, shot_list, settings: ComicSettings, chapter):
    """Copy panel metadata onto the prompts, size them, and bake Codex bubbles."""
    try:
        from services.media.shot_list import apply_shot_list_to_prompts

        apply_shot_list_to_prompts(prompts, shot_list)
    except Exception as e:
        logger.warning(
            "Shot-list threading failed for ch %s, continuing without: %s",
            getattr(chapter, "chapter_number", "?"),
            e,
        )
        return

    if settings.compose_pages:
        # Generate each panel at the aspect of the page cell it will land in.
        # Square panels center-cropped into a 2.1:1 tier cell lose more than
        # half the drawing.
        try:
            from services.media.page_compositor import (
                PageGeometry,
                panel_target_sizes,
            )

            sizes = panel_target_sizes(
                shot_list,
                geometry=PageGeometry.from_canvas_spec(settings.canvas),
                layout_mode=settings.layout_mode,
            )
            for prompt, size in zip(prompts, sizes):
                prompt.target_size = size
        except Exception as e:
            logger.warning(
                "Panel sizing failed for ch %s, using square panels: %s",
                getattr(chapter, "chapter_number", "?"),
                e,
            )

    if settings.is_codex:
        try:
            from services.media.image_prompt_generator import (
                bake_dialogue_into_prompts,
            )

            bake_dialogue_into_prompts(prompts)
        except Exception as e:
            logger.warning("Codex dialogue baking failed: %s", e)


def _compose(
    panel_paths: list[str], shot_list, settings: ComicSettings, image_gen, chapter
) -> list[str]:
    """Composite loose panels into page PNGs; [] when it fails (caller degrades)."""
    try:
        from services.media.page_compositor import PageGeometry, compose_chapter

        return compose_chapter(
            shot_list,
            panel_paths,
            os.path.join(image_gen.output_dir, "pages"),
            chapter_number=getattr(chapter, "chapter_number", 0),
            geometry=PageGeometry.from_canvas_spec(settings.canvas),
            font_path=settings.font,
            layout_mode=settings.layout_mode,
        )
    except Exception as e:
        logger.warning(
            "Page compositor failed for ch %s, using loose panels: %s",
            getattr(chapter, "chapter_number", "?"),
            e,
        )
        return []
