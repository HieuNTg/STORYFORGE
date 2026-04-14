"""Tests for Layer 2 Consistency Engine (A-E improvements)."""

from unittest.mock import MagicMock, patch

from pipeline.layer2_enhance.character_state_registry import (
    CharacterState, CharacterStateRegistry,
)
from pipeline.layer2_enhance.setting_continuity import (
    Location, SignificantObject, SettingContinuityGraph,
)
from pipeline.layer2_enhance.thread_watchdog import PlotThread, ThreadWatchdog
from pipeline.layer2_enhance.voice_fingerprint import VoiceProfile, VoiceFingerprintEngine
from pipeline.layer2_enhance.consistency_engine import (
    ConsistencyEngine, ConsistencyViolation, ConsistencyReport,
)


class TestCharacterStateRegistry:
    """Test character state tracking."""

    def test_character_state_model(self):
        state = CharacterState(
            name="An",
            chapter_number=1,
            location="Tử Cấm Thành",
            physical_state="khỏe mạnh",
            emotional_state="lo lắng",
        )
        assert state.name == "An"
        assert state.location == "Tử Cấm Thành"

    def test_registry_stores_states(self):
        registry = CharacterStateRegistry()
        registry.states["An"] = {
            1: CharacterState(name="An", chapter_number=1, location="Kinh thành"),
            2: CharacterState(name="An", chapter_number=2, location="Rừng sâu"),
        }

        state = registry.get_state("An", 1)
        assert state is not None
        assert state.location == "Kinh thành"

    def test_get_last_known_state(self):
        registry = CharacterStateRegistry()
        registry.states["An"] = {
            1: CharacterState(name="An", chapter_number=1, location="A"),
            3: CharacterState(name="An", chapter_number=3, location="B"),
        }

        # Before chapter 5, last known is chapter 3
        state = registry.get_last_known_state("An", 5)
        assert state is not None
        assert state.location == "B"

        # Before chapter 2, last known is chapter 1
        state = registry.get_last_known_state("An", 2)
        assert state is not None
        assert state.location == "A"

    def test_format_constraints(self):
        registry = CharacterStateRegistry()
        registry.states["An"] = {
            1: CharacterState(
                name="An",
                chapter_number=1,
                location="Kinh thành",
                physical_state="bị thương vai trái",
                emotional_state="tức giận",
            ),
        }

        constraints = registry.format_constraints_for_chapter(2)
        assert "An" in constraints
        assert "Kinh thành" in constraints
        assert "bị thương" in constraints


class TestSettingContinuityGraph:
    """Test setting/location tracking."""

    def test_location_model(self):
        loc = Location(
            name="Tử Cấm Thành",
            description="Hoàng cung",
            introduced_chapter=1,
            accessible_from=["Kinh thành"],
        )
        assert loc.name == "Tử Cấm Thành"
        assert "Kinh thành" in loc.accessible_from

    def test_significant_object_model(self):
        obj = SignificantObject(
            name="Thanh Long Kiếm",
            description="Bảo kiếm cổ",
            introduced_chapter=2,
            current_owner="An",
        )
        assert obj.name == "Thanh Long Kiếm"
        assert obj.current_owner == "An"

    def test_is_transition_valid(self):
        graph = SettingContinuityGraph()
        graph.locations = {
            "A": Location(name="A", accessible_from=["B", "C"]),
            "B": Location(name="B", accessible_from=["A"]),
            "C": Location(name="C", accessible_from=["A"]),
        }

        assert graph.is_transition_valid("A", "B") is True
        assert graph.is_transition_valid("B", "A") is True
        assert graph.is_transition_valid("B", "C") is False  # Not directly connected
        assert graph.is_transition_valid("", "A") is True  # Unknown location = valid

    def test_mark_object_destroyed(self):
        graph = SettingContinuityGraph()
        graph.objects["Thanh Long Kiếm"] = SignificantObject(
            name="Thanh Long Kiếm",
            introduced_chapter=1,
        )

        graph.mark_object_destroyed("Thanh Long Kiếm", 5)
        assert graph.objects["Thanh Long Kiếm"].destroyed is True
        assert graph.objects["Thanh Long Kiếm"].destroyed_chapter == 5


class TestThreadWatchdog:
    """Test plot thread tracking."""

    def test_plot_thread_model(self):
        thread = PlotThread(
            thread_id="t1",
            description="Bí mật về thân thế An",
            introduced_chapter=1,
            expected_resolution_chapter=10,
            importance="critical",
        )
        assert thread.status == "open"
        assert thread.importance == "critical"

    def test_add_thread(self):
        watchdog = ThreadWatchdog()
        tid = watchdog.add_thread(
            description="Bí mật mới",
            introduced_chapter=3,
            importance="normal",
        )

        assert tid in watchdog.threads
        assert watchdog.threads[tid].description == "Bí mật mới"

    def test_get_open_threads(self):
        watchdog = ThreadWatchdog()
        watchdog.threads = {
            "t1": PlotThread(thread_id="t1", description="Open", status="open"),
            "t2": PlotThread(thread_id="t2", description="Resolved", status="resolved"),
            "t3": PlotThread(thread_id="t3", description="Progressing", status="progressing"),
        }

        open_threads = watchdog.get_open_threads()
        assert len(open_threads) == 2
        assert all(t.status in ("open", "progressing") for t in open_threads)

    def test_format_constraints_critical_deadline(self):
        watchdog = ThreadWatchdog()
        watchdog.threads = {
            "t1": PlotThread(
                thread_id="t1",
                description="Phải giải quyết ngay",
                status="open",
                expected_resolution_chapter=5,
                importance="critical",
            ),
        }

        # At chapter 5 (deadline), thread should be marked critical
        constraints = watchdog.format_constraints_for_chapter(5, total_chapters=10)
        assert "CRITICAL" in constraints
        assert "Phải giải quyết ngay" in constraints


class TestVoiceFingerprintEngine:
    """Test voice/dialogue tracking."""

    def test_voice_profile_model(self):
        profile = VoiceProfile(
            name="An",
            vocabulary_level="sophisticated",
            formality="formal",
            speech_quirks=["hay nói 'thật ra'"],
        )
        assert profile.name == "An"
        assert profile.vocabulary_level == "sophisticated"

    def test_extract_dialogues_pattern(self):
        engine = VoiceFingerprintEngine()
        content = '''
        "Ta sẽ không bỏ cuộc!" - An nói.
        An quát lên: "Các ngươi dừng lại!"
        '''

        dialogues = engine._extract_dialogues(content, "An")
        assert len(dialogues) >= 1  # Should extract at least one dialogue

    def test_compute_avg_sentence_length(self):
        engine = VoiceFingerprintEngine()
        dialogues = [
            "Đây là câu ngắn.",
            "Đây là một câu dài hơn với nhiều từ.",
        ]

        avg_len = engine._compute_avg_sentence_length(dialogues)
        assert avg_len > 0

    def test_get_character_voice_guidance(self):
        engine = VoiceFingerprintEngine()
        engine.profiles["An"] = VoiceProfile(
            name="An",
            vocabulary_level="simple",
            formality="casual",
            emotional_expression="expressive",
            speech_quirks=["hay nói 'thật ra'"],
        )

        guidance = engine.get_character_voice_guidance("An")
        assert "đơn giản" in guidance or "thoải mái" in guidance


class TestConsistencyEngine:
    """Test the main consistency engine."""

    def test_consistency_violation_model(self):
        v = ConsistencyViolation(
            type="character_state",
            subtype="location_continuity",
            chapter=3,
            severity="warning",
            description="An teleported from A to B",
        )
        assert v.type == "character_state"
        assert v.severity == "warning"

    def test_consistency_report_model(self):
        report = ConsistencyReport(
            total_violations=5,
            critical_count=1,
            warning_count=4,
        )
        assert report.total_violations == 5

    def test_engine_initialization(self):
        engine = ConsistencyEngine()
        assert engine.state_registry is not None
        assert engine.setting_graph is not None
        assert engine.thread_watchdog is not None
        assert engine.voice_engine is not None

    def test_get_constraints_returns_empty_when_not_built(self):
        engine = ConsistencyEngine()
        # Not built yet
        constraints = engine.get_constraints_for_chapter(1)
        assert constraints == ""

    @patch.object(CharacterStateRegistry, "build_from_draft")
    @patch.object(SettingContinuityGraph, "build_from_draft")
    @patch.object(ThreadWatchdog, "load_from_draft")
    @patch.object(VoiceFingerprintEngine, "build_from_draft")
    def test_build_from_draft(
        self,
        mock_voice,
        mock_thread,
        mock_setting,
        mock_state,
    ):
        engine = ConsistencyEngine()

        # Mock draft
        draft = MagicMock()
        draft.chapters = [MagicMock(chapter_number=1, content="Test")]
        draft.characters = [MagicMock(name="An")]

        # Each build method returns self
        mock_state.return_value = engine.state_registry
        mock_setting.return_value = engine.setting_graph
        mock_thread.return_value = engine.thread_watchdog
        mock_voice.return_value = engine.voice_engine

        engine.build_from_draft(draft)

        assert engine._built is True
        mock_state.assert_called_once()
        mock_setting.assert_called_once()
        mock_thread.assert_called_once()
        mock_voice.assert_called_once()

    def test_get_final_report(self):
        engine = ConsistencyEngine()
        engine._built = True

        report = engine.get_final_report()
        assert isinstance(report, ConsistencyReport)


class TestIntegration:
    """Integration tests for consistency engine with mock LLM."""

    @patch("pipeline.layer2_enhance.character_state_registry.LLMClient")
    def test_state_extraction_with_mock_llm(self, mock_llm_class):
        mock_llm = MagicMock()
        mock_llm.generate_json.return_value = {
            "location": "Kinh thành",
            "physical_state": "khỏe mạnh",
            "emotional_state": "vui vẻ",
            "inventory": [],
            "companions": ["Bình"],
            "goals_active": [],
            "secrets_revealed": [],
        }
        mock_llm_class.return_value = mock_llm

        registry = CharacterStateRegistry()
        states = registry.extract_states_from_chapter(
            chapter_content="An đi bộ trong Kinh thành cùng Bình.",
            chapter_number=1,
            character_names=["An"],
        )

        assert len(states) == 1
        assert states[0].location == "Kinh thành"
        assert "Bình" in states[0].companions
