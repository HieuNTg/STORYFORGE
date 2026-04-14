"""Setting Continuity Graph — theo dõi bối cảnh, địa điểm, timeline xuyên chương.

Tracks: locations, objects, time_markers, spatial relationships.
Prevents: teleportation errors, object duplication, timeline contradictions.
"""

import logging
from pydantic import BaseModel, Field
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class Location(BaseModel):
    """Một địa điểm trong truyện."""
    name: str
    description: str = ""
    introduced_chapter: int = 0
    accessible_from: list[str] = Field(default_factory=list)
    contains_objects: list[str] = Field(default_factory=list)
    characters_present: list[str] = Field(default_factory=list)


class SignificantObject(BaseModel):
    """Vật phẩm quan trọng trong truyện."""
    name: str
    description: str = ""
    introduced_chapter: int = 0
    current_location: str = ""
    current_owner: str = ""
    destroyed: bool = False
    destroyed_chapter: int = 0


class TimeMarker(BaseModel):
    """Mốc thời gian trong truyện."""
    chapter_number: int
    description: str = ""  # "sáng hôm sau", "3 ngày sau", "mùa đông năm đó"
    relative_to: str = ""  # reference to another marker
    absolute_time: str = ""  # if specified


class SettingContinuityGraph:
    """Đồ thị liên tục bối cảnh — theo dõi locations, objects, timeline."""

    EXTRACT_SETTINGS_PROMPT = """Phân tích nội dung chương và trích xuất thông tin bối cảnh.

Chương {chapter_number}:
{content}

Trả về JSON:
{{
  "locations": [
    {{"name": "tên địa điểm", "description": "mô tả ngắn", "accessible_from": ["địa điểm có thể đến từ đây"]}}
  ],
  "objects": [
    {{"name": "tên vật phẩm", "description": "mô tả", "location": "ở đâu", "owner": "ai đang giữ"}}
  ],
  "time_markers": [
    {{"description": "mốc thời gian", "relative_to": "so với mốc nào"}}
  ],
  "characters_at_locations": {{
    "tên_địa_điểm": ["nhân vật 1", "nhân vật 2"]
  }}
}}

Chỉ ghi nhận thông tin rõ ràng trong văn bản."""

    def __init__(self):
        self.locations: dict[str, Location] = {}
        self.objects: dict[str, SignificantObject] = {}
        self.time_markers: list[TimeMarker] = []
        self.chapter_locations: dict[int, list[str]] = {}  # chapter -> locations mentioned
        self.llm = LLMClient()

    def extract_from_chapter(
        self,
        chapter_content: str,
        chapter_number: int,
    ) -> dict:
        """Trích xuất bối cảnh từ một chương."""
        content_truncated = chapter_content[:5000]

        try:
            result = self.llm.generate_json(
                system_prompt="Trích xuất thông tin bối cảnh truyện. Trả về JSON.",
                user_prompt=self.EXTRACT_SETTINGS_PROMPT.format(
                    chapter_number=chapter_number,
                    content=content_truncated,
                ),
                temperature=0.1,
                max_tokens=800,
                model_tier="cheap",
            )

            # Process locations
            for loc_data in result.get("locations", []):
                loc_name = loc_data.get("name", "").strip()
                if not loc_name:
                    continue

                if loc_name not in self.locations:
                    self.locations[loc_name] = Location(
                        name=loc_name,
                        description=loc_data.get("description", ""),
                        introduced_chapter=chapter_number,
                        accessible_from=loc_data.get("accessible_from", []),
                    )
                else:
                    # Update accessibility
                    existing = self.locations[loc_name]
                    for acc in loc_data.get("accessible_from", []):
                        if acc not in existing.accessible_from:
                            existing.accessible_from.append(acc)

            # Process objects
            for obj_data in result.get("objects", []):
                obj_name = obj_data.get("name", "").strip()
                if not obj_name:
                    continue

                if obj_name not in self.objects:
                    self.objects[obj_name] = SignificantObject(
                        name=obj_name,
                        description=obj_data.get("description", ""),
                        introduced_chapter=chapter_number,
                        current_location=obj_data.get("location", ""),
                        current_owner=obj_data.get("owner", ""),
                    )
                else:
                    # Update location/owner
                    existing = self.objects[obj_name]
                    if obj_data.get("location"):
                        existing.current_location = obj_data["location"]
                    if obj_data.get("owner"):
                        existing.current_owner = obj_data["owner"]

            # Process time markers
            for tm_data in result.get("time_markers", []):
                desc = tm_data.get("description", "").strip()
                if desc:
                    self.time_markers.append(TimeMarker(
                        chapter_number=chapter_number,
                        description=desc,
                        relative_to=tm_data.get("relative_to", ""),
                    ))

            # Track which locations appear in which chapter
            chapter_locs = list(result.get("characters_at_locations", {}).keys())
            self.chapter_locations[chapter_number] = chapter_locs

            # Update character presence
            for loc_name, chars in result.get("characters_at_locations", {}).items():
                if loc_name in self.locations:
                    self.locations[loc_name].characters_present = chars

            logger.debug(
                f"SettingGraph ch{chapter_number}: "
                f"{len(self.locations)} locs, {len(self.objects)} objs"
            )
            return result

        except Exception as e:
            logger.warning(f"Setting extraction failed for ch{chapter_number}: {e}")
            return {}

    def build_from_draft(self, draft, progress_callback=None) -> "SettingContinuityGraph":
        """Xây dựng graph từ toàn bộ draft."""
        chapters = getattr(draft, "chapters", []) or []

        for ch in chapters:
            content = getattr(ch, "content", "") or ""
            ch_num = getattr(ch, "chapter_number", 0)
            if content and ch_num:
                self.extract_from_chapter(content, ch_num)
                if progress_callback:
                    progress_callback(f"[SettingGraph] Processed ch{ch_num}")

        # Build bidirectional accessibility
        self._build_accessibility_graph()

        logger.info(
            f"SettingContinuityGraph: {len(self.locations)} locations, "
            f"{len(self.objects)} objects, {len(self.time_markers)} time markers"
        )
        return self

    def _build_accessibility_graph(self):
        """Ensure accessibility is bidirectional."""
        for loc_name, loc in self.locations.items():
            for accessible in loc.accessible_from:
                if accessible in self.locations:
                    target = self.locations[accessible]
                    if loc_name not in target.accessible_from:
                        target.accessible_from.append(loc_name)

    def get_accessible_locations(self, from_location: str) -> list[str]:
        """Lấy danh sách địa điểm có thể đến từ vị trí hiện tại."""
        if from_location not in self.locations:
            return list(self.locations.keys())  # Unknown location = can go anywhere
        return self.locations[from_location].accessible_from

    def is_transition_valid(self, from_loc: str, to_loc: str) -> bool:
        """Kiểm tra có thể di chuyển từ A đến B không."""
        if not from_loc or not to_loc:
            return True  # Unknown = assume valid
        if from_loc not in self.locations:
            return True
        return to_loc in self.locations[from_loc].accessible_from or to_loc == from_loc

    def format_constraints_for_chapter(self, chapter_number: int) -> str:
        """Tạo text ràng buộc bối cảnh cho enhance prompt."""
        lines = []

        # Recent locations
        recent_locs = []
        for ch in range(max(1, chapter_number - 3), chapter_number):
            recent_locs.extend(self.chapter_locations.get(ch, []))
        recent_locs = list(set(recent_locs))[:5]

        if recent_locs:
            lines.append("**Địa điểm gần đây:**")
            for loc_name in recent_locs:
                loc = self.locations.get(loc_name)
                if loc:
                    access = ", ".join(loc.accessible_from[:3]) if loc.accessible_from else "không rõ"
                    lines.append(f"  - {loc_name}: có thể đến → {access}")

        # Active objects
        active_objs = [
            obj for obj in self.objects.values()
            if not obj.destroyed and (obj.current_owner or obj.current_location)
        ]
        if active_objs:
            lines.append("**Vật phẩm quan trọng:**")
            for obj in active_objs[:5]:
                holder = obj.current_owner or obj.current_location or "không rõ"
                lines.append(f"  - {obj.name}: đang ở/thuộc {holder}")

        # Timeline context
        recent_times = [tm for tm in self.time_markers if tm.chapter_number >= chapter_number - 2]
        if recent_times:
            lines.append("**Mốc thời gian:**")
            for tm in recent_times[-3:]:
                lines.append(f"  - Ch{tm.chapter_number}: {tm.description}")

        if not lines:
            return ""

        return "## Bối cảnh liên tục\n" + "\n".join(lines)

    def validate_enhanced_chapter(
        self,
        enhanced_content: str,
        chapter_number: int,
        prev_locations: dict[str, str],  # character -> last known location
    ) -> list[dict]:
        """Kiểm tra enhanced content có vi phạm bối cảnh không."""
        violations = []

        try:
            result = self.llm.generate_json(
                system_prompt="Phân tích di chuyển và vật phẩm trong chương. Trả về JSON.",
                user_prompt=f"""Nội dung chương:
{enhanced_content[:4000]}

Trả về:
{{
  "movements": [
    {{"character": "tên", "from": "địa điểm A", "to": "địa điểm B"}}
  ],
  "object_changes": [
    {{"object": "tên", "action": "acquired/lost/destroyed", "by": "nhân vật"}}
  ]
}}""",
                temperature=0.1,
                max_tokens=400,
                model_tier="cheap",
            )

            # Check movement validity
            for mov in result.get("movements", []):
                from_loc = mov.get("from", "")
                to_loc = mov.get("to", "")
                char = mov.get("character", "")

                if not self.is_transition_valid(from_loc, to_loc):
                    violations.append({
                        "type": "invalid_transition",
                        "character": char,
                        "chapter": chapter_number,
                        "description": f"{char} di chuyển từ '{from_loc}' đến '{to_loc}' nhưng không có đường đi",
                        "severity": "warning",
                    })

            # Check object consistency
            for obj_change in result.get("object_changes", []):
                obj_name = obj_change.get("object", "")
                action = obj_change.get("action", "")

                if obj_name in self.objects:
                    obj = self.objects[obj_name]
                    if obj.destroyed and action != "destroyed":
                        violations.append({
                            "type": "object_continuity",
                            "object": obj_name,
                            "chapter": chapter_number,
                            "description": f"Vật phẩm '{obj_name}' đã bị phá hủy ở ch{obj.destroyed_chapter} nhưng xuất hiện lại",
                            "severity": "critical",
                        })

        except Exception as e:
            logger.debug(f"Setting validation failed for ch{chapter_number}: {e}")

        return violations

    def mark_object_destroyed(self, obj_name: str, chapter_number: int):
        """Đánh dấu vật phẩm đã bị phá hủy."""
        if obj_name in self.objects:
            self.objects[obj_name].destroyed = True
            self.objects[obj_name].destroyed_chapter = chapter_number
