"""Tạo image prompt cho địa điểm trong storyboard."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from models.schemas import StoryboardPanel
from services.llm_client import LLMClient
from services import prompts
from config import ConfigManager

logger = logging.getLogger(__name__)


def _generate_single_location(llm: LLMClient, loc: str, genre: str) -> tuple[str, str]:
    """Tạo prompt cho 1 địa điểm. Returns (location, prompt)."""
    result = llm.generate_json(
        system_prompt="Bạn là artist director. Trả về JSON.",
        user_prompt=prompts.LOCATION_IMAGE_PROMPT.format(
            location=loc,
            genre=genre,
            mood="phù hợp với thể loại truyện",
        ),
    )
    return loc, result.get("image_prompt", "")


def generate_location_prompts(
    llm: LLMClient,
    panels: list[StoryboardPanel],
    world_locations: list[str],
    genre: str,
) -> dict[str, str]:
    """Tạo image prompt cho các địa điểm (parallel)."""
    location_set: set[str] = set()
    for p in panels:
        if p.description:
            loc_key = p.description[:60].split(".")[0].strip()
            if loc_key:
                location_set.add(loc_key)

    for loc in world_locations:
        location_set.add(loc)

    locations = list(location_set)[:10]
    max_workers = ConfigManager().llm.max_parallel_workers

    location_prompts: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_generate_single_location, llm, loc, genre): loc
            for loc in locations
        }
        for future in as_completed(futures):
            loc = futures[future]
            try:
                _, prompt = future.result()
                location_prompts[loc] = prompt
            except Exception as e:
                logger.warning(f"Lỗi tạo prompt cho địa điểm '{loc[:30]}': {e}")

    return location_prompts
