"""Tests for services/story_brancher.py — coverage for StoryBrancher class."""
import json
import os
import pytest
import tempfile
from unittest.mock import MagicMock, patch, mock_open
from models.schemas import Chapter, StoryNode, BranchChoice, StoryTree
from services.story_brancher import StoryBrancher, BRANCHES_DIR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chapter(number: int = 1, title: str = "Test Ch", content: str = "Chapter content here.") -> Chapter:
    return Chapter(chapter_number=number, title=title, content=content)


def _make_tree(title: str = "Test Story", genre: str = "tien_hiep") -> StoryTree:
    root = StoryNode(
        node_id="root",
        chapter_number=1,
        title="Root",
        content="Root content",
    )
    return StoryTree(root_id="root", nodes={"root": root}, title=title, genre=genre)


def _make_brancher_with_mock_llm():
    with patch("services.story_brancher.LLMClient") as MockLLM:
        mock_llm = MockLLM.return_value
        brancher = StoryBrancher()
        brancher.llm = mock_llm
        return brancher, mock_llm


# ---------------------------------------------------------------------------
# create_tree_from_chapter
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCreateTreeFromChapter:
    def test_creates_tree_with_root(self):
        with patch("services.story_brancher.LLMClient"):
            brancher = StoryBrancher()
        ch = _make_chapter(3, "Opening", "Long content here.")
        tree = brancher.create_tree_from_chapter(ch, "fantasy")
        assert tree.root_id == "root"
        assert "root" in tree.nodes
        assert tree.nodes["root"].content == "Long content here."
        assert tree.genre == "fantasy"
        assert tree.title == "Opening"

    def test_tree_chapter_number(self):
        with patch("services.story_brancher.LLMClient"):
            brancher = StoryBrancher()
        ch = _make_chapter(5, "Middle", "Some content")
        tree = brancher.create_tree_from_chapter(ch, "romance")
        assert tree.nodes["root"].chapter_number == 5


# ---------------------------------------------------------------------------
# generate_choices
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGenerateChoices:
    def test_returns_choices(self):
        brancher, mock_llm = _make_brancher_with_mock_llm()
        mock_llm.generate_json.return_value = {
            "choices": [
                {"text": "Go north", "direction": "Adventure path"},
                {"text": "Go south", "direction": "Danger path"},
            ]
        }
        tree = _make_tree()
        choices = brancher.generate_choices(tree, "root")
        assert len(choices) == 2
        assert choices[0].text == "Go north"
        assert choices[1].text == "Go south"

    def test_unknown_node_returns_empty(self):
        brancher, _ = _make_brancher_with_mock_llm()
        tree = _make_tree()
        result = brancher.generate_choices(tree, "nonexistent_node")
        assert result == []

    def test_llm_exception_returns_empty(self):
        brancher, mock_llm = _make_brancher_with_mock_llm()
        mock_llm.generate_json.side_effect = Exception("LLM error")
        tree = _make_tree()
        result = brancher.generate_choices(tree, "root")
        assert result == []

    def test_choices_capped_at_three(self):
        brancher, mock_llm = _make_brancher_with_mock_llm()
        mock_llm.generate_json.return_value = {
            "choices": [
                {"text": f"Choice {i}", "direction": f"Dir {i}"} for i in range(5)
            ]
        }
        tree = _make_tree()
        choices = brancher.generate_choices(tree, "root")
        assert len(choices) <= 3

    def test_choices_have_unique_ids(self):
        brancher, mock_llm = _make_brancher_with_mock_llm()
        mock_llm.generate_json.return_value = {
            "choices": [
                {"text": "A", "direction": "dir_a"},
                {"text": "B", "direction": "dir_b"},
            ]
        }
        tree = _make_tree()
        choices = brancher.generate_choices(tree, "root")
        ids = [c.choice_id for c in choices]
        assert len(ids) == len(set(ids))

    def test_choices_stored_on_node(self):
        brancher, mock_llm = _make_brancher_with_mock_llm()
        mock_llm.generate_json.return_value = {
            "choices": [{"text": "X", "direction": "dir_x"}]
        }
        tree = _make_tree()
        choices = brancher.generate_choices(tree, "root")
        assert tree.nodes["root"].choices == choices


# ---------------------------------------------------------------------------
# generate_branch
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGenerateBranch:
    def test_creates_new_node(self):
        brancher, mock_llm = _make_brancher_with_mock_llm()
        mock_llm.generate.return_value = "  New branch content.  "
        tree = _make_tree()
        choice = BranchChoice(
            choice_id="root_c0",
            text="Go east",
            next_node_id="",
            state_delta={"direction": "Eastern path"},
        )
        new_node = brancher.generate_branch(tree, "root", choice)
        assert new_node.content == "New branch content."
        assert new_node.parent_id == "root"
        assert new_node.chapter_number == 2  # parent ch 1 + 1
        assert new_node.node_id in tree.nodes

    def test_raises_on_missing_parent(self):
        brancher, _ = _make_brancher_with_mock_llm()
        tree = _make_tree()
        choice = BranchChoice(choice_id="x_c0", text="X", next_node_id="", state_delta={})
        with pytest.raises(ValueError, match="not found"):
            brancher.generate_branch(tree, "nonexistent", choice)

    def test_llm_error_uses_fallback_content(self):
        brancher, mock_llm = _make_brancher_with_mock_llm()
        mock_llm.generate.side_effect = Exception("LLM error")
        tree = _make_tree()
        choice = BranchChoice(choice_id="root_c0", text="Go", next_node_id="", state_delta={})
        new_node = brancher.generate_branch(tree, "root", choice)
        assert "Loi" in new_node.content or "loi" in new_node.content.lower()

    def test_updates_current_node_id(self):
        brancher, mock_llm = _make_brancher_with_mock_llm()
        mock_llm.generate.return_value = "Content"
        tree = _make_tree()
        choice = BranchChoice(choice_id="root_c0", text="Go", next_node_id="", state_delta={})
        new_node = brancher.generate_branch(tree, "root", choice)
        assert tree.current_node_id == new_node.node_id
        assert choice.next_node_id == new_node.node_id


# ---------------------------------------------------------------------------
# save_tree / load_tree
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSaveLoadTree:
    def test_save_and_load_roundtrip(self, tmp_path):
        tree = _make_tree("My Story", "fantasy")
        filename = "test_tree.json"
        save_path = str(tmp_path / filename)

        with patch("services.story_brancher.BRANCHES_DIR", str(tmp_path)):
            path = StoryBrancher.save_tree(tree, filename)

        assert os.path.isfile(path)
        loaded = StoryBrancher.load_tree(path)
        assert loaded.title == "My Story"
        assert "root" in loaded.nodes

    def test_save_auto_filename(self, tmp_path):
        tree = _make_tree("Auto Title")
        with patch("services.story_brancher.BRANCHES_DIR", str(tmp_path)):
            path = StoryBrancher.save_tree(tree)  # no filename
        assert os.path.isfile(path)
        assert path.endswith(".json")

    def test_load_corrupt_file_raises(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json", encoding="utf-8")
        with pytest.raises(ValueError, match="Corrupt"):
            StoryBrancher.load_tree(str(bad_file))

    def test_load_missing_root_id_raises(self, tmp_path):
        bad_file = tmp_path / "missing.json"
        bad_file.write_text(json.dumps({"nodes": {}}), encoding="utf-8")
        with pytest.raises(ValueError, match="missing required"):
            StoryBrancher.load_tree(str(bad_file))


# ---------------------------------------------------------------------------
# list_saved_trees
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestListSavedTrees:
    def test_empty_if_dir_missing(self):
        with patch("services.story_brancher.BRANCHES_DIR", "/nonexistent/path/xyz"):
            result = StoryBrancher.list_saved_trees()
        assert result == []

    def test_lists_json_files(self, tmp_path):
        tree = _make_tree("Story A")
        data = tree.model_dump()
        (tmp_path / "story_a.json").write_text(json.dumps(data), encoding="utf-8")
        (tmp_path / "not_json.txt").write_text("ignore me", encoding="utf-8")

        with patch("services.story_brancher.BRANCHES_DIR", str(tmp_path)):
            result = StoryBrancher.list_saved_trees()

        assert len(result) == 1
        assert "Story A" in result[0][0]

    def test_handles_corrupt_json_gracefully(self, tmp_path):
        (tmp_path / "bad.json").write_text("corrupt", encoding="utf-8")
        with patch("services.story_brancher.BRANCHES_DIR", str(tmp_path)):
            result = StoryBrancher.list_saved_trees()
        # Should not raise; falls back to filename as display name
        assert len(result) == 1
        assert result[0][0] == "bad.json"
