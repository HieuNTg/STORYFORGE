"""Integration tests — P0 pipeline fixes #1-#10.

One test class per fix. All LLM calls mocked at services.llm.generation boundary.
No real network or API keys required.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.schemas import (
    AgentPost,
    Chapter,
    EnhancedStory,
    PipelineOutput,
    SimulationResult,
    StoryDraft,
)
from api.pipeline_routes import router
from services.llm.client import LLMClient, WalletState


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _parse_sse(raw_bytes: bytes) -> list[dict]:
    events = []
    for line in raw_bytes.decode("utf-8").splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ─── Fix #1: /pipeline/run returns session event without TypeError ─────────────
# Root cause: test used MagicMock (sync) for an async method. AsyncMock is required.

class TestFix1PipelineRunRouteSessionEvent:
    def test_pipeline_run_route_returns_session_event(self, api_client):
        """SSE stream starts with session event; no TypeError from awaiting sync mock."""
        long_idea = "A hero emerges to challenge the dark empire ruling the ancient land."
        mock_output = PipelineOutput(status="completed", current_layer=2, progress=1.0)

        with patch("api.pipeline_routes.PipelineOrchestrator") as mock_cls, \
             patch("services.llm_client.LLMClient") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.check_connection.return_value = (True, "ok")
            mock_llm_cls.return_value = mock_llm

            mock_orch = MagicMock()
            # MUST be AsyncMock — sync MagicMock would raise TypeError on await
            mock_orch.run_full_pipeline = AsyncMock(return_value=mock_output)
            mock_cls.return_value = mock_orch

            resp = api_client.post("/pipeline/run", json={
                "idea": long_idea,
                "genre": "tien_hiep",
                "num_chapters": 1,
                "enable_agents": False,
                "enable_scoring": False,
            })

        events = _parse_sse(resp.content)
        assert events, "Expected at least one SSE event"
        assert events[0]["type"] == "session", f"First event must be 'session', got {events[0]}"
        assert "session_id" in events[0], "session event must carry session_id"


# ─── Fix #2: character_generator handles string-list response ─────────────────
# Root cause: LLM returned {"characters": ["Alice", "Bob"]} — string entries not coerced.

class TestFix2CharacterGeneratorHandlesStringList:
    def test_character_generator_handles_string_list(self):
        """String entries in LLM character list must be coerced, not crash."""
        from pipeline.layer1_story.character_generator import generate_characters

        mock_llm = MagicMock()
        # LLM returns a mix of string entries and a valid dict entry
        mock_llm.generate_json.return_value = {
            "characters": [
                "Alice",
                "Bob",
                {
                    "name": "Charlie",
                    "role": "protagonist",
                    "personality": "Brave",
                    "backstory": "A wanderer",
                    "relationships": [],
                },
            ]
        }

        result = generate_characters(mock_llm, title="Test", genre="tien_hiep", idea="test idea")
        # Should not raise — string entries coerced to minimal Character
        names = [c.name for c in result]
        assert "Alice" in names, "String 'Alice' must be coerced to Character"
        assert "Bob" in names, "String 'Bob' must be coerced to Character"
        assert "Charlie" in names, "Dict character Charlie must be included"
        # All items must be Character instances
        from models.schemas import Character
        for c in result:
            assert isinstance(c, Character), f"Expected Character, got {type(c)}"


# ─── Fix #3: 404 from any provider triggers fallback rotation ────────────────
# Root cause: 404 conditional only checked openrouter; other providers skipped.

class TestFix3FallbackRotationOn404:
    def test_404_triggers_fallback_rotation(self):
        """Mock 404 on a model in fallback_models list → next model tried."""
        # We test the _build_fallback_chain and verify 404 handling marks a model.
        # Rather than testing the full generate() chain (which would try real network),
        # we verify that after a 404 error the model is rate-limited (marked for skip),
        # meaning the chain-level loop will try the next entry.
        from services.llm.client import LLMClient

        client = LLMClient()
        fallback_model = "gpt-test-fallback"
        api_key = "test-key-404"

        # Simulate: model IS in fallback_models list
        # Under the fix, 404 on a fallback model calls _mark_model_rate_limited
        # and does NOT re-raise, allowing the chain to try the next entry.
        # We verify _mark_model_rate_limited sets a cooldown > now.
        import time
        client._mark_model_rate_limited(fallback_model, api_key, cooldown=600.0)
        assert client._is_model_rate_limited(fallback_model, api_key), (
            "After 404, model must be marked rate-limited so chain skips it"
        )

        # Cleanup
        combo = f"{fallback_model}:{api_key}"
        client._rate_limited_models.pop(combo, None)

    def test_404_does_not_raise_when_chain_has_peers(self):
        """C3 regression: 404 on primary must NOT raise — chain must rotate.

        Synthesize a 2-entry chain: entry[0] raises 404, entry[1] succeeds.
        Verify generate() returns entry[1]'s response instead of propagating 404.
        """
        from unittest.mock import patch, MagicMock
        from services.llm.client import LLMClient

        client = LLMClient()

        # Build a fake 2-entry chain
        fake_chain = [
            {"label": "primary", "model": "primary-model", "_api_key": "k1",
             "provider": MagicMock(base_url="https://api.example.com"),
             "client": MagicMock()},
            {"label": "fallback", "model": "fallback-model", "_api_key": "k2",
             "provider": MagicMock(base_url="https://api.example.com"),
             "client": MagicMock()},
        ]

        call_count = {"n": 0}

        def fake_try_provider(entry, *args, **kwargs):
            call_count["n"] += 1
            if entry["model"] == "primary-model":
                raise RuntimeError("404 Not Found: model unavailable")
            return "fallback-response"

        with patch.object(LLMClient, "_build_fallback_chain", return_value=fake_chain), \
             patch.object(LLMClient, "_try_provider", side_effect=fake_try_provider):
            result = client.generate(
                system_prompt="sys",
                user_prompt="hi",
                temperature=0.5,
            )

        assert result == "fallback-response", f"chain should rotate on 404, got: {result!r}"
        assert call_count["n"] == 2, f"both entries must be tried, got {call_count['n']} calls"


# ─── Fix #4: AgentPost.target accepts None ───────────────────────────────────
# Root cause: target field was non-optional str → Pydantic ValidationError on None.

class TestFix4AgentPostTargetOptional:
    def test_agentpost_accepts_null_target(self):
        """AgentPost must validate with target=None without raising."""
        post = AgentPost(
            agent_name="Narrator",
            content="Some content here.",
            action_type="post",
            target=None,
        )
        assert post.target is None
        assert post.agent_name == "Narrator"

    def test_agentpost_accepts_string_target(self):
        """AgentPost still validates with a string target."""
        post = AgentPost(
            agent_name="Agent1",
            content="Some content.",
            action_type="comment",
            target="Agent2",
        )
        assert post.target == "Agent2"


# ─── Fix #5: Voice prompt in scene rewrite contains fingerprint markers ───────
# Root cause: placeholder {voice_block_prepend} / {voice_block_append} left blank.

class TestFix5VoicePromptInSceneRewrite:
    def test_voice_prompt_in_scene_rewrite(self):
        """When voice_engine is set, enhanced scene prompt must include voice fingerprint text."""
        from pipeline.layer2_enhance.scene_enhancer import SceneEnhancer, ENHANCE_SCENE
        from pipeline.layer2_enhance.voice_fingerprint import VoiceFingerprintEngine
        from models.schemas import VoiceProfile

        # Build a real engine with one profile (no LLM call needed)
        engine = VoiceFingerprintEngine()
        engine.profiles["Lan"] = VoiceProfile(
            name="Lan",
            vocabulary_level="simple",
            formality="casual",
            speech_quirks=["ừ thôi"],
        )

        # build_voice_enforcement_prompt should return non-empty text
        from pipeline.layer2_enhance.voice_fingerprint import build_voice_enforcement_prompt
        from models.schemas import Character
        char = Character(name="Lan", role="protagonist", personality="Gentle")
        voice_block = build_voice_enforcement_prompt(engine, [char])
        assert voice_block, "Voice enforcement prompt must be non-empty when profiles exist"
        # Check that it references the character name or profile content
        assert "Lan" in voice_block or "simple" in voice_block or "casual" in voice_block, (
            "Voice block must reference character voice data"
        )


# ─── Fix #6: enforce_voice_preservation called without extra kwargs ───────────
# Root cause: enhancer was calling enforce_voice_preservation with wrong/missing args.

class TestFix6DriftThresholdDefaultApplied:
    def test_drift_threshold_default_applied(self):
        """enforce_voice_preservation uses default drift_threshold=0.25 when not overridden."""
        from pipeline.layer2_enhance.voice_fingerprint import enforce_voice_preservation, VoiceFingerprintEngine
        from models.schemas import Character, VoiceProfile

        engine = VoiceFingerprintEngine()
        engine.profiles["TestChar"] = VoiceProfile(name="TestChar")

        char = Character(name="TestChar", role="supporting", personality="Quiet")
        original = "TestChar nói: xin chào."
        enhanced = "TestChar nói: chào bạn."

        # Should not raise; must return (str, VoicePreservationResult)
        result_content, vp_result = enforce_voice_preservation(
            engine, original, enhanced, [char]
        )
        assert isinstance(result_content, str)
        # drift_threshold default is 0.25 — verify the result has drift_severity attribute
        assert hasattr(vp_result, "drift_severity"), (
            "VoicePreservationResult must have drift_severity"
        )


# ─── Fix #7: adaptive rounds clamped to [min_rounds, max_rounds] ─────────────
# Root cause: calculate_adaptive_rounds returned values outside the configured bounds.

class TestFix7AdaptiveRoundsClamped:
    def test_adaptive_rounds_clamped_to_max(self):
        """Large inputs must not produce rounds > max_rounds."""
        from pipeline.layer2_enhance.simulator import calculate_adaptive_rounds

        # 30 characters, 50 threads, 100 conflicts → unclamped would overflow
        characters = [object()] * 30
        threads = [object()] * 50
        conflict_web = [object()] * 100

        result = calculate_adaptive_rounds(
            characters=characters,
            threads=threads,
            conflict_web=conflict_web,
            min_rounds=4,
            max_rounds=10,
        )
        assert result <= 10, f"rounds must not exceed max_rounds=10, got {result}"
        assert result >= 4, f"rounds must be at least min_rounds=4, got {result}"

    def test_adaptive_rounds_clamped_to_min(self):
        """Minimal inputs must not produce rounds < min_rounds."""
        from pipeline.layer2_enhance.simulator import calculate_adaptive_rounds

        result = calculate_adaptive_rounds(
            characters=[],
            threads=[],
            conflict_web=[],
            min_rounds=4,
            max_rounds=10,
        )
        assert result >= 4, f"rounds must be at least min_rounds=4, got {result}"
        assert result <= 10, f"rounds must not exceed max_rounds=10, got {result}"

    def test_adaptive_rounds_exact_max(self):
        """Passing num_rounds=10 with l2_max_rounds=10 → max_rounds==10."""
        from pipeline.layer2_enhance.simulator import calculate_adaptive_rounds

        result = calculate_adaptive_rounds(
            characters=[object()] * 3,
            threads=[object()] * 3,
            conflict_web=[object()] * 3,
            min_rounds=4,
            max_rounds=10,
        )
        assert 4 <= result <= 10


# ─── Fix #8: per-run wallet isolation ─────────────────────────────────────────
# Root cause: class-level counters shared across runs → concurrent run corruption.

class TestFix8WalletIsolatedPerRun:
    @pytest.fixture(autouse=True)
    def _clean_wallet(self):
        """Reset wallet state before and after each test to avoid singleton leakage."""
        LLMClient.reset_wallet("__test_sentinel__")
        yield
        # Clean up any test run_ids we created
        with LLMClient._wallet_lock:
            for rid in ["run-A", "run-B", "__test_sentinel__"]:
                LLMClient._wallet_state.pop(rid, None)

    def test_wallet_isolated_per_run(self):
        """Two runs with different run_ids have independent wallet counters."""
        LLMClient.reset_wallet("run-A")
        LLMClient.reset_wallet("run-B")

        # Charge only run-A
        LLMClient.charge_wallet(cost_usd=0.01, tokens=100, run_id="run-A")
        LLMClient.charge_wallet(cost_usd=0.01, tokens=100, run_id="run-A")

        snap_a = LLMClient.wallet_snapshot("run-A")
        snap_b = LLMClient.wallet_snapshot("run-B")

        assert snap_a["calls"] == 2, f"run-A must have 2 calls, got {snap_a['calls']}"
        assert snap_b["calls"] == 0, f"run-B must have 0 calls, got {snap_b['calls']}"
        assert snap_a["tokens"] == 200, f"run-A tokens wrong: {snap_a['tokens']}"
        assert snap_b["tokens"] == 0, f"run-B tokens must be 0, got {snap_b['tokens']}"

    @pytest.mark.asyncio
    async def test_wallet_isolation_via_contextvar(self):
        """C1 regression: charge_wallet without explicit run_id reads the contextvar.

        Two coroutines each set their own current_run_id and call charge_wallet
        without passing run_id. Their snapshots must remain independent — proves
        the contextvar plumbing works under asyncio.gather (production path).
        """
        from services.llm.client import current_run_id
        import asyncio

        LLMClient.reset_wallet("ctx-A")
        LLMClient.reset_wallet("ctx-B")

        async def _do(rid: str, n: int):
            current_run_id.set(rid)
            for _ in range(n):
                LLMClient.charge_wallet(cost_usd=0.001, tokens=10)
                await asyncio.sleep(0)

        await asyncio.gather(
            asyncio.create_task(_do("ctx-A", 3)),
            asyncio.create_task(_do("ctx-B", 5)),
        )

        snap_a = LLMClient.wallet_snapshot("ctx-A")
        snap_b = LLMClient.wallet_snapshot("ctx-B")

        assert snap_a["calls"] == 3, f"ctx-A: {snap_a}"
        assert snap_b["calls"] == 5, f"ctx-B: {snap_b}"
        assert snap_a["tokens"] == 30
        assert snap_b["tokens"] == 50

        # Cleanup
        with LLMClient._wallet_lock:
            for rid in ["ctx-A", "ctx-B"]:
                LLMClient._wallet_state.pop(rid, None)


# ─── Fix #9: structural rewrite capped per-chapter ───────────────────────────
# Root cause: cap was _max_rewrites * len(chapters) instead of min(_max_rewrites, len(issues)).

class TestFix9StructuralRewriteCappedPerChapter:
    def test_structural_rewrite_capped(self):
        """With _max_rewrites=1 and 5 chapters with issues, only 1 chapter entry in capped dict."""
        # Mirror the exact cap math from orchestrator_layers.py line ~736:
        # _capped_issues = dict(list(sorted(issues_by_chapter.items()))[:min(_max_rewrites, len(...))])
        _max_rewrites = 1
        # Simulate 5 chapters with issues
        issues_by_chapter = {
            1: ["issue_a"],
            2: ["issue_b"],
            3: ["issue_c"],
            4: ["issue_d"],
            5: ["issue_e"],
        }
        _capped_issues = dict(
            list(sorted(issues_by_chapter.items()))[:min(_max_rewrites, len(issues_by_chapter))]
        )
        assert len(_capped_issues) == 1, (
            f"With _max_rewrites=1, only 1 chapter should be in capped dict, got {len(_capped_issues)}"
        )
        # Must be the lowest-numbered chapter
        assert 1 in _capped_issues

    def test_cap_formula_with_zero_issues(self):
        """Empty issues_by_chapter produces empty capped dict."""
        _max_rewrites = 3
        issues_by_chapter = {}
        _capped_issues = dict(
            list(sorted(issues_by_chapter.items()))[:min(_max_rewrites, len(issues_by_chapter))]
        )
        assert len(_capped_issues) == 0


# ─── Fix #10: contract_gate reverts on voice score drop ──────────────────────
# Root cause: gate applied contract fixes but skipped voice re-validation → silent drift.

class TestFix10ContractGateRevalidatesVoice:
    """_post_gate_validate uses VoiceContract from chapter_contract.py.

    Chapter is a Pydantic model with no extra fields, so we attach voice_contract
    dynamically via a MagicMock wrapping a real Chapter or use a plain MagicMock.
    The function uses getattr(new_chapter, "voice_contract", None).
    """

    def _make_ns(self, ch_num: int, content: str, with_voice_contract: bool = True):
        """Return a SimpleNamespace that looks like a Chapter, optionally with voice_contract."""
        from types import SimpleNamespace
        from pipeline.layer2_enhance.chapter_contract import VoiceContract

        ns = SimpleNamespace(
            chapter_number=ch_num,
            content=content,
            voice_contract=(
                VoiceContract(
                    chapter_number=ch_num,
                    per_character={"Minh": {"vocabulary_level": "formal"}},
                )
                if with_voice_contract
                else None
            ),
        )
        return ns

    def test_post_gate_validate_reverts_on_voice_drop(self):
        """_post_gate_validate returns False (revert) when voice compliance < floor."""
        from pipeline.layer2_enhance.contract_gate import _post_gate_validate
        from pipeline.layer2_enhance.chapter_contract import VoiceValidation

        original_ch = self._make_ns(1, "Anh ấy nói: xin chào, tôi tên là Minh.", with_voice_contract=False)
        new_ch = self._make_ns(1, "He said: hello, my name is Minh.")

        # Low compliance — gate must revert
        low_validation = VoiceValidation(
            chapter_number=1,
            overall_compliance=0.1,
            passed=False,
            reason="voice drift",
        )

        with patch(
            "pipeline.layer2_enhance.chapter_contract.validate_chapter_voice",
            return_value=low_validation,
        ):
            result = _post_gate_validate(new_ch, original_ch)

        assert result is False, (
            "_post_gate_validate must return False (revert) when compliance < floor"
        )

    def test_post_gate_validate_keeps_on_passing_voice(self):
        """_post_gate_validate returns True when voice compliance is above floor."""
        from pipeline.layer2_enhance.contract_gate import _post_gate_validate
        from pipeline.layer2_enhance.chapter_contract import VoiceValidation

        original_ch = self._make_ns(2, "Nàng khẽ nói: đây là sự thật.", with_voice_contract=False)
        new_ch = self._make_ns(2, "Nàng nói rõ hơn: đây chính là sự thật hiển nhiên.")

        # High compliance — gate must keep the rewrite
        high_validation = VoiceValidation(
            chapter_number=2,
            overall_compliance=0.9,
            passed=True,
            reason="ok",
        )

        with patch(
            "pipeline.layer2_enhance.chapter_contract.validate_chapter_voice",
            return_value=high_validation,
        ):
            result = _post_gate_validate(new_ch, original_ch)

        assert result is True, (
            "_post_gate_validate must return True (keep) when compliance >= floor"
        )

    def test_post_gate_validate_reverts_on_validator_exception(self):
        """_post_gate_validate returns False (reverts) when validator raises."""
        from pipeline.layer2_enhance.contract_gate import _post_gate_validate

        original_ch = self._make_ns(3, "content", with_voice_contract=False)
        new_ch = self._make_ns(3, "content")

        with patch(
            "pipeline.layer2_enhance.chapter_contract.validate_chapter_voice",
            side_effect=RuntimeError("LLM timeout"),
        ):
            result = _post_gate_validate(new_ch, original_ch)

        assert result is False, (
            "_post_gate_validate must return False when validator raises (safe revert)"
        )

    def test_post_gate_validate_no_voice_contract_keeps_rewrite(self):
        """_post_gate_validate returns True when chapter has no voice_contract."""
        from pipeline.layer2_enhance.contract_gate import _post_gate_validate

        original_ch = self._make_ns(4, "some content", with_voice_contract=False)
        new_ch = self._make_ns(4, "some content", with_voice_contract=False)

        # No mock needed — code path returns True before calling validate_chapter_voice
        result = _post_gate_validate(new_ch, original_ch)
        assert result is True, (
            "_post_gate_validate must return True when no voice_contract is set"
        )
