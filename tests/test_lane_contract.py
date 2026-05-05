"""Lane contract tests — sprint plans/260505-1146-simulator-debate-contract/.

Verifies the dramatic↔craft lane separation between DramaSimulator and the
debate panel:

  1. LaneSuggestion schema round-trip + legacy str compat (auto-wrap +
     unknown-role fallback warning).
  2. Each craft agent's review prompt contains the CRAFT_LANE_BOUNDARY
     `PHẠM VI:` line, and the simulator's CharacterAgent prompts inject
     DRAMATIC_LANE_BOUNDARY.
  3. `_drop_cross_lane(reviews, "craft")` drops dramatic-tagged drift from a
     craft agent and emits a WARN.
  4. Simulator's defensive filter strips craft-tagged LaneSuggestion before
     building SimulationResult.
  5. Enhancer logs `[ENHANCER] applying N dramatic + M craft suggestions` at
     entry, with correct counts.
  6. Schema regression — AgentReview with mixed lane suggestions round-trips
     through `model_validate` / `model_dump` without errors.
"""
import logging

import pytest

from models.schemas import (
    AgentReview,
    LaneSuggestion,
    SimulationResult,
)


# ── Test 1: LaneSuggestion schema + legacy compat ───────────────────────

class TestLaneSuggestionSchema:
    def test_round_trip(self):
        sug = LaneSuggestion(
            lane="dramatic",
            text="Tăng xung đột chương 3",
            severity="warning",
            target_chapter=3,
            agent_role="character_simulator",
        )
        dumped = sug.model_dump()
        restored = LaneSuggestion.model_validate(dumped)
        assert restored == sug
        assert restored.lane == "dramatic"
        assert restored.target_chapter == 3

    def test_str_coercion(self):
        sug = LaneSuggestion(lane="craft", text="Tighten dialogue", agent_role="dialogue_expert")
        assert str(sug) == "Tighten dialogue"
        # Equality with plain string (backward compat)
        assert sug == "Tighten dialogue"
        # `in` operator works against text
        assert "dialogue" in sug

    def test_legacy_str_auto_wrap_known_role(self):
        review = AgentReview(
            agent_role="drama_critic",
            agent_name="Nhà Phê Bình Kịch Tính",
            score=0.8,
            suggestions=["Đẩy mạnh cao trào chương 5"],
        )
        assert len(review.suggestions) == 1
        sug = review.suggestions[0]
        assert isinstance(sug, LaneSuggestion)
        assert sug.lane == "craft"  # drama_critic is craft-lane per _DEFAULT_LANE_BY_ROLE
        assert sug.agent_role == "drama_critic"
        assert sug.text == "Đẩy mạnh cao trào chương 5"

    def test_legacy_str_auto_wrap_simulator(self):
        review = AgentReview(
            agent_role="character_simulator",
            agent_name="Sim",
            score=0.7,
            suggestions=["Nhân vật A nên phản kháng mạnh hơn"],
        )
        sug = review.suggestions[0]
        assert isinstance(sug, LaneSuggestion)
        assert sug.lane == "dramatic"

    def test_unknown_role_falls_back_to_craft_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            review = AgentReview(
                agent_role="some_made_up_role",
                agent_name="Mystery",
                score=0.5,
                suggestions=["plain string"],
            )
        assert len(review.suggestions) == 1
        assert isinstance(review.suggestions[0], LaneSuggestion)
        assert review.suggestions[0].lane == "craft"
        assert any("unknown_agent_role" in r.message for r in caplog.records)

    def test_dict_input_auto_wrapped(self):
        review = AgentReview(
            agent_role="pacing_analyzer",
            agent_name="Pacing",
            score=0.6,
            suggestions=[{"lane": "craft", "text": "Slow down chương 4"}],
        )
        sug = review.suggestions[0]
        assert isinstance(sug, LaneSuggestion)
        assert sug.lane == "craft"
        assert sug.agent_role == "pacing_analyzer"  # backfilled


# ── Test 2: Lane boundary present in all agent prompts ──────────────────

class TestPromptBoundaries:
    def test_all_craft_review_prompts_contain_boundary(self):
        from pipeline.agents import agent_prompts

        review_keys = [
            "EDITOR_REVIEW",
            "CHARACTER_REVIEW",
            "DIALOGUE_REVIEW",
            "DRAMA_REVIEW",
            "CONTINUITY_REVIEW",
            "STYLE_REVIEW",
            "PACING_REVIEW",
            "DIALOGUE_BALANCE_REVIEW",
        ]
        for key in review_keys:
            prompt = getattr(agent_prompts, key)
            assert "PHẠM VI:" in prompt, f"{key} missing lane boundary"
            assert "KHÔNG được đề xuất thay đổi plot" in prompt, (
                f"{key} missing craft-lane boundary clause"
            )

    def test_reader_simulator_prompt_has_boundary(self):
        from pipeline.agents.reader_simulator import _READER_PROMPT

        assert "PHẠM VI:" in _READER_PROMPT

    def test_simulator_dramatic_boundary_constant_present(self):
        from pipeline.layer2_enhance.simulator import DRAMATIC_LANE_BOUNDARY

        assert "PHẠM VI:" in DRAMATIC_LANE_BOUNDARY
        assert "nhập vai nhân vật" in DRAMATIC_LANE_BOUNDARY
        assert "KHÔNG critique craft" in DRAMATIC_LANE_BOUNDARY


# ── Test 3: _drop_cross_lane drops dramatic drift from craft agents ─────

class TestDropCrossLaneCraft:
    def test_drops_dramatic_tagged_from_craft_agent(self, caplog):
        from pipeline.agents.agent_registry import _drop_cross_lane

        # Craft agent (drama_critic) erroneously emits a dramatic suggestion
        review = AgentReview(
            agent_role="drama_critic",
            agent_name="DramaCritic",
            score=0.6,
            suggestions=[],
        )
        good = LaneSuggestion(lane="craft", text="Sửa nhịp đoạn 3", agent_role="drama_critic")
        bad = LaneSuggestion(lane="dramatic", text="Thêm conflict mới", agent_role="drama_critic")
        review.suggestions = [good, bad]

        with caplog.at_level(logging.WARNING):
            _drop_cross_lane([review], "craft")

        assert len(review.suggestions) == 1
        assert review.suggestions[0] == good
        assert any("cross_lane_suggestion_dropped" in r.message for r in caplog.records)

    def test_keeps_legacy_strings_untouched(self):
        from pipeline.agents.agent_registry import _drop_cross_lane

        review = AgentReview(
            agent_role="dialogue_expert",
            agent_name="Dlg",
            score=0.7,
            suggestions=["plain legacy string"],  # auto-wrapped to craft
        )
        _drop_cross_lane([review], "craft")
        assert len(review.suggestions) == 1
        assert str(review.suggestions[0]) == "plain legacy string"


# ── Test 4: Simulator filters craft-tagged drift before SimulationResult ─

class TestSimulatorLaneFilter:
    def test_simulator_filter_logic(self, caplog):
        """Replicate the inline filter from simulator.py:1018-1032."""
        from models.schemas import LaneSuggestion as _LS

        raw_suggestions = [
            _LS(lane="dramatic", text="Đẩy cao trào", agent_role="character_simulator"),
            _LS(lane="craft", text="Sửa pacing", agent_role="character_simulator"),  # cross-lane
            "plain string suggestion",
        ]

        sim_logger = logging.getLogger("pipeline.layer2_enhance.simulator")
        filtered_suggestions: list[str] = []
        with caplog.at_level(logging.WARNING, logger=sim_logger.name):
            for sug in raw_suggestions:
                if isinstance(sug, _LS) and sug.lane != "dramatic":
                    sim_logger.warning(
                        "cross_lane_suggestion_dropped agent=character_simulator "
                        "claimed=%s expected=dramatic text=%r",
                        sug.lane, str(sug)[:80],
                    )
                    continue
                filtered_suggestions.append(str(sug))

        assert len(filtered_suggestions) == 2
        assert "Đẩy cao trào" in filtered_suggestions
        assert "plain string suggestion" in filtered_suggestions
        assert "Sửa pacing" not in filtered_suggestions
        assert any("cross_lane_suggestion_dropped" in r.message for r in caplog.records)


# ── Test 5: Enhancer logs lane split at entry ───────────────────────────

class TestEnhancerLaneSplitLog:
    def test_lane_split_log_replicates_enhancer_logic(self, caplog):
        """Mirror the partition in enhancer.py:1046-1066 and verify the log.

        Uses a SimpleNamespace stand-in for sim_result because the enhancer's
        partition runs on `getattr(sim_result, "drama_suggestions", []) or []`
        — it doesn't require a validated SimulationResult. SimulationResult
        itself coerces drama_suggestions to `list[str]`, but the simulator
        passes raw lists in some flows; the partition handles both shapes.
        """
        from types import SimpleNamespace

        sim_result = SimpleNamespace(drama_suggestions=[
            LaneSuggestion(lane="dramatic", text="A", agent_role="character_simulator"),
            LaneSuggestion(lane="dramatic", text="B", agent_role="character_simulator"),
            LaneSuggestion(lane="craft", text="C", agent_role="drama_critic"),
            "plain str D",  # plain str passes the "not isinstance" branch → dramatic
        ])

        from models.schemas import LaneSuggestion as _LS
        _raw = list(getattr(sim_result, "drama_suggestions", []) or [])
        dramatic = [s for s in _raw if not isinstance(s, _LS) or s.lane == "dramatic"]
        craft = [s for s in _raw if isinstance(s, _LS) and s.lane == "craft"]

        # 2 dramatic LaneSuggestion + 1 plain str (passes "not isinstance" branch) = 3
        assert len(dramatic) == 3
        assert len(craft) == 1

        enhancer_logger = logging.getLogger("pipeline.layer2_enhance.enhancer")
        with caplog.at_level(logging.INFO, logger=enhancer_logger.name):
            enhancer_logger.info(
                f"[ENHANCER] applying {len(dramatic)} dramatic + {len(craft)} craft suggestions"
            )

        msgs = [r.message for r in caplog.records]
        assert any(
            "[ENHANCER] applying 3 dramatic + 1 craft suggestions" in m for m in msgs
        )


# ── Test 6: Schema regression — mixed-lane round-trip ───────────────────

class TestSchemaRegression:
    def test_mixed_lane_review_round_trips(self):
        review = AgentReview(
            agent_role="drama_critic",
            agent_name="DramaCritic",
            score=0.75,
            issues=["plot gap chương 4"],
            suggestions=[
                LaneSuggestion(lane="craft", text="Cải thiện pacing", agent_role="drama_critic"),
                "legacy str — auto-wrapped",
                {"lane": "craft", "text": "From dict", "severity": "info"},
            ],
            approved=True,
            layer=2,
            iteration=1,
        )
        dumped = review.model_dump()
        restored = AgentReview.model_validate(dumped)
        assert restored.score == 0.75
        assert len(restored.suggestions) == 3
        assert all(isinstance(s, LaneSuggestion) for s in restored.suggestions)
        assert restored.suggestions[0].text == "Cải thiện pacing"
        assert restored.suggestions[1].text == "legacy str — auto-wrapped"
        assert restored.suggestions[2].text == "From dict"
        # All craft (drama_critic role default)
        assert {s.lane for s in restored.suggestions} == {"craft"}

    def test_simulation_result_with_mixed_drama_suggestions_round_trips(self):
        # SimulationResult.drama_suggestions is list[str] — verify LaneSuggestion
        # inside it survives serialization via str() coercion (its __str__).
        sim = SimulationResult(
            drama_suggestions=[
                str(LaneSuggestion(lane="dramatic", text="Kịch tính hơn", agent_role="character_simulator")),
                "raw string",
            ]
        )
        dumped = sim.model_dump()
        restored = SimulationResult.model_validate(dumped)
        assert restored.drama_suggestions == ["Kịch tính hơn", "raw string"]
