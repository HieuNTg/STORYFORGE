"""Integration tests for pipeline layer transitions."""
from unittest.mock import MagicMock, patch
from models.schemas import (
    StoryDraft, EnhancedStory, Chapter, Character,
    VideoScript,
)


def _make_draft(n_chapters=2) -> StoryDraft:
    chapters = [
        Chapter(chapter_number=i, title=f"Chapter {i}",
                content=f"Content for chapter {i}. " * 50, word_count=200)
        for i in range(1, n_chapters + 1)
    ]
    characters = [
        Character(name="Hero", role="main", personality="brave",
                  background="orphan", motivation="save world")
    ]
    return StoryDraft(title="Test Story", genre="fantasy",
                      chapters=chapters, characters=characters)


class TestLayerTransitions:
    def test_empty_draft_stops_pipeline(self):
        """Pipeline should stop if Layer 1 produces empty chapters."""
        from pipeline.orchestrator import PipelineOrchestrator
        orch = PipelineOrchestrator()

        with patch('services.llm_client.LLMClient.check_connection', return_value=(True, "ok")), \
             patch.object(orch.story_gen, 'generate_full_story') as mock_gen:
            mock_gen.return_value = StoryDraft(
                title="Empty", genre="test", chapters=[]
            )
            result = orch.run_full_pipeline(
                title="Test", genre="test", idea="test",
                enable_agents=False, enable_scoring=False,
            )
            assert result.status == "error"

    def test_layer2_fallback_preserves_chapters(self):
        """When Layer 2 fails, enhanced story should have Layer 1 chapters."""
        from pipeline.orchestrator import PipelineOrchestrator
        orch = PipelineOrchestrator()
        draft = _make_draft(2)

        with patch('services.llm_client.LLMClient.check_connection', return_value=(True, "ok")), \
             patch.object(orch.story_gen, 'generate_full_story', return_value=draft), \
             patch.object(orch.analyzer, 'analyze', side_effect=Exception("Analysis failed")), \
             patch.object(orch.storyboard_gen, 'generate_full_video_script') as mock_sb:
            mock_sb.return_value = VideoScript(
                title="Test", panels=[], total_duration_seconds=0
            )
            result = orch.run_full_pipeline(
                title="Test", genre="test", idea="test",
                enable_agents=False, enable_scoring=False,
            )
            assert result.enhanced_story is not None
            assert len(result.enhanced_story.chapters) == 2
            assert result.status == "partial"

    def test_layer2_fallback_has_enhancement_notes(self):
        """Layer 2 fallback should include error context."""
        from pipeline.orchestrator import PipelineOrchestrator
        orch = PipelineOrchestrator()
        draft = _make_draft(2)

        with patch('services.llm_client.LLMClient.check_connection', return_value=(True, "ok")), \
             patch.object(orch.story_gen, 'generate_full_story', return_value=draft), \
             patch.object(orch.analyzer, 'analyze', side_effect=Exception("Test error")), \
             patch.object(orch.storyboard_gen, 'generate_full_video_script') as mock_sb:
            mock_sb.return_value = VideoScript(
                title="Test", panels=[], total_duration_seconds=0
            )
            result = orch.run_full_pipeline(
                title="Test", genre="test", idea="test",
                enable_agents=False, enable_scoring=False,
            )
            notes = result.enhanced_story.enhancement_notes
            assert any("Layer 2 skipped" in n for n in notes)

    def test_enable_media_defaults_false(self):
        """Media production should not run by default."""
        from pipeline.orchestrator import PipelineOrchestrator
        orch = PipelineOrchestrator()
        draft = _make_draft(1)
        enhanced = EnhancedStory(
            title="Test", genre="fantasy",
            chapters=draft.chapters, drama_score=0.7,
        )

        with patch('services.llm_client.LLMClient.check_connection', return_value=(True, "ok")), \
             patch.object(orch.story_gen, 'generate_full_story', return_value=draft), \
             patch.object(orch.analyzer, 'analyze', return_value={"relationships": []}), \
             patch.object(orch.simulator, 'run_simulation', return_value=MagicMock()), \
             patch.object(orch.enhancer, 'enhance_with_feedback', return_value=enhanced), \
             patch.object(orch.storyboard_gen, 'generate_full_video_script') as mock_sb, \
             patch.object(orch.media_producer, 'run') as mock_media:
            mock_sb.return_value = VideoScript(
                title="Test", panels=[], total_duration_seconds=0
            )
            orch.run_full_pipeline(
                title="Test", genre="test", idea="test",
                enable_agents=False, enable_scoring=False,
            )
            mock_media.assert_not_called()
