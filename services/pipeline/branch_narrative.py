"""Branch narrative — thread-safe in-memory choose-your-own-adventure tree manager."""

import uuid
import time
from collections import deque
from threading import Lock
from typing import Optional

MAX_SESSIONS = 50


class BranchManager:
    """In-memory branch tree manager for interactive storytelling."""

    def __init__(self) -> None:
        self._trees: dict[str, dict] = {}  # session_id -> tree
        self._order: deque[str] = deque()  # FIFO eviction order
        self._lock = Lock()

    # ── helpers ────────────────────────────────────────────────────────────

    def _make_node(
        self, node_id: str, text: str, choices: list[str],
        parent: Optional[str], character_states: Optional[dict] = None,
    ) -> dict:
        return {
            "id": node_id,
            "text": text,
            "choices": choices,
            "children": {},   # choice_index (str) -> node_id
            "parent": parent,
            "character_states": character_states or {},
        }

    def _evict_if_needed(self) -> None:
        """FIFO eviction when MAX_SESSIONS reached. Must be called under lock."""
        while len(self._trees) >= MAX_SESSIONS and self._order:
            oldest = self._order.popleft()
            self._trees.pop(oldest, None)

    def _get_session(self, session_id: str) -> dict:
        """Return session dict or raise KeyError."""
        tree = self._trees.get(session_id)
        if tree is None:
            raise KeyError(f"Session {session_id!r} not found")
        return tree

    def _walk_to_current(self, tree: dict) -> dict:
        """Return the node at tree['current']."""
        return tree["nodes"][tree["current"]]

    # ── public API ─────────────────────────────────────────────────────────

    def start_session(
        self, story_text: str, choices: Optional[list[str]] = None,
        context: Optional[dict] = None,
    ) -> dict:
        """Parse story text, create root node, return session data."""
        session_id = str(uuid.uuid4())
        root_id = str(uuid.uuid4())
        root_choices = choices or [
            "Continue the adventure",
            "Take a different path",
            "Make a bold decision",
        ]
        root_node = self._make_node(root_id, story_text, root_choices, None)
        tree = {
            "session_id": session_id,
            "root": root_id,
            "current": root_id,
            "nodes": {root_id: root_node},
            "created_at": time.time(),
            "context": context or {},
        }
        with self._lock:
            self._evict_if_needed()
            self._trees[session_id] = tree
            self._order.append(session_id)
        return {"session_id": session_id, "node": _public_node(root_node)}

    def get_current_node(self, session_id: str) -> dict:
        """Return current node with text and available choices."""
        with self._lock:
            tree = self._get_session(session_id)
            node = self._walk_to_current(tree)
        return _public_node(node)

    def choose_branch(self, session_id: str, choice_index: int) -> Optional[dict]:
        """Select a choice; return child node if already generated, else None."""
        with self._lock:
            tree = self._get_session(session_id)
            node = self._walk_to_current(tree)
            key = str(choice_index)
            child_id = node["children"].get(key)
            if child_id:
                child = tree["nodes"][child_id]
                tree["current"] = child_id
                return _public_node(child)
        return None  # needs LLM generation

    def add_generated_node(
        self, session_id: str, choice_index: int, text: str, choices: list[str],
        character_states: Optional[dict] = None,
    ) -> dict:
        """Add LLM-generated continuation as child node; move current pointer."""
        with self._lock:
            tree = self._get_session(session_id)
            node = self._walk_to_current(tree)
            new_id = str(uuid.uuid4())
            new_node = self._make_node(new_id, text, choices, node["id"], character_states)
            tree["nodes"][new_id] = new_node
            node["children"][str(choice_index)] = new_id
            tree["current"] = new_id
        return _public_node(new_node)

    def go_back(self, session_id: str) -> dict:
        """Navigate to parent node. Raises ValueError if already at root."""
        with self._lock:
            tree = self._get_session(session_id)
            node = self._walk_to_current(tree)
            if node["parent"] is None:
                raise ValueError("Already at root node")
            tree["current"] = node["parent"]
            parent = tree["nodes"][node["parent"]]
        return _public_node(parent)

    def get_context(self, session_id: str) -> dict:
        """Return session-level story context (genre, characters, world, conflicts)."""
        with self._lock:
            tree = self._get_session(session_id)
            return tree.get("context", {})

    def get_node_states(self, session_id: str) -> dict:
        """Return character_states of current node."""
        with self._lock:
            tree = self._get_session(session_id)
            node = self._walk_to_current(tree)
            return node.get("character_states", {})

    def get_tree(self, session_id: str) -> dict:
        """Return full tree structure for visualization."""
        with self._lock:
            tree = self._get_session(session_id)
            nodes_snapshot = {
                k: _public_node(v, tree["nodes"]) for k, v in tree["nodes"].items()
            }
            return {
                "session_id": session_id,
                "root": tree["root"],
                "current": tree["current"],
                "nodes": nodes_snapshot,
            }

    def goto_node(self, session_id: str, node_id: str) -> dict:
        """Jump to any existing node in the session tree."""
        with self._lock:
            tree = self._get_session(session_id)
            if node_id not in tree["nodes"]:
                raise ValueError(f"Node {node_id!r} not found in session")
            tree["current"] = node_id
            node = tree["nodes"][node_id]
        return _public_node(node, tree["nodes"])

    def merge_branches(
        self,
        session_id: str,
        node_a_id: str,
        node_b_id: str,
        strategy: str = "auto",
        llm=None,
    ) -> dict:
        """Merge two branch paths into a single canonical node.

        Args:
            session_id: Session containing the branches
            node_a_id: First node to merge
            node_b_id: Second node to merge
            strategy: 'auto' (LLM resolves), 'prefer_a', 'prefer_b'
            llm: LLM client for conflict resolution (required if strategy='auto')

        Returns:
            dict with merged_node, conflicts_resolved, conflicts_unresolved
        """
        with self._lock:
            tree = self._get_session(session_id)
            if node_a_id not in tree["nodes"]:
                raise ValueError(f"Node {node_a_id!r} not found")
            if node_b_id not in tree["nodes"]:
                raise ValueError(f"Node {node_b_id!r} not found")

            node_a = tree["nodes"][node_a_id]
            node_b = tree["nodes"][node_b_id]

            # Find common ancestor
            ancestors_a = self._get_ancestors(node_a, tree["nodes"])
            ancestors_b = self._get_ancestors(node_b, tree["nodes"])
            common_ancestor = None
            for anc_id in ancestors_a:
                if anc_id in ancestors_b:
                    common_ancestor = anc_id
                    break

            # Detect conflicts
            conflicts = self._detect_conflicts(node_a, node_b, tree.get("context", {}))

            # Resolve conflicts based on strategy
            resolved = []
            unresolved = []
            merged_text = ""

            if strategy == "prefer_a":
                merged_text = node_a["text"]
                resolved = [{"conflict": c, "resolution": "Used version A"} for c in conflicts]
            elif strategy == "prefer_b":
                merged_text = node_b["text"]
                resolved = [{"conflict": c, "resolution": "Used version B"} for c in conflicts]
            elif strategy == "auto" and llm:
                merge_result = self._llm_merge(node_a, node_b, conflicts, llm)
                merged_text = merge_result["text"]
                resolved = merge_result.get("resolved", [])
                unresolved = merge_result.get("unresolved", [])
            else:
                # Simple concatenation if no LLM
                merged_text = f"{node_a['text']}\n\n---\n\n{node_b['text']}"
                unresolved = conflicts

            # Create merged node
            new_id = str(uuid.uuid4())
            merged_choices = list(set(node_a["choices"] + node_b["choices"]))[:3]
            merged_states = {**node_a.get("character_states", {}), **node_b.get("character_states", {})}
            merged_node = self._make_node(
                new_id, merged_text, merged_choices, common_ancestor, merged_states
            )
            tree["nodes"][new_id] = merged_node
            tree["current"] = new_id

            # Link from common ancestor if exists
            if common_ancestor:
                tree["nodes"][common_ancestor]["children"]["merged"] = new_id

        return {
            "merged_node": _public_node(merged_node, tree["nodes"]),
            "conflicts_resolved": resolved,
            "conflicts_unresolved": unresolved,
            "common_ancestor": common_ancestor,
        }

    def _get_ancestors(self, node: dict, all_nodes: dict) -> list[str]:
        """Return list of ancestor node IDs from node to root."""
        ancestors = []
        current = node
        while current["parent"] is not None:
            ancestors.append(current["parent"])
            current = all_nodes.get(current["parent"], {"parent": None})
        return ancestors

    def _detect_conflicts(self, node_a: dict, node_b: dict, context: dict) -> list[dict]:
        """Detect narrative conflicts between two nodes."""
        conflicts = []
        states_a = node_a.get("character_states", {})
        states_b = node_b.get("character_states", {})

        # Check character state contradictions
        for char in set(states_a.keys()) | set(states_b.keys()):
            if char in states_a and char in states_b:
                if states_a[char] != states_b[char]:
                    conflicts.append({
                        "conflict_type": "character_state",
                        "description": f"{char} has different states",
                        "source_a": str(states_a[char]),
                        "source_b": str(states_b[char]),
                    })

        return conflicts

    def _llm_merge(self, node_a: dict, node_b: dict, conflicts: list, llm) -> dict:
        """Use LLM to merge conflicting narratives."""
        prompt = f"""Merge these two story branches into a coherent narrative.

BRANCH A:
{node_a['text']}

BRANCH B:
{node_b['text']}

DETECTED CONFLICTS:
{conflicts}

Create a merged narrative that:
1. Combines the best elements of both branches
2. Resolves contradictions in a narratively satisfying way
3. Maintains story continuity

Return JSON:
{{"text": "merged narrative", "resolutions": ["how each conflict was resolved"]}}"""

        try:
            result = llm.generate_json(
                system_prompt="You merge story branches. Return JSON.",
                user_prompt=prompt,
                temperature=0.7,
            )
            return {
                "text": result.get("text", f"{node_a['text']}\n\n{node_b['text']}"),
                "resolved": [
                    {"conflict": c, "resolution": r}
                    for c, r in zip(conflicts, result.get("resolutions", []))
                ],
                "unresolved": [],
            }
        except Exception:
            return {
                "text": f"{node_a['text']}\n\n{node_b['text']}",
                "resolved": [],
                "unresolved": conflicts,
            }


def _public_node(node: dict, all_nodes: dict | None = None) -> dict:
    """Strip internal children map; expose child_ids list for UI."""
    return {
        "id": node["id"],
        "text": node["text"],
        "choices": node["choices"],
        "parent": node["parent"],
        "child_ids": list(node["children"].values()),
        "depth": _depth(node, all_nodes),
    }


def _depth(node: dict, all_nodes: dict | None = None) -> int:
    """Compute depth by walking parent chain."""
    if all_nodes is None:
        return 0 if node["parent"] is None else 1
    depth = 0
    current = node
    while current["parent"] is not None:
        depth += 1
        current = all_nodes.get(current["parent"], {"parent": None})
    return depth


# Module-level singleton
manager = BranchManager()
