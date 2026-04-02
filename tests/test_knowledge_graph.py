"""Tests for services/knowledge_graph.py — StoryKnowledgeGraph."""

import json
import os
import tempfile
import types
import unittest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helper: build a graph with pure Python backend regardless of NetworkX
# ---------------------------------------------------------------------------

def _make_pure_python_graph():
    """Return a StoryKnowledgeGraph forced to use the pure Python fallback."""
    import services.knowledge_graph as kg_module
    original = kg_module.HAS_NETWORKX
    kg_module.HAS_NETWORKX = False
    from services.knowledge_graph import StoryKnowledgeGraph
    g = StoryKnowledgeGraph()
    kg_module.HAS_NETWORKX = original
    return g


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestAddNodes(unittest.TestCase):
    def setUp(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        self.kg = StoryKnowledgeGraph()

    def test_add_character(self):
        self.kg.add_character("Alice", {"role": "main"})
        chars = self.kg.get_all_characters()
        names = [c["name"] for c in chars]
        self.assertIn("Alice", names)

    def test_add_character_no_attrs(self):
        self.kg.add_character("Bob")
        chars = self.kg.get_all_characters()
        self.assertEqual(len(chars), 1)

    def test_add_location(self):
        self.kg.add_location("Hanoi")
        self.assertEqual(self.kg.node_count(), 1)

    def test_add_event(self):
        self.kg.add_event("e1", "Big battle", chapter=3)
        events = self.kg.get_chapter_events(3)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["description"], "Big battle")

    def test_add_event_with_characters_creates_edges(self):
        self.kg.add_character("Alice")
        self.kg.add_event("e1", "Alice acts", chapter=1, characters=["Alice"])
        self.assertGreater(self.kg.edge_count(), 0)


class TestAddRelationship(unittest.TestCase):
    def setUp(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        self.kg = StoryKnowledgeGraph()
        self.kg.add_character("Alice")
        self.kg.add_character("Bob")

    def test_add_relationship_increases_edge_count(self):
        self.kg.add_relationship("char:Alice", "char:Bob", "ally", chapter=1)
        self.assertEqual(self.kg.edge_count(), 1)

    def test_get_character_relationships_source(self):
        self.kg.add_relationship("char:Alice", "char:Bob", "ally", chapter=1)
        rels = self.kg.get_character_relationships("Alice")
        self.assertTrue(any(r.get("type") == "ally" for r in rels))

    def test_get_character_relationships_target(self):
        self.kg.add_relationship("char:Alice", "char:Bob", "enemy", chapter=2)
        rels = self.kg.get_character_relationships("Bob")
        self.assertTrue(any(r.get("type") == "enemy" for r in rels))

    def test_get_character_relationships_empty(self):
        self.kg.add_character("Charlie")
        rels = self.kg.get_character_relationships("Charlie")
        self.assertEqual(rels, [])


class TestGetChapterEvents(unittest.TestCase):
    def setUp(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        self.kg = StoryKnowledgeGraph()
        self.kg.add_event("e1", "Chapter 1 event", chapter=1)
        self.kg.add_event("e2", "Chapter 2 event", chapter=2)
        self.kg.add_event("e3", "Another chapter 1", chapter=1)

    def test_chapter1_has_two_events(self):
        events = self.kg.get_chapter_events(1)
        self.assertEqual(len(events), 2)

    def test_chapter2_has_one_event(self):
        events = self.kg.get_chapter_events(2)
        self.assertEqual(len(events), 1)

    def test_chapter99_is_empty(self):
        events = self.kg.get_chapter_events(99)
        self.assertEqual(events, [])


class TestGetCharacterTimeline(unittest.TestCase):
    def setUp(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        self.kg = StoryKnowledgeGraph()
        self.kg.add_character("Alice")
        self.kg.add_event("e3", "Late event", chapter=3, characters=["Alice"])
        self.kg.add_event("e1", "Early event", chapter=1, characters=["Alice"])
        self.kg.add_event("e2", "Middle event", chapter=2, characters=["Alice"])

    def test_timeline_sorted_by_chapter(self):
        timeline = self.kg.get_character_timeline("Alice")
        chapters = [t["chapter"] for t in timeline]
        self.assertEqual(chapters, sorted(chapters))

    def test_timeline_contains_all_events(self):
        timeline = self.kg.get_character_timeline("Alice")
        self.assertEqual(len(timeline), 3)

    def test_timeline_empty_for_unknown_char(self):
        timeline = self.kg.get_character_timeline("Nobody")
        self.assertEqual(timeline, [])


class TestGetAllCharacters(unittest.TestCase):
    def setUp(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        self.kg = StoryKnowledgeGraph()

    def test_empty_graph(self):
        self.assertEqual(self.kg.get_all_characters(), [])

    def test_characters_only(self):
        self.kg.add_character("Alice")
        self.kg.add_location("Hanoi")
        chars = self.kg.get_all_characters()
        self.assertEqual(len(chars), 1)
        self.assertEqual(chars[0]["name"], "Alice")


class TestNodeEdgeCount(unittest.TestCase):
    def setUp(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        self.kg = StoryKnowledgeGraph()

    def test_empty_graph_counts(self):
        self.assertEqual(self.kg.node_count(), 0)
        self.assertEqual(self.kg.edge_count(), 0)

    def test_counts_after_add(self):
        self.kg.add_character("Alice")
        self.kg.add_character("Bob")
        self.kg.add_relationship("char:Alice", "char:Bob", "ally")
        self.assertEqual(self.kg.node_count(), 2)
        self.assertEqual(self.kg.edge_count(), 1)


class TestToSummary(unittest.TestCase):
    def setUp(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        self.kg = StoryKnowledgeGraph()

    def test_summary_contains_header(self):
        summary = self.kg.to_summary()
        self.assertIn("KNOWLEDGE GRAPH", summary)

    def test_summary_respects_max_chars(self):
        for i in range(20):
            self.kg.add_character(f"Char{i}", {"role": "x" * 200})
        summary = self.kg.to_summary(max_chars=100)
        self.assertLessEqual(len(summary), 100)

    def test_summary_includes_character_names(self):
        self.kg.add_character("Alice")
        self.kg.add_character("Bob")
        summary = self.kg.to_summary()
        self.assertIn("Alice", summary)
        self.assertIn("Bob", summary)

    def test_summary_includes_relationships(self):
        self.kg.add_character("Alice")
        self.kg.add_character("Bob")
        self.kg.add_relationship("char:Alice", "char:Bob", "enemy")
        summary = self.kg.to_summary()
        self.assertIn("enemy", summary)


class TestSaveLoad(unittest.TestCase):
    def test_save_load_roundtrip(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        kg = StoryKnowledgeGraph()
        kg.add_character("Alice", {"role": "hero"})
        kg.add_location("Hanoi")
        kg.add_event("e1", "Big fight", chapter=2, characters=["Alice"])

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name

        try:
            kg.save(path)
            kg2 = StoryKnowledgeGraph().load(path)
            chars = kg2.get_all_characters()
            names = [c["name"] for c in chars]
            self.assertIn("Alice", names)
            self.assertGreater(kg2.node_count(), 0)
        finally:
            os.unlink(path)

    def test_save_creates_file(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        kg = StoryKnowledgeGraph()
        kg.add_character("Test")
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            kg.save(path)
            self.assertTrue(os.path.exists(path))
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("nodes", data)
            self.assertIn("edges", data)
        finally:
            os.unlink(path)


class TestBuildFromStoryDraft(unittest.TestCase):
    def _make_mock_draft(self):
        """Build a minimal mock StoryDraft-like object."""
        char = types.SimpleNamespace(
            name="Alice",
            role="main",
            personality="brave",
            background="warrior",
            relationships=["Bob: ally", "no-colon-here"],
        )
        char2 = types.SimpleNamespace(
            name="Bob",
            role="side",
            personality="wise",
            background="mage",
            relationships=[],
        )
        plot_event = types.SimpleNamespace(
            event="Great battle",
            chapter_number=1,
            characters_involved=["Alice", "Bob"],
        )
        draft = types.SimpleNamespace(
            characters=[char, char2],
            plot_events=[plot_event],
            story_context=None,
        )
        return draft

    def test_characters_added(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        draft = self._make_mock_draft()
        kg = StoryKnowledgeGraph().build_from_story_draft(draft)
        names = [c["name"] for c in kg.get_all_characters()]
        self.assertIn("Alice", names)
        self.assertIn("Bob", names)

    def test_plot_events_added(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        draft = self._make_mock_draft()
        kg = StoryKnowledgeGraph().build_from_story_draft(draft)
        events = kg.get_chapter_events(1)
        self.assertEqual(len(events), 1)

    def test_relationships_parsed(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        draft = self._make_mock_draft()
        kg = StoryKnowledgeGraph().build_from_story_draft(draft)
        rels = kg.get_character_relationships("Alice")
        # Should have related_to Bob + involved_in event
        types_found = {r.get("type") for r in rels}
        self.assertIn("related_to", types_found)

    def test_story_context_states(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        state = types.SimpleNamespace(name="Alice", mood="happy", arc_position="rising", last_action="fought")
        ctx = types.SimpleNamespace(
            plot_events=[],
            character_states=[state],
        )
        draft = types.SimpleNamespace(characters=[], plot_events=[], story_context=ctx)
        kg = StoryKnowledgeGraph().build_from_story_draft(draft)
        chars = kg.get_all_characters()
        self.assertTrue(any(c["name"] == "Alice" for c in chars))

    def test_empty_draft(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        draft = types.SimpleNamespace(characters=[], plot_events=[], story_context=None)
        kg = StoryKnowledgeGraph().build_from_story_draft(draft)
        self.assertEqual(kg.node_count(), 0)


class TestPurePythonFallback(unittest.TestCase):
    """Force pure Python fallback and verify all operations work."""

    def setUp(self):
        """Patch HAS_NETWORKX=False for the entire test method."""
        import services.knowledge_graph as kg_module
        self._patcher = patch.object(kg_module, "HAS_NETWORKX", False)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def _kg(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        return StoryKnowledgeGraph()

    def test_add_character_fallback(self):
        kg = self._kg()
        kg.add_character("Alice")
        self.assertEqual(len(kg.get_all_characters()), 1)

    def test_add_location_fallback(self):
        kg = self._kg()
        kg.add_location("Saigon")
        self.assertEqual(kg.node_count(), 1)

    def test_add_event_fallback(self):
        kg = self._kg()
        kg.add_event("e1", "Test event", chapter=1)
        events = kg.get_chapter_events(1)
        self.assertEqual(len(events), 1)

    def test_add_relationship_fallback(self):
        kg = self._kg()
        kg.add_character("A")
        kg.add_character("B")
        kg.add_relationship("char:A", "char:B", "ally")
        rels = kg.get_character_relationships("A")
        self.assertTrue(any(r.get("type") == "ally" for r in rels))

    def test_edge_count_fallback(self):
        kg = self._kg()
        kg.add_character("A")
        kg.add_character("B")
        kg.add_relationship("char:A", "char:B", "enemy")
        kg.add_relationship("char:A", "char:B", "ally")
        self.assertEqual(kg.edge_count(), 2)

    def test_timeline_fallback(self):
        kg = self._kg()
        kg.add_character("Alice")
        kg.add_event("e2", "Later", chapter=2, characters=["Alice"])
        kg.add_event("e1", "Earlier", chapter=1, characters=["Alice"])
        timeline = kg.get_character_timeline("Alice")
        chapters = [t["chapter"] for t in timeline]
        self.assertEqual(chapters, sorted(chapters))

    def test_to_summary_fallback(self):
        kg = self._kg()
        kg.add_character("Alice")
        summary = kg.to_summary()
        self.assertIn("Alice", summary)

    def test_save_load_fallback(self):
        kg = self._kg()
        kg.add_character("Alice", {"role": "hero"})
        kg.add_event("e1", "Fight", chapter=1, characters=["Alice"])

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = f.name
        try:
            kg.save(path)
            kg2 = self._kg()
            kg2.load(path)
            self.assertGreater(kg2.node_count(), 0)
        finally:
            os.unlink(path)


class TestEmptyGraphOperations(unittest.TestCase):
    def setUp(self):
        from services.knowledge_graph import StoryKnowledgeGraph
        self.kg = StoryKnowledgeGraph()

    def test_get_all_characters_empty(self):
        self.assertEqual(self.kg.get_all_characters(), [])

    def test_get_chapter_events_empty(self):
        self.assertEqual(self.kg.get_chapter_events(1), [])

    def test_get_character_relationships_empty(self):
        self.assertEqual(self.kg.get_character_relationships("Nobody"), [])

    def test_get_character_timeline_empty(self):
        self.assertEqual(self.kg.get_character_timeline("Nobody"), [])

    def test_node_count_zero(self):
        self.assertEqual(self.kg.node_count(), 0)

    def test_edge_count_zero(self):
        self.assertEqual(self.kg.edge_count(), 0)

    def test_to_summary_empty(self):
        summary = self.kg.to_summary()
        self.assertIn("KNOWLEDGE GRAPH", summary)


class TestPipelineOutputField(unittest.TestCase):
    def test_knowledge_graph_summary_field_exists(self):
        from models.schemas import PipelineOutput
        output = PipelineOutput()
        self.assertTrue(hasattr(output, "knowledge_graph_summary"))
        self.assertEqual(output.knowledge_graph_summary, "")

    def test_field_accepts_string(self):
        from models.schemas import PipelineOutput
        output = PipelineOutput(knowledge_graph_summary="test summary")
        self.assertEqual(output.knowledge_graph_summary, "test summary")


if __name__ == "__main__":
    unittest.main()
