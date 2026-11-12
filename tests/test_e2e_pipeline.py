"""E2E pipeline tests — full pipeline flow with mocked LLM."""

import json
import pytest
from unittest.mock import patch

# ── Mock response data ────────────────────────────────────────────────────────

MOCK_CHARACTERS = {
    "characters": [
        {
            "name": "Minh",
            "role": "chính",
            "personality": "Dũng cảm, thông minh",
            "background": "Thanh niên từ làng nhỏ",
            "motivation": "Tìm kiếm sức mạnh",
            "appearance": "Cao ráo, mắt sáng",
            "relationships": ["Lan: bạn thân", "Hùng: kẻ thù"],
        },
        {
            "name": "Lan",
            "role": "chính",
            "personality": "Xinh đẹp, mưu trí",
            "background": "Con gái trưởng lão",
            "motivation": "Bảo vệ gia tộc",
            "appearance": "Tóc dài, áo trắng",
            "relationships": ["Minh: bạn thân"],
        },
        {
            "name": "Hùng",
            "role": "phản diện",
            "personality": "Tàn nhẫn, mưu mô",
            "background": "Đệ tử bị trục xuất",
            "motivation": "Trả thù",
            "appearance": "Sẹo trên mặt",
            "relationships": ["Minh: kẻ thù"],
        },
    ]
}

MOCK_WORLD = {
    "name": "Thiên Linh Giới",
    "description": "Thế giới tu tiên với 5 tông phái lớn",
    "rules": ["Tu luyện chia 9 cảnh giới", "Linh khí là nguồn sức mạnh"],
    "locations": ["Thanh Vân Tông", "Hắc Ám Lâm"],
    "era": "Thượng cổ",
}

MOCK_OUTLINE = {
    "synopsis": "Câu chuyện về Minh trong hành trình tu tiên đầy gian khổ.",
    "outlines": [
        {
            "chapter_number": 1,
            "title": "Khởi Đầu",
            "summary": "Minh bắt đầu hành trình tu tiên.",
            "key_events": ["Minh gia nhập tông phái", "Gặp Lan lần đầu"],
            "characters_involved": ["Minh", "Lan"],
            "emotional_arc": "Hứng khởi và lo lắng",
        },
        {
            "chapter_number": 2,
            "title": "Thử Thách",
            "summary": "Minh đối mặt với kẻ thù đầu tiên.",
            "key_events": ["Hùng xuất hiện", "Trận chiến đầu tiên"],
            "characters_involved": ["Minh", "Hùng"],
            "emotional_arc": "Căng thẳng và quyết tâm",
        },
    ],
}

MOCK_CHAPTER_TEXT = (
    "Minh bước vào tông phái với ánh mắt kiên định. "
    "Xung quanh anh, những đệ tử khác đang luyện tập dưới ánh nắng chiều. "
    "Tiếng kiếm va chạm vang lên như nhạc điệu. "
    "Lan tiến đến gần, mỉm cười nhẹ nhàng: 'Chào mừng đến Thanh Vân Tông.' "
    "Minh gật đầu, trong lòng đã quyết tâm trở thành cao thủ. "
    "Con đường phía trước đầy gian nan, nhưng anh không hề chùn bước. "
    "Bóng tối đang rình rập nơi xa, nhưng giờ này chưa phải lúc. "
    "Hành trình tu tiên chính thức bắt đầu từ đây. " * 5
)

MOCK_SUMMARY = "Minh gia nhập tông phái và gặp Lan."

MOCK_CHARACTER_STATES = {
    "character_states": [
        {
            "name": "Minh",
            "mood": "quyết tâm",
            "arc_position": "rising",
            "knowledge": ["biết đường vào tông phái"],
            "relationship_changes": [],
            "last_action": "gia nhập tông phái",
        },
        {
            "name": "Lan",
            "mood": "thân thiện",
            "arc_position": "neutral",
            "knowledge": [],
            "relationship_changes": [],
            "last_action": "chào đón Minh",
        },
    ]
}

MOCK_PLOT_EVENTS = {
    "events": [
        {
            "event": "Minh gia nhập Thanh Vân Tông",
            "characters_involved": ["Minh"],
        },
        {
            "event": "Minh gặp Lan lần đầu",
            "characters_involved": ["Minh", "Lan"],
        },
    ]
}

MOCK_CHAPTER_SCORE = {
    "coherence": 4.0,
    "character_consistency": 4.0,
    "drama": 3.5,
    "writing_quality": 4.0,
    "notes": "Chương viết tốt, nhân vật rõ nét.",
}

MOCK_ANALYZE_STORY = {
    "relationships": [
        {
            "character_a": "Minh",
            "character_b": "Lan",
            "relation_type": "đồng_minh",
            "intensity": 0.6,
            "description": "Bạn đồng hành tu tiên",
            "tension": 0.1,
        },
        {
            "character_a": "Minh",
            "character_b": "Hùng",
            "relation_type": "kẻ_thù",
            "intensity": 0.8,
            "description": "Kẻ thù không đội trời chung",
            "tension": 0.8,
        },
    ],
    "conflict_points": ["Minh vs Hùng", "Bí mật tông phái"],
    "untapped_drama": ["Phản bội nội bộ"],
    "character_weaknesses": {"Minh": "Tự tin quá mức"},
}

MOCK_AGENT_ACTION = {
    "content": "Ta sẽ không bỏ cuộc dù khó khăn đến đâu!",
    "action_type": "post",
    "target": "Lan",
    "sentiment": "tích_cực",
    "new_mood": "quyết_tâm",
    "trust_change": 5,
}

MOCK_EVALUATE_DRAMA = {
    "events": [
        {
            "event_type": "xung_đột",
            "characters_involved": ["Minh", "Hùng"],
            "description": "Minh và Hùng đối đầu căng thẳng",
            "drama_score": 0.75,
            "suggested_insertion": "chương 2",
        }
    ],
    "overall_drama_score": 0.7,
    "relationship_changes": [
        {
            "character_a": "Minh",
            "character_b": "Hùng",
            "new_relation": "kẻ_thù",
        }
    ],
}

MOCK_DRAMA_SUGGESTIONS = {
    "suggestions": [
        "Thêm cảnh phản bội bất ngờ",
        "Tạo tình huống nguy hiểm tột cùng",
        "Tiết lộ bí mật làm đảo lộn mọi thứ",
    ],
    "character_arcs": {
        "Minh": "anh hùng vươn lên từ nghịch cảnh",
        "Hùng": "kẻ phản diện có lý do chính đáng",
    },
    "tension_points": {"Minh-Hùng": 0.8},
}

MOCK_ESCALATION_EVENT = {
    "event_type": "đối_đầu",
    "characters_involved": ["Minh", "Hùng"],
    "description": "Trận đại chiến quyết định tại đỉnh núi",
    "drama_score": 0.9,
    "suggested_insertion": "chương 2",
}

MOCK_QUICK_DRAMA_CHECK = {
    "drama_score": 0.8,
    "weak_points": [],
    "strong_points": ["Xung đột rõ ràng", "Nhân vật sống động"],
}


MOCK_VOICE_PROFILES = [
    {
        "name": name,
        "register": "casual",
        "vocabulary_level": "casual",
        "sentence_style": "short_punchy",
        "verbal_tics": [tic],
        "emotional_baseline": baseline,
        "emotional_expression": {
            "anger": "nói cộc lốc",
            "joy": "cười lớn",
            "sadness": "im lặng",
        },
        "avoid_phrases": ["xin lỗi rối rít"],
        "dialogue_examples": [line],
    }
    for name, tic, baseline, line in (
        ("Minh", "hay nói 'được thôi'", "kiên định", "Ta sẽ không lùi bước."),
        ("Lan", "hay hỏi lại 'thật sao?'", "trầm tĩnh", "Chào mừng đến Thanh Vân Tông."),
        ("Hùng", "cười khẩy trước khi nói", "kiêu ngạo", "Ngươi chưa đủ tư cách."),
    )
]

# (system-prompt substring, response). Matched against the lower-cased system
# prompt, in order, after the role routes in _route_mock_response. A str
# response is returned as-is; anything else is JSON-encoded.
_SYSTEM_PROMPT_ROUTES: list[tuple[str, object]] = [
    # ── Layer 1 planning ──────────────────────────────────────────────────────
    (
        "nhà văn triết học",  # theme_premise_generator
        {
            "premise_statement": "Câu chuyện về tu tiên, nhưng thực chất nói về lòng kiên định",
            "thematic_core": "Sức mạnh thật sự đến từ ý chí.",
            "thematic_keywords": ["kiên định", "tu luyện", "tình bạn"],
            "moral_dilemma": "Minh phải chọn giữa sức mạnh và bạn bè.",
        },
    ),
    (
        "tạo cấu trúc arc nhân vật",  # arc_waypoint_generator
        {
            "characters": [
                {
                    "name": "Minh",
                    "waypoints": [
                        {
                            "stage_name": "khởi đầu",
                            "chapter_start": 1,
                            "chapter_end": 2,
                            "description": "Minh gia nhập tông phái",
                            "emotional_state": "hứng khởi",
                            "progress_pct": 0.5,
                        }
                    ],
                }
            ]
        },
    ),
    ("xây dựng giọng văn nhân vật", MOCK_VOICE_PROFILES),  # character_voice_profiler
    (
        "biên tập viên phân tích cấu trúc truyện",  # outline_arc_validator
        {"warnings": [], "score": 0.9},
    ),
    (
        "biên tập viên kịch bản chuyên nghiệp",  # outline_critic
        {
            "plot_holes": [],
            "pacing_issues": [],
            "character_underuse": [],
            "arc_coherence": [],
            "foreshadowing_gaps": [],
            "overall_score": 4,
        },
    ),
    (
        "chuyên gia xây dựng xung đột truyện",  # conflict_web_builder
        {
            "conflicts": [
                {
                    "conflict_id": "c1",
                    "conflict_type": "external",
                    "characters": ["Minh", "Hùng"],
                    "description": "Hùng muốn trả thù tông phái",
                    "arc_range": "1-2",
                    "intensity": 4,
                }
            ]
        },
    ),
    (
        "bậc thầy foreshadowing",  # foreshadowing_manager
        {
            "foreshadowing": [
                {
                    "hint": "Vết sẹo của Hùng",
                    "plant_chapter": 1,
                    "payoff_chapter": 2,
                    "characters_involved": ["Hùng"],
                }
            ]
        },
    ),
    (
        "chuyên gia cấu trúc cảnh truyện",  # scene_beat_generator
        {
            "scenes": [
                {
                    "scene_num": 1,
                    "characters": ["Minh", "Lan"],
                    "setting": "Thanh Vân Tông, buổi chiều",
                    "action": "Minh gia nhập tông phái",
                    "tension_level": 0.4,
                    "pov": "Minh",
                    "emotional_goal": "hứng khởi",
                }
            ]
        },
    ),
    # ── Layer 1 per-chapter validation / extraction ───────────────────────────
    (
        "editor kiểm tra chất lượng truyện",  # chapter_contract_builder
        {"compliance_score": 0.9, "met": ["nhân vật chính xuất hiện"], "failures": []},
    ),
    (
        "bạn là nhà phê bình văn học. trả về json",  # self_review critic
        {
            "coherence": 4,
            "character_consistency": 4,
            "pacing": 4,
            "writing_quality": 4,
            "overall": 4,
            "weaknesses": [],
            "strengths": ["Nhân vật rõ nét"],
        },
    ),
    (
        "editor phân tích nhịp độ",  # pacing_enforcer.verify_pacing
        {"detected": "rising", "confidence": 0.8, "reason": "xung đột tăng dần"},
    ),
    ("trích xuất thay đổi thế giới", {"world_changes": []}),  # post_processing
    (
        "trích xuất thời gian và vị trí",  # consistency_validators
        {"timeline_positions": {}, "character_locations": {"Minh": "Thanh Vân Tông"}},
    ),
    (
        "trích xuất tóm tắt có cấu trúc",  # structured_summary_extractor
        {
            "plot_critical_events": ["Minh gia nhập tông phái"],
            "character_developments": [],
            "open_questions": [],
            "emotional_shift": "hứng khởi",
            "threads_advanced": [],
            "threads_opened": [],
            "threads_resolved": [],
            "chapter_ending_hook": "",
            "actual_emotional_arc": "hứng khởi",
        },
    ),
    (
        "trích xuất tuyến truyện",  # plot_thread_tracker
        {
            "new_threads": [
                {
                    "thread_id": "t1",
                    "description": "Hùng muốn trả thù",
                    "involved_characters": ["Hùng"],
                    "urgency": 3,
                }
            ],
            "progressed_threads": [],
            "resolved_threads": [],
        },
    ),
    (
        "chuyên gia tâm lý nhân vật",  # character_memory_bank
        {
            "characters": [
                {
                    "character_name": "Minh",
                    "emotional_memories": [
                        {
                            "chapter": 1,
                            "trigger_event": "gặp Lan",
                            "emotion": "ấm áp",
                            "intensity": 0.5,
                        }
                    ],
                }
            ]
        },
    ),
    (
        "chuyên gia phân tích cốt truyện",  # l1_causal_graph
        {
            "events": [
                {
                    "description": "Minh gia nhập tông phái",
                    "characters": ["Minh"],
                    "event_type": "setup",
                }
            ]
        },
    ),
    ("kiểm tra vi phạm quy tắc thế giới", {"violations": []}),  # quality_validators
    (
        "kiểm tra giọng nói nhân vật trong đối thoại",  # quality_validators voice
        {"warnings": []},
    ),
    (
        "phân tích chủ đề. trả json",  # thematic_resonance_tracker
        {
            "themes": [
                {
                    "theme": "lòng kiên định",
                    "strength": 0.7,
                    "manifestation": "Minh không chùn bước",
                    "symbols": ["thanh kiếm"],
                }
            ]
        },
    ),
    # ── Layer 2 analysis ──────────────────────────────────────────────────────
    (
        "phân tích chủ đề văn học",  # thematic_tracker
        {
            "central_theme": "lòng kiên định",
            "recurring_motifs": ["thanh kiếm"],
            "symbolic_items": [],
            "thematic_questions": [],
        },
    ),
    (
        "đánh giá độ nhất quán chủ đề",  # thematic_tracker per-chapter check
        {
            "theme_alignment": 0.8,
            "motifs_present": ["thanh kiếm"],
            "motifs_missing": [],
            "drift_warning": "",
        },
    ),
    (
        "phân tích tiến triển tuyến truyện",  # thread_watchdog
        {"thread_updates": [{"thread_id": "t1", "mentioned": True}]},
    ),
    (
        "editor chuyên giải quyết tuyến truyện",  # thread_watchdog resolution
        {"resolutions_added": []},
    ),
    (
        "biên tập viên giọng văn khắt khe",  # layer2 chapter_contract voice check
        {
            "per_character": {
                "Minh": {"compliance_score": 0.9, "missing_tics": [], "tone_mismatch": ""}
            }
        },
    ),
    (
        "chuyên gia tâm lý học nhân vật",  # psychology_engine
        {
            "primary_goal": "trở nên mạnh mẽ",
            "hidden_motive": "chứng tỏ bản thân",
            "fear": "thất bại",
            "shame_trigger": "bị coi thường",
            "vulnerabilities": [],
        },
    ),
    (
        "trích xuất thông tin bối cảnh truyện",  # setting_continuity locations
        {
            "locations": [
                {
                    "name": "Thanh Vân Tông",
                    "description": "Tông phái trên núi",
                    "accessible_from": [],
                }
            ],
            "objects": [],
        },
    ),
    ("phân tích di chuyển và vật phẩm", {"movements": []}),  # setting_continuity
    (
        "phân tích phong cách nói",  # voice_fingerprint
        {
            "vocabulary_level": "moderate",
            "formality": "neutral",
            "emotional_expression": "moderate",
            "speech_quirks": [],
            "accent_markers": [],
            "typical_topics": ["tu luyện"],
        },
    ),
    ("phân tách văn bản thành các cảnh", {"scenes": []}),  # scene_enhancer split
    (
        "đánh giá kịch tính. trả về json",  # scene_enhancer.score_scenes
        {"drama_score": 0.7, "weak_points": [], "strong_points": ["xung đột rõ"]},
    ),
    ("đánh giá kịch tính nhanh", {"drama_score": 0.7}),  # enhancer drama re-check
    ("biên tập viên kiểm tra nhất quán", {"issues": []}),  # enhancer consistency
    ("biên tập viên kiểm tra tính nhất quán", {"issues": []}),  # coherence_validator
    (
        "biên tập viên khắt khe",  # layer2 chapter_contract
        {
            "drama_actual": 0.7,
            "missing_escalations": [],
            "missing_subtext": [],
            "missing_causal_refs": [],
            "violated_patterns": [],
        },
    ),
    ("trích xuất các lời khẳng định", {"fact_mentions": []}),  # causal_chain
    ("thêm chi tiết giác quan", MOCK_CHAPTER_TEXT),  # sensory_polish (plain text)
]


# ── Routing helper ────────────────────────────────────────────────────────────


# Prompts that hit no route. The pipeline catches most LLM-call exceptions and
# falls back, so the AssertionError alone could be swallowed; the mock_llm
# fixture fails the test at teardown if anything landed here.
_UNROUTED: list[str] = []


def _route_mock_response(
    system_prompt: str = "", user_prompt: str = "", **kwargs
) -> str:
    """Return appropriate mock text response based on prompt keywords.

    Routing order matters — more specific checks come first.
    We check both system_prompt and user_prompt (many prompts embed the role in user_prompt).
    A prompt that matches no route fails the test: a new LLM call must get an
    explicit route instead of silently receiving chapter text.
    """
    sys_p = system_prompt.lower()
    usr_p = user_prompt.lower()
    combined = sys_p + " " + usr_p

    # ── Layer 1: character generation ─────────────────────────────────────────
    # system_prompt = "Bạn là nhà văn chuyên xây dựng nhân vật. Trả về JSON."
    if "xây dựng nhân vật" in combined or "nhà văn chuyên xây dựng" in combined:
        return json.dumps(MOCK_CHARACTERS, ensure_ascii=False)

    # ── Layer 1: world building ────────────────────────────────────────────────
    # user_prompt = "Bạn là kiến trúc sư thế giới cho truyện..."
    # system_prompt = "Bạn là kiến trúc sư thế giới. Trả về JSON."
    if "kiến trúc sư" in combined or "kiến trúc sư thế giới" in combined:
        return json.dumps(MOCK_WORLD, ensure_ascii=False)

    # ── Layer 1: outline / synopsis ────────────────────────────────────────────
    # user_prompt = "Bạn là biên kịch chuyên xây dựng cốt truyện..."
    # system_prompt = "Bạn là biên kịch tài năng. Trả về JSON."
    if "biên kịch" in combined:
        return json.dumps(MOCK_OUTLINE, ensure_ascii=False)

    # ── Layer 1: summarize chapter ─────────────────────────────────────────────
    # system_prompt = "Bạn là trợ lý tóm tắt nội dung. Viết bằng tiếng Việt."
    if "trợ lý tóm tắt" in combined or "tóm tắt nội dung" in combined:
        return MOCK_SUMMARY

    # ── Layer 1: extract character states ─────────────────────────────────────
    # system_prompt = "Trích xuất trạng thái nhân vật. Trả về JSON."
    if "trích xuất trạng thái nhân vật" in combined:
        return json.dumps(MOCK_CHARACTER_STATES, ensure_ascii=False)

    # ── Layer 1: extract plot events ──────────────────────────────────────────
    # system_prompt = "Trích xuất sự kiện cốt truyện. Trả về JSON."
    if "trích xuất sự kiện cốt truyện" in combined:
        return json.dumps(MOCK_PLOT_EVENTS, ensure_ascii=False)

    # ── Layer 1: write chapter (non-streaming) ─────────────────────────────────
    # system_prompt = "Bạn là tiểu thuyết gia tài năng viết truyện {genre} bằng tiếng Việt."
    if "tiểu thuyết gia tài năng" in combined:
        return MOCK_CHAPTER_TEXT

    # ── Quality scoring ────────────────────────────────────────────────────────
    # system_prompt = "Bạn là chuyên gia đánh giá văn học. Trả về JSON."
    if "chuyên gia đánh giá văn học" in combined:
        return json.dumps(MOCK_CHAPTER_SCORE, ensure_ascii=False)

    # ── Layer 2: story analysis ────────────────────────────────────────────────
    # system_prompt = "Bạn là nhà phân tích truyện chuyên sâu. Trả về JSON."
    # user_prompt starts with "Bạn là nhà phân tích truyện chuyên sâu..."
    if "nhà phân tích truyện" in combined:
        return json.dumps(MOCK_ANALYZE_STORY, ensure_ascii=False)

    # ── Layer 2: conflict graph (per-chapter analysis) ─────────────────────────
    # system_prompt = "Phân tích cấu trúc tường thuật. Trả về JSON."
    if "phân tích cấu trúc tường thuật" in combined or "tường thuật" in combined:
        return json.dumps(
            {"goal": "chiến thắng", "obstacle": "kẻ thù", "conflict": "đối đầu"},
            ensure_ascii=False,
        )

    # ── Layer 2: agent persona (simulator) ────────────────────────────────────
    # system_prompt = "Bạn đang nhập vai {name} trong một mô phỏng tương tác..."
    if "nhập vai" in combined and "mô phỏng tương tác" in combined:
        return json.dumps(MOCK_AGENT_ACTION, ensure_ascii=False)

    # ── Layer 2: agent reaction ────────────────────────────────────────────────
    # system_prompt = "Bạn là {name}. Phản ứng với hành động của..."
    if "phản ứng với hành động" in combined:
        return json.dumps(MOCK_AGENT_ACTION, ensure_ascii=False)

    # ── Layer 2: evaluate drama ────────────────────────────────────────────────
    # system_prompt = "Bạn là đạo diễn kịch tính. Trả về JSON."
    # user_prompt starts with "Bạn là đạo diễn kịch tính, đánh giá..."
    if "đạo diễn kịch tính" in combined:
        return json.dumps(MOCK_EVALUATE_DRAMA, ensure_ascii=False)

    # ── Layer 2: drama suggestions ─────────────────────────────────────────────
    # system_prompt = "Bạn là cố vấn kịch bản. Trả về JSON."
    if "cố vấn kịch bản" in combined:
        return json.dumps(MOCK_DRAMA_SUGGESTIONS, ensure_ascii=False)

    # ── Layer 2: escalation events ─────────────────────────────────────────────
    # Also uses "Bạn là đạo diễn kịch tính" but with escalation keywords in user
    # (already caught above — escalation uses same system prompt as evaluate_drama)
    # Handled by đạo diễn kịch tính check above

    # ── Layer 2: enhance chapter ──────────────────────────────────────────────
    # system_prompt = "Bạn là nhà văn tài năng chuyên viết truyện kịch tính..."
    # user_prompt starts "Bạn là nhà văn tài năng chuyên viết truyện {genre_style}..."
    if "nhà văn tài năng" in combined:
        return MOCK_CHAPTER_TEXT

    # ── Layer 2: quick drama check ─────────────────────────────────────────────
    # system_prompt = "Đánh giá kịch tính chi tiết. Trả về JSON."
    if "đánh giá kịch tính chi tiết" in combined:
        return json.dumps(MOCK_QUICK_DRAMA_CHECK, ensure_ascii=False)

    # ── Per-step analysis/validation calls, matched on their system prompt ────
    for needle, payload in _SYSTEM_PROMPT_ROUTES:
        if needle in sys_p:
            return payload if isinstance(payload, str) else json.dumps(
                payload, ensure_ascii=False
            )

    _UNROUTED.append(user_prompt[:120])
    raise AssertionError(f"unrouted prompt: {user_prompt[:120]}")


def _route_mock_json(system_prompt: str = "", user_prompt: str = "", **kwargs) -> dict:
    """Return appropriate mock dict response based on prompt keywords."""
    text = _route_mock_response(
        system_prompt=system_prompt, user_prompt=user_prompt, **kwargs
    )
    try:
        result = json.loads(text)
        return result
    except (json.JSONDecodeError, ValueError):
        return {"content": text}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_llm_singleton():
    """Reset LLMClient singleton between tests to avoid state leakage."""
    from services import llm_client as llm_module

    original_instance = llm_module.LLMClient._instance
    llm_module.LLMClient._instance = None
    yield
    llm_module.LLMClient._instance = original_instance


@pytest.fixture
def mock_llm():
    """Patch LLMClient methods at class level for all pipeline tests."""
    _UNROUTED.clear()
    with (
        patch(
            "services.llm_client.LLMClient.generate", side_effect=_route_mock_response
        ) as mock_gen,
        patch(
            "services.llm_client.LLMClient.generate_json", side_effect=_route_mock_json
        ) as mock_json,
        patch(
            "services.llm_client.LLMClient.check_connection", return_value=(True, "OK")
        ) as mock_check,
    ):
        yield {
            "generate": mock_gen,
            "generate_json": mock_json,
            "check_connection": mock_check,
        }
    assert not _UNROUTED, f"unrouted prompts: {_UNROUTED}"


@pytest.fixture
def pipeline(mock_llm):
    """Create PipelineOrchestrator with mocked LLM."""
    from pipeline.orchestrator import PipelineOrchestrator

    return PipelineOrchestrator()


async def _run_minimal_pipeline(pipeline, **overrides):
    """Helper: run pipeline with minimal settings."""
    defaults = dict(
        title="Thiên Linh Kiếm Khách",
        genre="tiên hiệp",
        idea="Một thanh niên bước vào thế giới tu tiên đầy nguy hiểm",
        style="Miêu tả chi tiết",
        num_chapters=2,
        num_characters=3,
        word_count=500,
        num_sim_rounds=1,
        enable_agents=False,
        enable_scoring=False,
        enable_media=False,
    )
    defaults.update(overrides)
    return await pipeline.run_full_pipeline(**defaults)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestFullPipelineFlow:
    """E2E tests for the full 2-layer pipeline."""

    async def test_full_pipeline_completes(self, pipeline):
        """Pipeline should complete with status 'completed'."""
        output = await _run_minimal_pipeline(pipeline)
        assert output.status == "completed", f"Expected completed, got: {output.status}"

    async def test_pipeline_output_has_story_draft(self, pipeline):
        """story_draft must be populated with chapters."""
        output = await _run_minimal_pipeline(pipeline)
        assert output.story_draft is not None, "story_draft is None"
        assert len(output.story_draft.chapters) > 0, "No chapters in story_draft"

    async def test_pipeline_output_has_enhanced_story(self, pipeline):
        """enhanced_story must be populated with chapters."""
        output = await _run_minimal_pipeline(pipeline)
        assert output.enhanced_story is not None, "enhanced_story is None"
        assert len(output.enhanced_story.chapters) > 0, "No chapters in enhanced_story"

    async def test_pipeline_output_logs_populated(self, pipeline):
        """logs list must have entries after pipeline run."""
        output = await _run_minimal_pipeline(pipeline)
        assert len(output.logs) > 0, "logs list is empty"
        # Verify layer markers appear in logs
        all_logs = " ".join(output.logs)
        assert "LAYER 1" in all_logs or "Layer 1" in all_logs

    async def test_pipeline_draft_chapters_have_content(self, pipeline):
        """Each chapter in story_draft must have non-empty content."""
        output = await _run_minimal_pipeline(pipeline)
        for ch in output.story_draft.chapters:
            assert ch.content, f"Chapter {ch.chapter_number} has empty content"
            assert ch.chapter_number > 0

    async def test_pipeline_draft_has_characters(self, pipeline):
        """story_draft must have characters populated."""
        output = await _run_minimal_pipeline(pipeline)
        assert len(output.story_draft.characters) > 0, "No characters in story_draft"

    async def test_pipeline_draft_has_world(self, pipeline):
        """story_draft must have world setting."""
        output = await _run_minimal_pipeline(pipeline)
        assert output.story_draft.world is not None, "world is None in story_draft"

    async def test_pipeline_progress_reaches_1(self, pipeline):
        """progress should reach 1.0 on successful pipeline."""
        output = await _run_minimal_pipeline(pipeline)
        assert output.status == "completed"
        assert output.progress == 1.0, f"Expected progress=1.0, got {output.progress}"


class TestPipelineWithScoring:
    """Tests for pipeline with scoring enabled."""

    async def test_pipeline_output_has_quality_scores(self, pipeline):
        """quality_scores list must be non-empty when enable_scoring=True."""
        output = await _run_minimal_pipeline(pipeline, enable_scoring=True)
        assert len(output.quality_scores) > 0, "quality_scores is empty"

    async def test_quality_scores_have_valid_range(self, pipeline):
        """Each StoryScore.overall must be in 1-5 range."""
        output = await _run_minimal_pipeline(pipeline, enable_scoring=True)
        for score in output.quality_scores:
            assert 1.0 <= score.overall <= 5.0, (
                f"overall score {score.overall} out of range [1, 5]"
            )


class TestPipelineWithScoringDisabled:
    """Tests for pipeline with scoring disabled."""

    async def test_pipeline_with_scoring_disabled(self, pipeline):
        """Pipeline should complete without quality scores when disabled."""
        output = await _run_minimal_pipeline(pipeline, enable_scoring=False)
        assert output.status == "completed"
        assert output.story_draft is not None
        assert output.quality_scores == []


class TestPipelineWithAgentsDisabled:
    """Tests for pipeline with agents disabled."""

    async def test_pipeline_with_agents_disabled(self, pipeline):
        """Pipeline should complete without agent reviews."""
        output = await _run_minimal_pipeline(pipeline, enable_agents=False)
        assert output.status == "completed"
        assert output.story_draft is not None
        assert output.enhanced_story is not None


class TestPipelineGracefulFallbacks:
    """Tests for graceful handling of layer failures."""

    async def test_pipeline_handles_layer2_failure(self, mock_llm):
        """A Layer 2 failure is caught; the draft stands in for the enhanced story."""
        from pipeline.orchestrator import PipelineOrchestrator

        with patch(
            "pipeline.layer2_enhance.enhancer.StoryEnhancer.enhance_story",
            side_effect=RuntimeError("Simulated Layer 2 failure"),
        ):
            orch = PipelineOrchestrator()
            output = await _run_minimal_pipeline(orch)

        # Should fall back gracefully — Layer 2 failure is caught
        assert output.enhanced_story is not None, (
            "enhanced_story should fall back to draft chapters"
        )
        assert [c.content for c in output.enhanced_story.chapters] == [
            c.content for c in output.story_draft.chapters
        ]
        assert output.status == "completed"

    async def test_pipeline_connection_failure_returns_error(self, mock_llm):
        """Connection check failure should abort pipeline with error status."""
        from pipeline.orchestrator import PipelineOrchestrator

        mock_llm["check_connection"].return_value = (False, "Connection refused")
        orch = PipelineOrchestrator()
        output = await _run_minimal_pipeline(orch)

        assert output.status == "error"
        assert any(
            "LLM" in log or "ket noi" in log.lower() or "kết nối" in log
            for log in output.logs
        )

    async def test_pipeline_layer1_failure_returns_error(self, mock_llm):
        """Layer 1 hard failure should abort with error status."""
        from pipeline.orchestrator import PipelineOrchestrator

        with patch(
            "pipeline.layer1_story.generator.StoryGenerator.generate_full_story",
            side_effect=RuntimeError("Simulated Layer 1 failure"),
        ):
            orch = PipelineOrchestrator()
            output = await _run_minimal_pipeline(orch)

        assert output.status == "error"


class TestPipelineOutputStructure:
    """Tests for output schema integrity."""

    async def test_pipeline_output_is_pipeline_output_type(self, pipeline):
        """Output must be a PipelineOutput instance."""
        from models.schemas import PipelineOutput

        output = await _run_minimal_pipeline(pipeline)
        assert isinstance(output, PipelineOutput)

    async def test_pipeline_chapters_match_requested_count(self, pipeline):
        """story_draft should have chapters matching num_chapters."""
        output = await _run_minimal_pipeline(pipeline, num_chapters=2)
        assert len(output.story_draft.chapters) == 2, (
            f"Expected 2 chapters, got {len(output.story_draft.chapters)}"
        )

    async def test_pipeline_simulation_result_set(self, pipeline):
        """simulation_result should be populated after Layer 2."""
        output = await _run_minimal_pipeline(pipeline)
        assert output.simulation_result is not None, "simulation_result is None"

    async def test_pipeline_current_layer_advanced(self, pipeline):
        """current_layer should be at least 2 after successful run."""
        output = await _run_minimal_pipeline(pipeline)
        assert output.current_layer >= 2, (
            f"current_layer={output.current_layer}, expected >=2"
        )
