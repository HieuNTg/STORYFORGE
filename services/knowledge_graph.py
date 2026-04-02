"""Knowledge graph for story entities — characters, locations, events, relationships.

Lightweight graph using NetworkX (optional) with pure Python fallback.
Tracks entity relationships across chapters for agent review and consistency checking.
"""

import json
import logging
import os
from collections import defaultdict

logger = logging.getLogger(__name__)

# Try NetworkX, fallback to pure Python
try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    logger.info("NetworkX not installed — using pure Python graph fallback")


class StoryKnowledgeGraph:
    """Track story entities and relationships across chapters.

    Nodes: characters, locations, events, items
    Edges: relationships with type, chapter_introduced, strength
    """

    def __init__(self):
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
        if HAS_NETWORKX:
            self._graph.add_node(node_id, **attrs)
        else:
            self._nodes[node_id] = attrs

    def add_location(self, name: str, attributes: dict = None):
        """Add or update a location node."""
        node_id = f"loc:{name}"
        attrs = {"type": "location", "name": name, **(attributes or {})}
        if HAS_NETWORKX:
            self._graph.add_node(node_id, **attrs)
        else:
            self._nodes[node_id] = attrs

    def add_event(self, event_id: str, description: str, chapter: int, characters: list = None):
        """Add a plot event node linked to involved characters."""
        node_id = f"event:{event_id}"
        attrs = {"type": "event", "description": description, "chapter": chapter}
        if HAS_NETWORKX:
            self._graph.add_node(node_id, **attrs)
        else:
            self._nodes[node_id] = attrs

        # Link characters to event
        for char_name in (characters or []):
            self.add_relationship(f"char:{char_name}", node_id, "involved_in", chapter)

    def add_relationship(self, source_id: str, target_id: str, rel_type: str,
                         chapter: int = 0, strength: float = 1.0, description: str = ""):
        """Add a directed relationship edge between two nodes."""
        edge_data = {
            "type": rel_type,
            "chapter": chapter,
            "strength": strength,
            "description": description,
        }
        if HAS_NETWORKX:
            # Use multigraph behavior: add as attribute dict
            key = f"{rel_type}_ch{chapter}"
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
        data = {"nodes": {}, "edges": []}
        if HAS_NETWORKX:
            for node_id, attrs in self._graph.nodes(data=True):
                data["nodes"][node_id] = attrs
            for src, dst, attrs in self._graph.edges(data=True):
                data["edges"].append({"source": src, "target": dst, **attrs})
        else:
            data["nodes"] = self._nodes
            for (src, dst), edge_list in self._edges.items():
                for e in edge_list:
                    data["edges"].append({"source": src, "target": dst, **e})

        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, filepath: str) -> "StoryKnowledgeGraph":
        """Load graph from JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        for node_id, attrs in data.get("nodes", {}).items():
            node_type = attrs.get("type", "unknown")
            if node_type == "character":
                self.add_character(attrs.get("name", node_id), attrs)
            elif node_type == "location":
                self.add_location(attrs.get("name", node_id), attrs)
            elif node_type == "event":
                self.add_event(node_id.replace("event:", ""),
                               attrs.get("description", ""),
                               attrs.get("chapter", 0))

        for edge in data.get("edges", []):
            edge = dict(edge)  # copy to avoid mutating original
            src = edge.pop("source", "")
            dst = edge.pop("target", "")
            rel_type = edge.pop("type", "related_to")
            self.add_relationship(src, dst, rel_type,
                                  chapter=edge.get("chapter", 0),
                                  strength=edge.get("strength", 1.0),
                                  description=edge.get("description", ""))
        return self
