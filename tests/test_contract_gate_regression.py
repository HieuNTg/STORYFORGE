"""Regression tests: the post-L2 contract gate must actually inspect chapters.

`SceneEnhancer` rebuilt each Chapter by listing fields by hand, which dropped
`contract`. `apply_contract_gate` skips any chapter whose contract is None, so
every chapter was skipped — while the gate reported "0 vi phạm" over the full
chapter count and the run looked clean.

The related defect: `_post_gate_validate` read `new_chapter.voice_contract`, an
attribute Chapter has never declared, so the voice re-validation it advertises
always short-circuited to True.
"""

from unittest.mock import MagicMock, patch

from models.narrative_schemas import ChapterContract
from models.schemas import Chapter
from pipeline.layer2_enhance.contract_gate import (
    _post_gate_validate,
    apply_contract_gate,
    verify_contract,
)


def _chapter_with_contract(n=1, content="Lan bước vào khu rừng."):
    contract = ChapterContract(
        chapter_number=n,
        must_mention_characters=["Lan", "Minh"],
    )
    return Chapter(
        chapter_number=n,
        title=f"Chương {n}",
        content=content,
        word_count=len(content.split()),
        summary="tóm tắt",
        contract=contract,
    )


class TestChapterCarriesContractThroughEnhancement:
    def test_chapter_model_has_no_voice_contract_attribute(self):
        """Pins the premise of the _post_gate_validate defect."""
        assert "voice_contract" not in Chapter.model_fields

    def test_scene_enhancer_preserves_contract_when_no_weak_scenes(self):
        """The no-weak-scenes path returns a rebuilt Chapter; it must keep `contract`."""
        from pipeline.layer2_enhance.scene_enhancer import SceneEnhancer, SceneScore

        chapter = _chapter_with_contract()
        enhancer = SceneEnhancer.__new__(SceneEnhancer)  # no LLM wiring needed

        scenes = [{"scene_number": 1, "content": "Lan và Minh gặp nhau."}]
        # needs_enhancement=False → the early-return path that rebuilds the Chapter.
        scores = [SceneScore(scene_number=1)]

        result = enhancer.enhance_weak_scenes(
            chapter=chapter,
            scenes=scenes,
            scores=scores,
            sim_result=MagicMock(),
            genre="hiện đại",
        )

        assert result.contract is not None, "contract dropped during enhancement"
        assert result.contract.chapter_number == chapter.contract.chapter_number
        assert result.summary == chapter.summary


class TestGateReportsWhatItActuallyChecked:
    def test_violation_is_detected_when_contract_survives(self):
        """A chapter missing a required character must produce failures."""
        chapter = _chapter_with_contract(content="Lan đi một mình.")  # no "Minh"
        failures = verify_contract(chapter, chapter.contract, [])
        assert any(f.field == "must_mention_characters" for f in failures)

    def test_chapters_without_contract_are_not_counted_as_checked(self):
        """The false-green bug: skipped chapters used to inflate chapters_checked."""
        story = MagicMock()
        story.chapters = [
            Chapter(
                chapter_number=1,
                title="C1",
                content="nội dung",
                word_count=2,
                summary="s",
            )
        ]  # no contract

        stats = apply_contract_gate(MagicMock(), story, [], enabled=True)

        assert stats["chapters_checked"] == 0
        assert stats["chapters_skipped_no_contract"] == 1
        assert stats["chapters_total"] == 1

    def test_gate_counts_chapters_that_carry_a_contract(self):
        story = MagicMock()
        story.chapters = [_chapter_with_contract(content="Lan và Minh cùng đi.")]

        stats = apply_contract_gate(MagicMock(), story, [], enabled=True)

        assert stats["chapters_checked"] == 1
        assert stats["chapters_skipped_no_contract"] == 0


class TestPostGateVoiceValidation:
    def test_missing_contract_keeps_the_rewrite(self):
        ch = _chapter_with_contract()
        assert _post_gate_validate(ch, ch, None) is True

    @patch("services.llm_client.LLMClient")
    @patch("pipeline.layer2_enhance.chapter_contract.validate_chapter_voice")
    def test_supplied_contract_is_actually_validated(self, mock_validate, _mock_llm):
        """Previously unreachable: the voice check never ran at all."""
        mock_validate.return_value = MagicMock(overall_compliance=0.1)
        ch = _chapter_with_contract()

        contract = MagicMock()
        keep = _post_gate_validate(ch, ch, contract)

        assert mock_validate.called, "voice validation never ran"
        assert keep is False, "a below-floor rewrite must be reverted"
