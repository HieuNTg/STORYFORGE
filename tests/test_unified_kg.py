"""Sprint 3 Task 1 — Unified knowledge graph.

Covers:
- New node types: thread, item, conflict
- EdgeType enum + unknown-type fallback to RELATED_TO
- build_unified ingests characters + conflict_web + open_threads + foreshadowing_plan + macro_arcs
- to_dict / from_dict round-trip preserves all node types and typed edges
- StoryDraft.knowledge_graph field exists and accepts dict
- PipelineOutput.knowledge_graph field exists alongside knowledge_graph_summary
"""
from __future__ import annotations

import types
import unittest

from services.knowledge_graph import (
    EdgeType,
    StoryKnowledgeGraph,
    _normalize_edge_type,
)


def _make_unified_draft():
    """Mock StoryDraft-like object spanning all unified-KG inputs."""
    char_a = types.SimpleNamespace(
        name="Linh", role="protagonist", personality="determined",
        background="", relationships=["An: ally"],
    )
    char_b = types.SimpleNamespace(
        name="An", role="antagonist", personality="cold",
        background="", relationships=[],
    )
    conflict = types.SimpleNamespace(
        conflict_id="c1", conflict_type="external",
        characters=["Linh", "An"], description="Power struggle",
        arc_range="1-3", status="active",
    )
    thread_open = types.SimpleNamespace(
        thread_id="t1", description="Lost heirloom",
        status="open", planted_chapter=1,
        involved_characters=["Linh"], last_mentioned_chapter=2,
        resolution_chapter=0,
    )
    thread_resolved = types.SimpleNamespace(
        thread_id="t2", description="Debt settled",
        status="resolved", planted_chapter=1,
        involved_characters=["An"], last_mentioned_chapter=3,
        resolution_chapter=3,
    )
    fs = types.SimpleNamespace(
        hint="Mysterious letter", plant_chapter=1, payoff_chapter=4,
        characters_involved=["Linh"],
    )
    arc = types.SimpleNamespace(
        arc_number=1, name="Rise", chapter_start=1, chapter_end=5,
        central_conflict="power", character_focus=["Linh"],
        resolution="",
    )
    draft = types.SimpleNamespace(
        characters=[char_a, char_b],
        plot_events=[],
        story_context=None,
        conflict_web=[conflict],
        open_threads=[thread_open, thread_resolved],
        foreshadowing_plan=[fs],
        macro_arcs=[arc],
    )
    return draft


class TestEdgeType(unittest.TestCase):
    def test_normalize_passes_known(self):
        self.assertEqual(_normalize_edge_type("ally"), "ally")
        self.assertEqual(_normalize_edge_type(EdgeType.PAYS_OFF.value), "pays_off")

    def test_normalize_unknown_falls_back(self):
        self.assertEqual(_normalize_edge_type("totally-bogus"), EdgeType.RELATED_TO.value)

    def test_edge_type_has_arc_payoff_thread_members(self):
        # Regression guard for Sprint 3 required edges
        for member in ("PAYS_OFF", "RESOLVES_THREAD", "ADVANCES_THREAD",
                       "PART_OF_CONFLICT", "PART_OF_ARC", "PLANTS"):
            self.assertTrue(hasattr(EdgeType, member))


class TestNewNodeTypes(unittest.TestCase):
    def setUp(self):
        self.kg = StoryKnowledgeGraph()

    def test_add_thread(self):
        self.kg.add_thread("t1", {"status": "open"})
        self.assertEqual(self.kg.node_count(), 1)

    def test_add_item(self):
        self.kg.add_item("sword_of_omens")
        self.assertEqual(self.kg.node_count(), 1)

    def test_add_conflict(self):
        self.kg.add_conflict("c1", {"conflict_type": "external"})
        self.assertEqual(self.kg.node_count(), 1)

    def test_unknown_rel_type_falls_back(self):
        self.kg.add_character("A")
        self.kg.add_character("B")
        self.kg.add_relationship("char:A", "char:B", "no-such-type")
        rels = self.kg.get_character_relationships("A")
        self.assertTrue(any(r["type"] == EdgeType.RELATED_TO.value for r in rels))


class TestBuildUnified(unittest.TestCase):
    def setUp(self):
        self.draft = _make_unified_draft()
        self.kg = StoryKnowledgeGraph().build_unified(self.draft)

    def test_characters_ingested(self):
        names = {c["name"] for c in self.kg.get_all_characters()}
        self.assertEqual(names, {"Linh", "An"})

    def test_conflict_nodes_created(self):
        dump = self.kg.to_dict()
        conflict_nodes = [n for n in dump["nodes"] if n.startswith("conflict:")]
        self.assertEqual(conflict_nodes, ["conflict:c1"])

    def test_thread_nodes_created(self):
        dump = self.kg.to_dict()
        thread_nodes = sorted(n for n in dump["nodes"] if n.startswith("thread:"))
        self.assertEqual(thread_nodes, ["thread:t1", "thread:t2"])

    def test_resolved_thread_uses_resolves_edge(self):
        dump = self.kg.to_dict()
        edges_to_t2 = [e for e in dump["edges"] if e["target"] == "thread:t2"]
        self.assertTrue(edges_to_t2, "Expected at least one edge targeting thread:t2")
        self.assertTrue(any(e["type"] == EdgeType.RESOLVES_THREAD.value for e in edges_to_t2))

    def test_open_thread_uses_advances_edge(self):
        dump = self.kg.to_dict()
        edges_to_t1 = [e for e in dump["edges"] if e["target"] == "thread:t1"]
        self.assertTrue(any(e["type"] == EdgeType.ADVANCES_THREAD.value for e in edges_to_t1))

    def test_foreshadowing_creates_plant_and_payoff_events(self):
        dump = self.kg.to_dict()
        event_ids = {n for n in dump["nodes"] if n.startswith("event:")}
        self.assertIn("event:plant_fs0", event_ids)
        self.assertIn("event:payoff_fs0", event_ids)

    def test_foreshadowing_has_pays_off_edge(self):
        dump = self.kg.to_dict()
        pays_off = [e for e in dump["edges"]
                    if e["source"] == "event:plant_fs0"
                    and e["target"] == "event:payoff_fs0"
                    and e["type"] == EdgeType.PAYS_OFF.value]
        self.assertEqual(len(pays_off), 1)

    def test_plants_edge_from_character(self):
        dump = self.kg.to_dict()
        plants = [e for e in dump["edges"]
                  if e["source"] == "char:Linh"
                  and e["target"] == "event:plant_fs0"
                  and e["type"] == EdgeType.PLANTS.value]
        self.assertEqual(len(plants), 1)

    def test_macro_arc_adds_part_of_arc_edge(self):
        dump = self.kg.to_dict()
        arc_edges = [e for e in dump["edges"]
                     if e["source"] == "char:Linh"
                     and e["target"] == "event:arc_1"
                     and e["type"] == EdgeType.PART_OF_ARC.value]
        self.assertEqual(len(arc_edges), 1)

    def test_part_of_conflict_edge_from_character(self):
        dump = self.kg.to_dict()
        conflict_edges = [e for e in dump["edges"]
                          if e["target"] == "conflict:c1"
                          and e["type"] == EdgeType.PART_OF_CONFLICT.value]
        self.assertEqual(len(conflict_edges), 2)  # Linh + An


class TestSerializationRoundTrip(unittest.TestCase):
    def test_round_trip_preserves_all_node_types(self):
        draft = _make_unified_draft()
        kg1 = StoryKnowledgeGraph().build_unified(draft)
        kg1.add_item("heirloom", {"chapter_introduced": 1})
        kg1.add_location("Hanoi")

        dump = kg1.to_dict()
        kg2 = StoryKnowledgeGraph.from_dict(dump)

        # Same node count and same edge count
        self.assertEqual(kg2.node_count(), kg1.node_count())
        self.assertEqual(kg2.edge_count(), kg1.edge_count())

        # Spot-check a typed edge survives round-trip
        dump2 = kg2.to_dict()
        self.assertTrue(
            any(e["type"] == EdgeType.PAYS_OFF.value for e in dump2["edges"]),
            "PAYS_OFF edge lost on round-trip",
        )

    def test_from_dict_empty(self):
        kg = StoryKnowledgeGraph.from_dict({})
        self.assertEqual(kg.node_count(), 0)
        self.assertEqual(kg.edge_count(), 0)

    def test_from_dict_none(self):
        kg = StoryKnowledgeGraph.from_dict(None)
        self.assertEqual(kg.node_count(), 0)


class TestIdempotentBuild(unittest.TestCase):
    def test_build_unified_twice_does_not_duplicate_nodes(self):
        draft = _make_unified_draft()
        kg = StoryKnowledgeGraph()
        kg.build_unified(draft)
        n_after_first = kg.node_count()
        kg.build_unified(draft)
        self.assertEqual(kg.node_count(), n_after_first)


class TestSchemaFields(unittest.TestCase):
    def test_story_draft_has_knowledge_graph_field(self):
        from models.schemas import StoryDraft
        d = StoryDraft(title="t", genre="g")
        self.assertTrue(hasattr(d, "knowledge_graph"))
        self.assertEqual(d.knowledge_graph, {})
        d.knowledge_graph = {"nodes": {}, "edges": []}
        self.assertEqual(d.knowledge_graph["edges"], [])

    def test_pipeline_output_has_knowledge_graph_field(self):
        from models.schemas import PipelineOutput
        o = PipelineOutput()
        self.assertTrue(hasattr(o, "knowledge_graph"))
        self.assertEqual(o.knowledge_graph, {})
        # Legacy field still present
        self.assertTrue(hasattr(o, "knowledge_graph_summary"))


class TestConfigFlag(unittest.TestCase):
    def test_enable_unified_kg_default_false(self):
        from config.defaults import PipelineConfig
        cfg = PipelineConfig()
        self.assertFalse(cfg.enable_unified_kg)


class TestThreadSafety(unittest.TestCase):
    """Concurrent mutation must not raise. Edge_count semantics vary by backend
    (NetworkX DiGraph collapses same-pair edges; pure-python accumulates), so we
    assert only on no-crash and post-condition stability."""

    def test_concurrent_mutation_no_crash(self):
        import threading as _t
        kg = StoryKnowledgeGraph()
        kg.add_character("A")
        kg.add_character("B")
        errors: list[BaseException] = []

        def _worker(i: int) -> None:
            try:
                for j in range(50):
                    kg.add_relationship("char:A", "char:B",
                                        EdgeType.ALLY.value, chapter=i * 100 + j)
                    # Concurrent readers exercise lock on read side too
                    kg.get_character_relationships("A")
            except BaseException as e:  # pragma: no cover — only fires if lock broken
                errors.append(e)

        threads = [_t.Thread(target=_worker, args=(i,)) for i in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        self.assertFalse(errors, f"Workers crashed: {errors}")
        # At least one edge landed, regardless of backend semantics
        self.assertGreaterEqual(kg.edge_count(), 1)
        # Node count stable at 2 chars (no accidental duplication)
        self.assertEqual(kg.node_count(), 2)


class TestBackwardCompatLegacyBuild(unittest.TestCase):
    """build_from_story_draft must still work unchanged (no draft-level conflicts/threads required)."""

    def test_legacy_build_still_works(self):
        char = types.SimpleNamespace(
            name="Alice", role="main", personality="brave",
            background="", relationships=["Bob: ally"],
        )
        draft = types.SimpleNamespace(
            characters=[char], plot_events=[], story_context=None,
        )
        kg = StoryKnowledgeGraph().build_from_story_draft(draft)
        names = {c["name"] for c in kg.get_all_characters()}
        self.assertIn("Alice", names)


if __name__ == "__main__":
    unittest.main()
