"""Knowledge graph for story entities — characters, locations, events, relationships.

Lightweight graph using NetworkX (optional) with pure Python fallback.
Tracks entity relationships across chapters for agent review and consistency checking.

Sprint 3 Task 1 — Unified KG: adds typed EdgeType enum, thread/item/conflict
node types, build_unified(draft), to_dict/from_dict, and RLock-guarded mutators
so L2 can augment the graph concurrently during per-scene enhancement.
"""

import json
import logging
import os
import threading
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)

# Try NetworkX, fallback to pure Python
try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    logger.info("NetworkX not installed — using pure Python graph fallback")


class EdgeType(str, Enum):
    """Typed edge relationships for the unified knowledge graph.

    Strict-enum; unknown edge types fall back to RELATED_TO and emit a debug log.
    """

    # Character ↔ character
    ALLY = "ally"
    RIVAL = "rival"
    LOVER = "lover"
    MENTOR = "mentor"
    ENEMY = "enemy"
    FAMILY = "family"
    BETRAYER = "betrayer"
    RELATED_TO = "related_to"

    # Character ↔ event / location / item
    INVOLVED_IN = "involved_in"
    LOCATED_AT = "located_at"
    OWNS_ITEM = "owns_item"

    # Character ↔ thread / conflict
    ADVANCES_THREAD = "advances_thread"
    RESOLVES_THREAD = "resolves_thread"
    PART_OF_CONFLICT = "part_of_conflict"
    PART_OF_ARC = "part_of_arc"

    # Foreshadowing
    PLANTS = "plants"
    PAYS_OFF = "pays_off"

    # Generic
    BLOCKS = "blocks"


_EDGE_TYPE_VALUES = {e.value for e in EdgeType}


def _normalize_edge_type(rel_type: str) -> str:
    """Return a canonical edge-type string. Unknown values fall back to RELATED_TO."""
    if rel_type in _EDGE_TYPE_VALUES:
        return rel_type
    logger.debug("Unknown edge type %r — falling back to RELATED_TO", rel_type)
    return EdgeType.RELATED_TO.value


class StoryKnowledgeGraph:
    """Track story entities and relationships across chapters.

    Nodes: characters, locations, events, items, threads, conflicts
    Edges: typed relationships with chapter, strength, description.

    All mutator methods are guarded by an RLock so L2 can augment the graph
    from parallel scene-enhancement workers without racing.
    """

    def __init__(self):
        self._lock = threading.RLock()
        if HAS_NETWORKX:
            self._graph = nx.DiGraph()
        else:
            # Pure Python fallback: adjacency dict
            self._nodes = {}  # {node_id: {type, name, attributes}}
            self._edges = defaultdict(list)  # {(src, dst): [{type, chapter, strength, ...}]}

    def add_character(self, name: str, attributes: dict = None):
        """Add or update a character node."""
        node_id = f"char:{name}"
        attrs = {"type": "character", "name": name, **(attributes or {})}
        with self._lock:
            if HAS_NETWORKX:
                self._graph.add_node(node_id, **attrs)
            else:
                self._nodes[node_id] = attrs

    def add_location(self, name: str, attributes: dict = None):
        """Add or update a location node."""
        node_id = f"loc:{name}"
        attrs = {"type": "location", "name": name, **(attributes or {})}
        with self._lock:
            if HAS_NETWORKX:
                self._graph.add_node(node_id, **attrs)
            else:
                self._nodes[node_id] = attrs

    def add_event(self, event_id: str, description: str, chapter: int, characters: list = None):
        """Add a plot event node linked to involved characters."""
        node_id = f"event:{event_id}"
        attrs = {"type": "event", "description": description, "chapter": chapter}
        with self._lock:
            if HAS_NETWORKX:
                self._graph.add_node(node_id, **attrs)
            else:
                self._nodes[node_id] = attrs

            # Link characters to event
            for char_name in (characters or []):
                self.add_relationship(f"char:{char_name}", node_id,
                                      EdgeType.INVOLVED_IN.value, chapter)

    def add_thread(self, thread_id: str, attributes: dict = None):
        """Add or update a narrative-thread node (open plot thread)."""
        node_id = f"thread:{thread_id}"
        attrs = {"type": "thread", "name": thread_id, **(attributes or {})}
        with self._lock:
            if HAS_NETWORKX:
                self._graph.add_node(node_id, **attrs)
            else:
                self._nodes[node_id] = attrs

    def add_item(self, item_id: str, attributes: dict = None):
        """Add or update an item node (artifacts, MacGuffins, symbolic objects)."""
        node_id = f"item:{item_id}"
        attrs = {"type": "item", "name": item_id, **(attributes or {})}
        with self._lock:
            if HAS_NETWORKX:
                self._graph.add_node(node_id, **attrs)
            else:
                self._nodes[node_id] = attrs

    def add_conflict(self, conflict_id: str, attributes: dict = None):
        """Add or update a conflict node (from conflict_web)."""
        node_id = f"conflict:{conflict_id}"
        attrs = {"type": "conflict", "name": conflict_id, **(attributes or {})}
        with self._lock:
            if HAS_NETWORKX:
                self._graph.add_node(node_id, **attrs)
            else:
                self._nodes[node_id] = attrs

    def add_relationship(self, source_id: str, target_id: str, rel_type: str,
                         chapter: int = 0, strength: float = 1.0, description: str = ""):
        """Add a directed relationship edge between two nodes.

        rel_type is normalized through EdgeType — unknown values fall back to
        RELATED_TO (logged at debug). Accepts free-form legacy strings so
        build_from_story_draft / load remain backward-compatible.
        """
        canonical = _normalize_edge_type(rel_type)
        edge_data = {
            "type": canonical,
            "chapter": chapter,
            "strength": strength,
            "description": description,
        }
        with self._lock:
            if HAS_NETWORKX:
                # Use multigraph behavior: add as attribute dict
                key = f"{canonical}_ch{chapter}"
                self._graph.add_edge(source_id, target_id, key=key, **edge_data)
            else:
                self._edges[(source_id, target_id)].append(edge_data)

    def get_character_relationships(self, char_name: str) -> list[dict]:
        """Get all relationships for a character."""
        node_id = f"char:{char_name}"
        results = []
        if HAS_NETWORKX:
            for _, target, data in self._graph.out_edges(node_id, data=True):
                results.append({"target": target, **data})
            for source, _, data in self._graph.in_edges(node_id, data=True):
                results.append({"source": source, **data})
        else:
            for (src, dst), edges in self._edges.items():
                if src == node_id or dst == node_id:
                    for e in edges:
                        results.append({"source": src, "target": dst, **e})
        return results

    def get_chapter_events(self, chapter: int) -> list[dict]:
        """Get all events in a specific chapter."""
        events = []
        if HAS_NETWORKX:
            for node_id, data in self._graph.nodes(data=True):
                if data.get("type") == "event" and data.get("chapter") == chapter:
                    events.append({"id": node_id, **data})
        else:
            for node_id, data in self._nodes.items():
                if data.get("type") == "event" and data.get("chapter") == chapter:
                    events.append({"id": node_id, **data})
        return events

    def get_character_timeline(self, char_name: str) -> list[dict]:
        """Get chronological events involving a character."""
        timeline = []
        rels = self.get_character_relationships(char_name)
        for rel in rels:
            target = rel.get("target", rel.get("source", ""))
            if target.startswith("event:"):
                # Get event details
                if HAS_NETWORKX:
                    event_data = self._graph.nodes.get(target, {})
                else:
                    event_data = self._nodes.get(target, {})
                timeline.append({
                    "event_id": target,
                    "chapter": event_data.get("chapter", 0),
                    "description": event_data.get("description", ""),
                })
        return sorted(timeline, key=lambda x: x["chapter"])

    def get_all_characters(self) -> list[dict]:
        """Get all character nodes."""
        chars = []
        if HAS_NETWORKX:
            for node_id, data in self._graph.nodes(data=True):
                if data.get("type") == "character":
                    chars.append({"id": node_id, **data})
        else:
            for node_id, data in self._nodes.items():
                if data.get("type") == "character":
                    chars.append({"id": node_id, **data})
        return chars

    def node_count(self) -> int:
        if HAS_NETWORKX:
            return self._graph.number_of_nodes()
        return len(self._nodes)

    def edge_count(self) -> int:
        if HAS_NETWORKX:
            return self._graph.number_of_edges()
        return sum(len(v) for v in self._edges.values())

    def build_from_story_draft(self, story_draft) -> "StoryKnowledgeGraph":
        """Populate graph from a StoryDraft object.

        Extracts characters, plot_events, and character_states from the draft.
        """
        # Add characters
        for char in getattr(story_draft, "characters", []):
            self.add_character(char.name, {
                "role": getattr(char, "role", ""),
                "personality": getattr(char, "personality", ""),
                "background": getattr(char, "background", ""),
            })
            # Character relationships from schema
            for rel in getattr(char, "relationships", []):
                if isinstance(rel, str) and ":" in rel:
                    parts = rel.split(":", 1)
                    if len(parts) == 2:
                        self.add_relationship(f"char:{char.name}", f"char:{parts[0].strip()}",
                                              "related_to", description=parts[1].strip())

        # Add plot events from story context
        context = getattr(story_draft, "story_context", None)
        if context:
            for i, event in enumerate(getattr(context, "plot_events", [])):
                event_text = getattr(event, "event", str(event))
                chars = getattr(event, "characters_involved", [])
                chapter = getattr(event, "chapter_number", 0)
                self.add_event(f"e{i}", event_text, chapter, chars)

            # Add character states as attributes
            for state in getattr(context, "character_states", []):
                name = getattr(state, "name", "")
                if name:
                    self.add_character(name, {
                        "mood": getattr(state, "mood", ""),
                        "arc_position": getattr(state, "arc_position", ""),
                        "last_action": getattr(state, "last_action", ""),
                    })

        # Also ingest top-level plot_events on StoryDraft itself
        for i, event in enumerate(getattr(story_draft, "plot_events", [])):
            event_text = getattr(event, "event", str(event))
            chars = getattr(event, "characters_involved", [])
            chapter = getattr(event, "chapter_number", 0)
            self.add_event(f"draft_e{i}", event_text, chapter, chars)

        return self

    def build_unified(self, story_draft) -> "StoryKnowledgeGraph":
        """Sprint 3 unified build — merges conflict_web, open_threads, foreshadowing_plan,
        macro_arcs, and character relationships into one graph.

        Idempotent: safe to call multiple times on the same draft; repeated node adds
        overwrite attrs, repeated edges accumulate (mirrors build_from_story_draft).
        """
        # Delegate character + plot-event ingestion to the legacy builder
        self.build_from_story_draft(story_draft)

        # Conflicts — characters → conflict nodes
        for c in getattr(story_draft, "conflict_web", []) or []:
            cid = getattr(c, "conflict_id", None) or getattr(c, "id", None)
            if not cid:
                continue
            self.add_conflict(cid, {
                "conflict_type": getattr(c, "conflict_type", ""),
                "description": getattr(c, "description", ""),
                "arc_range": getattr(c, "arc_range", ""),
                "status": getattr(c, "status", ""),
            })
            for char_name in getattr(c, "characters", []) or []:
                self.add_relationship(f"char:{char_name}", f"conflict:{cid}",
                                      EdgeType.PART_OF_CONFLICT.value)

        # Open threads — characters → thread nodes (advances / resolves)
        for t in getattr(story_draft, "open_threads", []) or []:
            tid = getattr(t, "thread_id", None)
            if not tid:
                continue
            self.add_thread(tid, {
                "description": getattr(t, "description", ""),
                "status": getattr(t, "status", "open"),
                "planted_chapter": getattr(t, "planted_chapter", 0),
                "last_mentioned_chapter": getattr(t, "last_mentioned_chapter", 0),
                "resolution_chapter": getattr(t, "resolution_chapter", 0),
            })
            status = getattr(t, "status", "open")
            edge = (EdgeType.RESOLVES_THREAD.value if status == "resolved"
                    else EdgeType.ADVANCES_THREAD.value)
            for char_name in getattr(t, "involved_characters", []) or []:
                self.add_relationship(f"char:{char_name}", f"thread:{tid}", edge,
                                      chapter=getattr(t, "last_mentioned_chapter", 0))

        # Foreshadowing — plant/payoff edges from involved characters to synthetic event ids
        for i, fs in enumerate(getattr(story_draft, "foreshadowing_plan", []) or []):
            plant_ch = getattr(fs, "plant_chapter", 0)
            payoff_ch = getattr(fs, "payoff_chapter", 0)
            fs_id = f"fs{i}"
            # Use an event-like node (type=event) to stay compatible with chapter-events lookups
            self.add_event(f"plant_{fs_id}",
                           getattr(fs, "hint", ""), plant_ch,
                           getattr(fs, "characters_involved", []) or [])
            if payoff_ch and payoff_ch != plant_ch:
                self.add_event(f"payoff_{fs_id}",
                               getattr(fs, "hint", ""), payoff_ch,
                               getattr(fs, "characters_involved", []) or [])
                # Link plant → payoff
                self.add_relationship(f"event:plant_{fs_id}",
                                      f"event:payoff_{fs_id}",
                                      EdgeType.PAYS_OFF.value, chapter=payoff_ch)
            for char_name in getattr(fs, "characters_involved", []) or []:
                self.add_relationship(f"char:{char_name}", f"event:plant_{fs_id}",
                                      EdgeType.PLANTS.value, chapter=plant_ch)

        # Macro arcs — characters → synthetic arc event nodes
        for arc in getattr(story_draft, "macro_arcs", []) or []:
            arc_num = getattr(arc, "arc_number", None)
            if arc_num is None:
                continue
            arc_eid = f"arc_{arc_num}"
            self.add_event(arc_eid,
                           getattr(arc, "name", "") or f"Arc {arc_num}",
                           getattr(arc, "chapter_start", 0),
                           getattr(arc, "character_focus", []) or [])
            for char_name in getattr(arc, "character_focus", []) or []:
                self.add_relationship(f"char:{char_name}", f"event:{arc_eid}",
                                      EdgeType.PART_OF_ARC.value,
                                      chapter=getattr(arc, "chapter_start", 0))

        return self

    def to_dict(self) -> dict:
        """Serialize the full graph to a JSON-safe dict (for checkpointing / persistence)."""
        data = {"nodes": {}, "edges": []}
        with self._lock:
            if HAS_NETWORKX:
                for node_id, attrs in self._graph.nodes(data=True):
                    data["nodes"][node_id] = dict(attrs)
                for src, dst, attrs in self._graph.edges(data=True):
                    data["edges"].append({"source": src, "target": dst, **dict(attrs)})
            else:
                data["nodes"] = {k: dict(v) for k, v in self._nodes.items()}
                for (src, dst), edge_list in self._edges.items():
                    for e in edge_list:
                        data["edges"].append({"source": src, "target": dst, **dict(e)})
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "StoryKnowledgeGraph":
        """Reconstruct a graph from the dict produced by `to_dict`."""
        kg = cls()
        data = data or {}
        for node_id, attrs in (data.get("nodes") or {}).items():
            node_type = attrs.get("type", "unknown")
            name = attrs.get("name") or node_id.split(":", 1)[-1]
            if node_type == "character":
                kg.add_character(name, attrs)
            elif node_type == "location":
                kg.add_location(name, attrs)
            elif node_type == "event":
                kg.add_event(node_id.replace("event:", ""),
                             attrs.get("description", ""),
                             attrs.get("chapter", 0))
            elif node_type == "thread":
                kg.add_thread(name, attrs)
            elif node_type == "item":
                kg.add_item(name, attrs)
            elif node_type == "conflict":
                kg.add_conflict(name, attrs)
            else:
                # Unknown node type — store raw via character-like node so it's not lost
                logger.debug("Unknown node type %r for %s — storing as-is", node_type, node_id)
                with kg._lock:
                    if HAS_NETWORKX:
                        kg._graph.add_node(node_id, **attrs)
                    else:
                        kg._nodes[node_id] = dict(attrs)
        for edge in (data.get("edges") or []):
            edge = dict(edge)
            src = edge.pop("source", "")
            dst = edge.pop("target", "")
            rel_type = edge.pop("type", EdgeType.RELATED_TO.value)
            kg.add_relationship(src, dst, rel_type,
                                chapter=edge.get("chapter", 0),
                                strength=edge.get("strength", 1.0),
                                description=edge.get("description", ""))
        return kg

    def get_entity_context(self, char_names: list[str], max_chars: int = 1000) -> str:
        """Return relationship summary text for given character names (for prompt injection)."""
        lines = []
        for name in char_names:
            rels = self.get_character_relationships(name)
            if rels:
                rel_strs = []
                for r in rels[:5]:
                    target = r.get("target", r.get("source", "")).replace("char:", "").replace("event:", "")
                    rel_strs.append(f"{r.get('type', '?')}→{target}")
                lines.append(f"- {name}: {', '.join(rel_strs)}")
        summary = "\n".join(lines)
        return summary[:max_chars]

    def to_summary(self, max_chars: int = 2000) -> str:
        """Export graph as compact text summary for LLM context injection."""
        lines = []
        chars = self.get_all_characters()
        lines.append(f"KNOWLEDGE GRAPH: {len(chars)} nhân vật, {self.node_count()} nodes, {self.edge_count()} edges")

        for c in chars[:10]:  # Cap at 10 characters
            name = c.get("name", "?")
            rels = self.get_character_relationships(name)
            rel_strs = []
            for r in rels[:5]:  # Cap at 5 relationships per char
                target = r.get("target", r.get("source", "")).replace("char:", "").replace("event:", "")
                rel_strs.append(f"{r.get('type', '?')}→{target}")
            line = f"- {name}: {', '.join(rel_strs)}" if rel_strs else f"- {name}"
            lines.append(line)

        summary = "\n".join(lines)
        return summary[:max_chars]

    def save(self, filepath: str):
        """Save graph to JSON file."""
        data = self.to_dict()
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, filepath: str) -> "StoryKnowledgeGraph":
        """Load graph from JSON file — populates self in-place for legacy API compat."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        other = self.from_dict(data)
        # Copy state from `other` into self so callers that do `kg.load(path)` keep their reference
        with self._lock:
            if HAS_NETWORKX:
                self._graph = other._graph
            else:
                self._nodes = other._nodes
                self._edges = other._edges
        return self
