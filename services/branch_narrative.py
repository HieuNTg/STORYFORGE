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

    def _make_node(self, node_id: str, text: str, choices: list[str], parent: Optional[str]) -> dict:
        return {
            "id": node_id,
            "text": text,
            "choices": choices,
            "children": {},   # choice_index (str) -> node_id
            "parent": parent,
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

    def start_session(self, story_text: str, choices: Optional[list[str]] = None) -> dict:
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
        self, session_id: str, choice_index: int, text: str, choices: list[str]
    ) -> dict:
        """Add LLM-generated continuation as child node; move current pointer."""
        with self._lock:
            tree = self._get_session(session_id)
            node = self._walk_to_current(tree)
            new_id = str(uuid.uuid4())
            new_node = self._make_node(new_id, text, choices, node["id"])
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

    def get_tree(self, session_id: str) -> dict:
        """Return full tree structure for visualization."""
        with self._lock:
            tree = self._get_session(session_id)
            nodes_snapshot = {k: _public_node(v) for k, v in tree["nodes"].items()}
            return {
                "session_id": session_id,
                "root": tree["root"],
                "current": tree["current"],
                "nodes": nodes_snapshot,
            }


def _public_node(node: dict) -> dict:
    """Strip internal children map; expose child_ids list for UI."""
    return {
        "id": node["id"],
        "text": node["text"],
        "choices": node["choices"],
        "parent": node["parent"],
        "child_ids": list(node["children"].values()),
        "depth": _depth(node),
    }


def _depth(node: dict) -> int:
    """Approximate depth via parent chain length (not stored; caller handles)."""
    # depth is not tracked explicitly; expose parent presence for UI
    return 0 if node["parent"] is None else 1


# Module-level singleton
manager = BranchManager()
