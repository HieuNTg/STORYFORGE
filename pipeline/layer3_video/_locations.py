"""Tạo image prompt cho địa điểm trong storyboard."""

import logging
from models.schemas import StoryboardPanel
from services.llm_client import LLMClient
from services import prompts

logger = logging.getLogger(__name__)


def generate_location_prompts(
    llm: LLMClient,
    panels: list[StoryboardPanel],
    world_locations: list[str],
    genre: str,
) -> dict[str, str]:
    """Tạo image prompt cho các địa điểm xuất hiện trong storyboard.

    Trích xuất địa điểm duy nhất từ panels + world settings,
    sau đó dùng LOCATION_IMAGE_PROMPT để tạo prompt.
    """
    # Gom địa điểm từ description của panels
    location_set: set[str] = set()
    for p in panels:
        if p.description:
            loc_key = p.description[:60].split(".")[0].strip()
            if loc_key:
                location_set.add(loc_key)

    # Thêm địa điểm từ world settings
    for loc in world_locations:
        location_set.add(loc)

    # Giới hạn số lượng để tránh quá nhiều API calls
    locations = list(location_set)[:10]

    location_prompts: dict[str, str] = {}
    for loc in locations:
        try:
            result = llm.generate_json(
                system_prompt="Bạn là artist director. Trả về JSON.",
                user_prompt=prompts.LOCATION_IMAGE_PROMPT.format(
                    location=loc,
                    genre=genre,
                    mood="phù hợp với thể loại truyện",
                ),
            )
            location_prompts[loc] = result.get("image_prompt", "")
        except Exception as e:
            logger.warning(f"Lỗi tạo prompt cho địa điểm '{loc[:30]}': {e}")

    return location_prompts
