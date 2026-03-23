"""Mô hình dữ liệu cho toàn bộ pipeline."""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# === Layer 1: Tạo truyện ===

class Character(BaseModel):
    """Nhân vật trong truyện."""
    name: str = Field(description="Tên nhân vật")
    role: str = Field(description="Vai trò: chính/phụ/phản diện")
    personality: str = Field(description="Tính cách")
    background: str = Field(description="Tiểu sử")
    motivation: str = Field(description="Động lực")
    appearance: str = Field(default="", description="Ngoại hình")
    relationships: list[str] = Field(default_factory=list, description="Mối quan hệ")


class WorldSetting(BaseModel):
    """Bối cảnh thế giới."""
    name: str = Field(description="Tên thế giới/bối cảnh")
    description: str = Field(description="Mô tả chi tiết")
    rules: list[str] = Field(default_factory=list, description="Quy tắc thế giới")
    locations: list[str] = Field(default_factory=list, description="Địa điểm chính")
    era: str = Field(default="", description="Thời đại")


class ChapterOutline(BaseModel):
    """Dàn ý 1 chương."""
    chapter_number: int
    title: str
    summary: str = Field(description="Tóm tắt nội dung")
    key_events: list[str] = Field(default_factory=list, description="Sự kiện chính")
    characters_involved: list[str] = Field(default_factory=list)
    emotional_arc: str = Field(default="", description="Cung bậc cảm xúc")


class Chapter(BaseModel):
    """Một chương truyện hoàn chỉnh."""
    chapter_number: int
    title: str
    content: str
    word_count: int = 0
    summary: str = ""


class CharacterState(BaseModel):
    """Trạng thái nhân vật thay đổi theo chương."""
    name: str
    mood: str = ""
    arc_position: str = ""  # e.g., "rising", "crisis", "resolution"
    knowledge: list[str] = Field(default_factory=list)
    relationship_changes: list[str] = Field(default_factory=list)
    last_action: str = ""


class PlotEvent(BaseModel):
    """Sự kiện quan trọng để theo dõi tính liên tục."""
    chapter_number: int
    event: str
    characters_involved: list[str] = Field(default_factory=list)


class StoryContext(BaseModel):
    """Rolling context cho việc viết chương."""
    recent_summaries: list[str] = Field(default_factory=list)
    character_states: list[CharacterState] = Field(default_factory=list)
    plot_events: list[PlotEvent] = Field(default_factory=list)
    total_chapters: int = 0
    current_chapter: int = 0


class StoryDraft(BaseModel):
    """Bản thảo truyện từ Layer 1."""
    title: str
    genre: str
    sub_genres: list[str] = Field(default_factory=list)
    synopsis: str = ""
    characters: list[Character] = Field(default_factory=list)
    world: Optional[WorldSetting] = None
    outlines: list[ChapterOutline] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)
    character_states: list[CharacterState] = Field(default_factory=list)
    plot_events: list[PlotEvent] = Field(default_factory=list)


# === Layer 2: Mô phỏng tăng kịch tính ===

class RelationType(str, Enum):
    ALLY = "đồng_minh"
    RIVAL = "đối_thủ"
    LOVER = "tình_nhân"
    MENTOR = "sư_phụ"
    ENEMY = "kẻ_thù"
    FAMILY = "gia_đình"
    BETRAYER = "phản_bội"
    UNKNOWN = "chưa_rõ"


class Relationship(BaseModel):
    """Mối quan hệ giữa 2 nhân vật."""
    character_a: str
    character_b: str
    relation_type: RelationType
    intensity: float = Field(default=0.5, ge=0, le=1, description="Cường độ 0-1")
    description: str = ""
    tension: float = Field(default=0.0, ge=0, le=1, description="Mức xung đột 0-1")


class SimulationEvent(BaseModel):
    """Sự kiện phát sinh từ mô phỏng."""
    round_number: int
    event_type: str = Field(description="Loại: xung_đột/liên_minh/phản_bội/tiết_lộ/đối_đầu")
    characters_involved: list[str]
    description: str
    drama_score: float = Field(ge=0, le=1, description="Độ kịch tính 0-1")
    suggested_insertion: str = Field(default="", description="Gợi ý chèn vào chương nào")


class AgentPost(BaseModel):
    """Bài viết/hành động của agent trong mô phỏng."""
    agent_name: str
    content: str
    action_type: str = Field(description="post/comment/reaction/confrontation")
    target: str = ""
    sentiment: str = ""
    round_number: int = 0


class SimulationResult(BaseModel):
    """Kết quả mô phỏng từ Layer 2."""
    events: list[SimulationEvent] = Field(default_factory=list)
    updated_relationships: list[Relationship] = Field(default_factory=list)
    drama_suggestions: list[str] = Field(default_factory=list)
    character_arcs: dict[str, str] = Field(default_factory=dict)
    tension_map: dict[str, float] = Field(default_factory=dict)
    agent_posts: list[AgentPost] = Field(default_factory=list)


class EnhancedStory(BaseModel):
    """Truyện đã được tăng cường kịch tính."""
    title: str
    genre: str
    chapters: list[Chapter] = Field(default_factory=list)
    enhancement_notes: list[str] = Field(default_factory=list)
    drama_score: float = Field(default=0.0, description="Điểm kịch tính tổng thể")


# === Layer 3: Video ===

class ShotType(str, Enum):
    WIDE = "toàn_cảnh"
    MEDIUM = "trung_cảnh"
    CLOSE_UP = "cận_cảnh"
    EXTREME_CLOSE_UP = "đặc_tả"
    OVER_SHOULDER = "qua_vai"
    POV = "góc_nhìn_nhân_vật"
    AERIAL = "từ_trên_cao"


class StoryboardPanel(BaseModel):
    """Một panel trong storyboard."""
    panel_number: int
    chapter_number: int
    shot_type: ShotType
    description: str = Field(description="Mô tả hình ảnh")
    camera_movement: str = Field(default="tĩnh", description="Di chuyển camera")
    dialogue: str = Field(default="", description="Lời thoại")
    narration: str = Field(default="", description="Lời kể")
    mood: str = Field(default="", description="Tâm trạng/không khí")
    characters_in_frame: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(default=5.0)
    image_prompt: str = Field(default="", description="Prompt tạo hình ảnh")
    sound_effect: str = Field(default="", description="Hiệu ứng âm thanh")


class VoiceLine(BaseModel):
    """Lời thoại cho voice-over."""
    character: str
    text: str
    emotion: str = ""
    panel_number: int = 0


class VideoScript(BaseModel):
    """Kịch bản video hoàn chỉnh."""
    title: str
    total_duration_seconds: float = 0
    panels: list[StoryboardPanel] = Field(default_factory=list)
    voice_lines: list[VoiceLine] = Field(default_factory=list)
    character_descriptions: dict[str, str] = Field(default_factory=dict)
    location_descriptions: dict[str, str] = Field(default_factory=dict)


# === Quality Metrics ===

class ChapterScore(BaseModel):
    """Quality score for a single chapter."""
    chapter_number: int
    coherence: float = Field(default=3.0, ge=1, le=5, description="Plot logic & flow")
    character_consistency: float = Field(default=3.0, ge=1, le=5, description="Character behavior consistency")
    drama: float = Field(default=3.0, ge=1, le=5, description="Tension & engagement")
    writing_quality: float = Field(default=3.0, ge=1, le=5, description="Prose quality & clarity")
    overall: float = Field(default=0.0, description="Computed average of 4 dimensions")
    notes: str = Field(default="", max_length=200, description="Brief strengths/weaknesses note")


class StoryScore(BaseModel):
    """Aggregate quality score for full story."""
    chapter_scores: list[ChapterScore] = Field(default_factory=list, description="Per-chapter scores")
    avg_coherence: float = Field(default=0.0, description="Mean coherence across chapters")
    avg_character: float = Field(default=0.0, description="Mean character consistency")
    avg_drama: float = Field(default=0.0, description="Mean drama/tension")
    avg_writing: float = Field(default=0.0, description="Mean writing quality")
    overall: float = Field(default=0.0, description="Computed average of 4 aggregates")
    weakest_chapter: int = Field(default=0, description="Chapter number with lowest overall")
    scoring_layer: int = Field(default=0, description="Which layer was scored (1 or 2)")


# === Agent Review ===

class AgentReview(BaseModel):
    """Kết quả đánh giá từ một agent."""
    agent_role: str
    agent_name: str
    score: float = Field(ge=0, le=1, description="Điểm chất lượng 0-1")
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    approved: bool = True
    refined_content: Optional[str] = None
    layer: int = 0
    iteration: int = 0


# === Pipeline Output ===

class PipelineOutput(BaseModel):
    """Kết quả cuối cùng của toàn bộ pipeline."""
    story_draft: Optional[StoryDraft] = None
    simulation_result: Optional[SimulationResult] = None
    enhanced_story: Optional[EnhancedStory] = None
    video_script: Optional[VideoScript] = None
    status: str = "pending"
    current_layer: int = 0
    progress: float = 0.0
    logs: list[str] = Field(default_factory=list)
    reviews: list[AgentReview] = Field(default_factory=list)
    quality_scores: list[StoryScore] = Field(default_factory=list)
