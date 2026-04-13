"""Mô hình dữ liệu cho toàn bộ pipeline."""

import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from enum import Enum


def count_words(text: str) -> int:
    """Count words accurately — filters out standalone punctuation tokens."""
    return len([w for w in text.split() if re.search(r'\w', w)])


# === Layer 1: Tạo truyện ===

class Character(BaseModel):
    """Nhân vật trong truyện."""
    name: str = Field(description="Tên nhân vật")
    role: str = Field(description="Vai trò: chính/phụ/phản diện")
    personality: str = Field(description="Tính cách")
    background: str = Field(default="", description="Tiểu sử")
    motivation: str = Field(default="", description="Động lực")
    appearance: str = Field(default="", description="Ngoại hình")
    relationships: list[str] = Field(default_factory=list, description="Mối quan hệ")
    reference_image: str = Field(default="", description="Ảnh tham chiếu nhân vật")
    arc_trajectory: str = Field(default="", description="Character transformation arc, e.g. 'từ hèn nhát → can đảm'")
    internal_conflict: str = Field(default="", description="Core internal conflict driving character")
    breaking_point: str = Field(default="", description="Event that triggers character transformation")
    secret: str = Field(default="", description="Hidden information that shifts dynamics when revealed")
    speech_pattern: str = Field(default="", description="Distinctive speech style: formal/slang/archaic/etc")
    arc_waypoints: list[dict] = Field(default_factory=list, description="Structured arc stages — each dict is an ArcWaypoint")

    @field_validator("relationships", mode="before")
    @classmethod
    def _coerce_relationships(cls, v):
        """LLM sometimes returns a string instead of list — coerce robustly."""
        if isinstance(v, str):
            if not v.strip():
                return []
            if "\n" in v:
                lines = [ln.strip().lstrip("-•*0123456789.) ") for ln in v.splitlines()]
                return [ln for ln in lines if ln]
            if "," in v:
                return [s.strip() for s in v.split(",") if s.strip()]
            return [v.strip()]
        if v is None:
            return []
        return v


class WorldSetting(BaseModel):
    """Bối cảnh thế giới."""
    name: str = Field(description="Tên thế giới/bối cảnh")
    description: str = Field(description="Mô tả chi tiết")
    rules: list[str] = Field(default_factory=list, description="Quy tắc thế giới")
    locations: list[str] = Field(default_factory=list, description="Địa điểm chính")
    era: str = Field(default="", description="Thời đại")


class StructuredSummary(BaseModel):
    """Rich chapter summary for better context tracking."""
    plot_critical_events: list[str] = Field(default_factory=list, description="Events that affect future chapters")
    character_developments: list[str] = Field(default_factory=list, description="Character growth moments")
    open_questions: list[str] = Field(default_factory=list, description="Questions reader will have")
    emotional_shift: str = Field(default="", description="How emotional tone changed")
    threads_advanced: list[str] = Field(default_factory=list, description="Thread IDs that progressed")
    threads_opened: list[str] = Field(default_factory=list, description="New thread IDs introduced")
    threads_resolved: list[str] = Field(default_factory=list, description="Thread IDs resolved")
    chapter_ending_hook: str = Field(default="", description="Cliffhanger hoặc khoảnh khắc chưa giải quyết cuối chương")
    actual_emotional_arc: str = Field(default="", description="Cung bậc cảm xúc thực sự trong chương")


class ChapterOutline(BaseModel):
    """Dàn ý 1 chương."""
    chapter_number: int
    title: str
    summary: str = Field(description="Tóm tắt nội dung")
    key_events: list[str] = Field(default_factory=list, description="Sự kiện chính")
    characters_involved: list[str] = Field(default_factory=list)
    emotional_arc: str = Field(default="", description="Cung bậc cảm xúc")
    pacing_type: str = Field(default="rising", description="Pacing: setup/rising/climax/cooldown/twist")
    foreshadowing_plants: list[str] = Field(default_factory=list, description="Seeds to plant for future payoff")
    payoff_references: list[str] = Field(default_factory=list, description="Earlier foreshadowing to pay off in this chapter")
    arc_id: int = Field(default=0, description="Which macro arc this chapter belongs to")


class Chapter(BaseModel):
    """Một chương truyện hoàn chỉnh."""
    chapter_number: int
    title: str
    content: str
    word_count: int = 0
    summary: str = ""
    structured_summary: Optional[StructuredSummary] = Field(default=None, description="Rich structured summary")
    enhancement_changelog: list[str] = Field(default_factory=list, description="Log các thay đổi trong quá trình tăng cường kịch tính")
    contract: Optional["ChapterContract"] = Field(default=None, description="L1-generated per-chapter requirements contract")


class CharacterState(BaseModel):
    """Trạng thái nhân vật thay đổi theo chương."""
    name: str
    mood: str = ""
    arc_position: str = ""  # e.g., "rising", "crisis", "resolution"
    knowledge: list[str] = Field(default_factory=list)
    relationship_changes: list[str] = Field(default_factory=list)
    last_action: str = ""
    cumulative_knowledge: list[str] = Field(default_factory=list)
    cumulative_relationships: list[str] = Field(default_factory=list)


class PlotEvent(BaseModel):
    """Sự kiện quan trọng để theo dõi tính liên tục."""
    chapter_number: int
    event: str
    characters_involved: list[str] = Field(default_factory=list)
    critical: bool = Field(default=False, description="If True, this event is never pruned from context")


class PlotThread(BaseModel):
    """Tracks an open narrative thread across chapters."""
    thread_id: str = Field(description="Unique thread identifier")
    description: str = Field(description="What this thread is about")
    planted_chapter: int = Field(description="Chapter where thread was introduced")
    status: str = Field(default="open", description="open/progressing/resolved")
    involved_characters: list[str] = Field(default_factory=list)
    last_mentioned_chapter: int = Field(default=0)
    resolution_chapter: int = Field(default=0)
    depends_on: list[str] = Field(default_factory=list, description="Thread IDs that must resolve before this one")
    blocks: list[str] = Field(default_factory=list, description="Thread IDs this thread blocks")
    urgency: int = Field(default=3, ge=1, le=5, description="1=background, 5=must-resolve-soon")


class ConflictEntry(BaseModel):
    """A conflict between characters or internal conflict."""
    conflict_id: str = Field(description="Unique conflict identifier")
    conflict_type: str = Field(description="external/internal/ideological")
    characters: list[str] = Field(description="Characters involved")
    description: str = Field(description="Nature of conflict")
    arc_range: str = Field(default="", description="Arc range where active, e.g. '1-3'")
    trigger_event: str = Field(default="", description="Event that activates this conflict")
    status: str = Field(default="dormant", description="dormant/active/escalating/resolved")
    intensity: int = Field(default=1, ge=1, le=5, description="Current conflict intensity 1-5")
    escalation_timeline: list[dict] = Field(default_factory=list, description="[{chapter: int, intensity: int}]")


class MacroArc(BaseModel):
    """High-level story arc spanning multiple chapters."""
    arc_number: int = Field(description="Arc sequence number")
    name: str = Field(description="Arc name")
    chapter_start: int = Field(description="First chapter")
    chapter_end: int = Field(description="Last chapter")
    central_conflict: str = Field(description="Main conflict of this arc")
    character_focus: list[str] = Field(default_factory=list, description="Key characters in this arc")
    resolution: str = Field(default="", description="How arc resolves")
    emotional_trajectory: str = Field(default="", description="Overall emotional arc")


class ForeshadowingEntry(BaseModel):
    """A foreshadowing seed and its planned payoff."""
    hint: str = Field(description="The subtle hint/seed")
    plant_chapter: int = Field(description="Chapter to plant the seed")
    payoff_chapter: int = Field(description="Chapter where payoff happens")
    characters_involved: list[str] = Field(default_factory=list)
    planted: bool = Field(default=False, description="Whether seed has been written")
    paid_off: bool = Field(default=False, description="Whether payoff has been written")
    planted_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Semantic confidence that seed was planted")


class StoryArc(BaseModel):
    """Một arc trong truyện dài."""
    arc_number: int = 0
    title: str = ""
    summary: str = ""
    start_chapter: int = 0
    end_chapter: int = 0
    key_events: list[str] = Field(default_factory=list)
    status: str = "active"  # active/completed


class StoryBible(BaseModel):
    """Memory dài hạn cho truyện 100+ chương."""
    premise: str = ""
    world_rules: list[str] = Field(default_factory=list)
    active_threads: list[PlotThread] = Field(default_factory=list)
    resolved_threads: list[PlotThread] = Field(default_factory=list)
    arcs: list[StoryArc] = Field(default_factory=list)
    milestone_events: list[str] = Field(default_factory=list)
    arc_summaries: list[str] = Field(default_factory=list)
    timeline_positions: dict[str, str] = Field(default_factory=dict, description="Mốc thời gian per POV {tên nhân vật: mốc thời gian}")
    character_locations: dict[str, str] = Field(default_factory=dict, description="Vị trí nhân vật {tên: địa điểm}")


class StoryContext(BaseModel):
    """Rolling context cho việc viết chương."""
    recent_summaries: list[str] = Field(default_factory=list)
    character_states: list[CharacterState] = Field(default_factory=list)
    plot_events: list[PlotEvent] = Field(default_factory=list)
    total_chapters: int = 0
    current_chapter: int = 0
    open_threads: list[PlotThread] = Field(default_factory=list, description="Active narrative threads")
    conflict_map: list[ConflictEntry] = Field(default_factory=list, description="Active conflicts")
    current_arc: int = Field(default=1, description="Current macro arc number")
    pacing_history: list[str] = Field(default_factory=list, description="Recent pacing types for rhythm tracking")
    world_state_changes: list[str] = Field(default_factory=list, description="Permanent world changes (cities burned, rulers dead, etc.)")
    timeline_positions: dict[str, str] = Field(default_factory=dict, description="Mốc thời gian per POV {tên nhân vật/narrator: mốc thời gian}")
    character_locations: dict[str, str] = Field(default_factory=dict, description="Vị trí hiện tại {tên nhân vật: địa điểm}")
    arc_drift_warnings: list[str] = Field(default_factory=list, description="Cảnh báo trượt arc nhân vật")
    name_warnings: list[str] = Field(default_factory=list, description="Cảnh báo tên nhân vật không nhất quán")
    stale_thread_warnings: list[str] = Field(default_factory=list, description="Cảnh báo tuyến truyện bị bỏ quên")
    chapter_ending_hook: str = Field(default="", description="Hook từ chương trước để tiếp nối")
    emotional_history: list[str] = Field(default_factory=list, description="Lịch sử cảm xúc per chapter")
    world_rule_violations: list[str] = Field(default_factory=list, description="Vi phạm quy tắc thế giới phát hiện trong chương")
    dialogue_voice_warnings: list[str] = Field(default_factory=list, description="Cảnh báo giọng nói nhân vật không nhất quán")
    pacing_adjustment: str = Field(default="", description="Pacing correction directive for next chapter")


class StoryDraft(BaseModel):
    """Bản thảo truyện từ Layer 1."""
    title: str
    genre: str
    sub_genres: list[str] = Field(default_factory=list)
    synopsis: str = ""
    premise: dict = Field(default_factory=dict, description="Thematic premise anchor from theme_premise_generator")
    voice_profiles: list[dict] = Field(default_factory=list, description="Character voice profiles for distinct dialogue")
    characters: list[Character] = Field(default_factory=list)
    world: Optional[WorldSetting] = None
    outlines: list[ChapterOutline] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)
    character_states: list[CharacterState] = Field(default_factory=list)
    plot_events: list[PlotEvent] = Field(default_factory=list)
    story_bible: Optional[StoryBible] = None
    macro_arcs: list[MacroArc] = Field(default_factory=list, description="High-level story arcs")
    conflict_web: list[ConflictEntry] = Field(default_factory=list, description="All planned conflicts")
    foreshadowing_plan: list[ForeshadowingEntry] = Field(default_factory=list, description="Planned foreshadowing")
    open_threads: list[PlotThread] = Field(default_factory=list, description="Active narrative threads carried across chapters")


# === Layer 2: Mô phỏng tăng kịch tính ===

# --- Psychology Engine schemas ---

class GoalHierarchy(BaseModel):
    primary_goal: str = ""
    hidden_motive: str = ""
    fear: str = ""
    shame_trigger: str = ""


class VulnerabilityEntry(BaseModel):
    wound: str = ""
    exploiters: list[str] = Field(default_factory=list)
    drama_multiplier: float = Field(default=1.5, ge=1.0, le=3.0)


class CharacterPsychology(BaseModel):
    character_name: str = ""
    goals: GoalHierarchy = Field(default_factory=GoalHierarchy)
    vulnerabilities: list[VulnerabilityEntry] = Field(default_factory=list)
    pressure: float = Field(default=0.0, ge=0, le=1)
    defenses: list[str] = Field(default_factory=list)


# --- Simulation schemas ---

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
    cause_event_id: str = Field(default="", description="ID of event that caused this one")
    consequences: list[str] = Field(default_factory=list, description="What this event caused")


class AgentPost(BaseModel):
    """Bài viết/hành động của agent trong mô phỏng."""
    agent_name: str
    content: str
    action_type: str = Field(description="post/comment/reaction/confrontation")
    target: str = ""
    sentiment: str = ""
    round_number: int = 0
    importance_score: float = Field(default=0.5, ge=0, le=1, description="Điểm quan trọng để lọc bộ nhớ agent thông minh")


class SimulationResult(BaseModel):
    """Kết quả mô phỏng từ Layer 2."""
    events: list[SimulationEvent] = Field(default_factory=list)
    updated_relationships: list[Relationship] = Field(default_factory=list)
    drama_suggestions: list[str] = Field(default_factory=list)
    character_arcs: dict[str, str] = Field(default_factory=dict)
    tension_map: dict[str, float] = Field(default_factory=dict)
    agent_posts: list[AgentPost] = Field(default_factory=list)
    emotional_trajectories: dict[str, list[str]] = Field(default_factory=dict, description="Chuỗi trạng thái cảm xúc theo vòng mô phỏng: tên_nhân_vật → [mood_round1, mood_round2, ...]")
    knowledge_state: dict[str, list[str]] = Field(default_factory=dict, description="Per-character knowledge at end of simulation")
    causal_chains: list[list[str]] = Field(default_factory=list, description="Top causal chains as event_id lists")
    actual_rounds: int = Field(default=0, description="Actual rounds run (may differ from requested)")


class EnhancedStory(BaseModel):
    """Truyện đã được tăng cường kịch tính."""
    title: str
    genre: str
    chapters: list[Chapter] = Field(default_factory=list)
    enhancement_notes: list[str] = Field(default_factory=list)
    drama_score: float = Field(default=0.0, description="Điểm kịch tính tổng thể")
    coherence_issues: list[str] = Field(default_factory=list, description="Danh sách vấn đề nhất quán phát hiện sau khi tăng cường")


# === Quality Metrics ===

class ChapterScore(BaseModel):
    """Quality score for a single chapter."""
    chapter_number: int
    coherence: float = Field(default=3.0, ge=1, le=5, description="Plot logic & flow")
    character_consistency: float = Field(default=3.0, ge=1, le=5, description="Character behavior consistency")
    drama: float = Field(default=3.0, ge=1, le=5, description="Tension & engagement")
    writing_quality: float = Field(default=3.0, ge=1, le=5, description="Prose quality & clarity")
    thematic_alignment: float = Field(default=0.0, ge=0, le=5, description="Theme reinforcement score")
    dialogue_depth: float = Field(default=0.0, ge=0, le=5, description="Dialogue subtext depth score")
    overall: float = Field(default=0.0, description="Computed average of 4 dimensions")
    notes: str = Field(default="", max_length=1000, description="Brief strengths/weaknesses note")


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


# === Features: Drama, Image Gen, User, Share ===

class EscalationPattern(BaseModel):
    """Drama escalation pattern for Layer 2."""
    pattern_type: str = Field(description="betrayal/revelation/confrontation/sacrifice/reversal")
    trigger_tension: float = Field(default=0.6, ge=0, le=1, description="Min tension to trigger")
    characters_required: int = Field(default=2, ge=1)
    description: str = ""
    intensity_multiplier: float = Field(default=1.5, ge=1.0, le=3.0)


class ImagePrompt(BaseModel):
    """AI image generation prompt from story content."""
    panel_number: int = 0
    chapter_number: int = 0
    scene_description: str = ""
    style: str = Field(default="cinematic", description="cinematic/anime/watercolor/realistic")
    dalle_prompt: str = ""
    sd_prompt: str = ""
    negative_prompt: str = ""
    characters_in_scene: list[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    """Simple user profile for story library."""
    user_id: str
    username: str
    password_hash: str = ""
    created_at: str = ""
    story_ids: list[str] = Field(default_factory=list)
    usage_count: int = 0
    credits: int = 20  # Free tier: 20 credits
    tier: str = "free"  # free/pro/studio
    total_stories_created: int = 0


class ReadingStats(BaseModel):
    """Reading statistics for a story."""
    total_words: int = 0
    total_chapters: int = 0
    estimated_reading_minutes: int = 0
    avg_words_per_chapter: int = 0


class ShareableStory(BaseModel):
    """Story share metadata."""
    share_id: str
    story_title: str
    created_at: str = ""
    html_path: str = ""
    expires_at: str = ""
    is_public: bool = False


# === Story Branching ===

class BranchChoice(BaseModel):
    """A decision point choice."""
    choice_id: str = Field(description="Unique choice identifier")
    text: str = Field(description="Choice text shown to user")
    next_node_id: str = Field(default="", description="ID of next story node")
    state_delta: dict = Field(default_factory=dict, description="Character state changes")


class StoryNode(BaseModel):
    """A node in the branching story tree."""
    node_id: str = Field(description="Unique node identifier")
    chapter_number: int = 0
    title: str = ""
    content: str = ""
    choices: list[BranchChoice] = Field(default_factory=list)
    parent_id: str = Field(default="", description="Parent node ID")
    is_ending: bool = False


class StoryTree(BaseModel):
    """Complete branching story structure (DAG)."""
    root_id: str = "root"
    nodes: dict[str, StoryNode] = Field(default_factory=dict)
    current_node_id: str = "root"
    title: str = ""
    genre: str = ""


# === Agent Debate ===

class DebateStance(str, Enum):
    CHALLENGE = "challenge"
    SUPPORT = "support"
    NEUTRAL = "neutral"


class DebateEntry(BaseModel):
    """Single entry in a debate round."""
    agent_name: str
    round_number: int = 1
    stance: DebateStance = DebateStance.NEUTRAL
    target_agent: str = ""
    target_issue: str = ""
    reasoning: str = ""
    revised_score: Optional[float] = None


class DebateResult(BaseModel):
    """Full debate outcome across all rounds."""
    rounds: list[list[DebateEntry]] = Field(default_factory=list)
    final_reviews: list[AgentReview] = Field(default_factory=list)
    consensus_score: float = 0.0
    total_challenges: int = 0
    debate_skipped: bool = False


# === Pipeline Output ===

class PipelineOutput(BaseModel):
    """Kết quả cuối cùng của toàn bộ pipeline."""
    story_draft: Optional[StoryDraft] = None
    simulation_result: Optional[SimulationResult] = None
    enhanced_story: Optional[EnhancedStory] = None
    status: str = "pending"
    current_layer: int = 0
    progress: float = 0.0
    logs: list[str] = Field(default_factory=list)
    reviews: list[AgentReview] = Field(default_factory=list)
    quality_scores: list[StoryScore] = Field(default_factory=list)
    analytics: dict = Field(default_factory=dict)
    knowledge_graph_summary: str = ""
    progress_events: list = Field(default_factory=list)


try:
    from models.narrative_schemas import ChapterContract
    Chapter.model_rebuild(_types_namespace={"ChapterContract": ChapterContract})
except Exception:
    pass
