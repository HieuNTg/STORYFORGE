"""Tests for story branch persistence."""
import os
from models.schemas import StoryTree, StoryNode


class TestBranchPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        from services.story_brancher import StoryBrancher
        import services.story_brancher as sb

        tree = StoryTree(
            root_id="root",
            nodes={"root": StoryNode(
                node_id="root", chapter_number=1,
                title="Test", content="Hello"
            )},
            title="Test Story", genre="fantasy",
        )
        orig_dir = sb.BRANCHES_DIR
        sb.BRANCHES_DIR = str(tmp_path)
        try:
            path = StoryBrancher.save_tree(tree)
            assert os.path.exists(path)
            loaded = StoryBrancher.load_tree(path)
            assert loaded.title == "Test Story"
            assert "root" in loaded.nodes
            assert loaded.nodes["root"].content == "Hello"
        finally:
            sb.BRANCHES_DIR = orig_dir

    def test_list_saved_trees(self, tmp_path):
        from services.story_brancher import StoryBrancher
        import services.story_brancher as sb

        orig_dir = sb.BRANCHES_DIR
        sb.BRANCHES_DIR = str(tmp_path)
        try:
            tree = StoryTree(
                root_id="r", nodes={"r": StoryNode(
                    node_id="r", chapter_number=1, title="T", content="C"
                )},
                title="My Tree", genre="sci-fi",
            )
            StoryBrancher.save_tree(tree)
            trees = StoryBrancher.list_saved_trees()
            assert len(trees) == 1
            assert "My Tree" in trees[0][0]
        finally:
            sb.BRANCHES_DIR = orig_dir

    def test_list_empty_dir(self, tmp_path):
        from services.story_brancher import StoryBrancher
        import services.story_brancher as sb

        orig_dir = sb.BRANCHES_DIR
        sb.BRANCHES_DIR = str(tmp_path / "nonexistent")
        try:
            assert StoryBrancher.list_saved_trees() == []
        finally:
            sb.BRANCHES_DIR = orig_dir
