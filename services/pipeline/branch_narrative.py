"""Branch narrative — thread-safe choose-your-own-adventure tree manager.

Supports dual-backend persistence: Redis (production) or in-memory (local).
"""

import uuid
import time
from threading import Lock
from typing import Optional

from services.pipeline.branch_persistence import get_branch_store

MAX_SESSIONS = 50


class BranchManager:
    """Branch tree manager with optional Redis persistence."""

    def __init__(self) -> None:
        self._store = get_branch_store()
        self._lock = Lock()
        # In-memory caches for undo/redo (not persisted to Redis)
        self._undo_stacks: dict[str, list[str]] = {}
        self._redo_stacks: dict[str, list[str]] = {}

    # ── helpers ────────────────────────────────────────────────────────────

    def _make_node(
        self, node_id: str, text: str, choices: list[str],
        parent: Optional[str], character_states: Optional[dict] = None,
        state_changes: Optional[dict] = None,
        choice_conditions: Optional[list[dict]] = None,
    ) -> dict:
        return {
            "id": node_id,
            "text": text,
            "choices": choices,
            "children": {},   # choice_index (str) -> node_id
            "parent": parent,
            "character_states": character_states or {},
            "state_changes": state_changes or {},  # {"gold": 10, "reputation": -5}
            "choice_conditions": choice_conditions or [],  # [{"index": 0, "requires": {"gold": 50}}]
        }

    def _get_session(self, session_id: str) -> dict:
        """Return session dict or raise KeyError."""
        tree = self._store.get(session_id)
        if tree is None:
            raise KeyError(f"Session {session_id!r} not found")
        return tree

    def _save_session(self, session_id: str, tree: dict) -> None:
        """Persist session to store."""
        self._store.put(session_id, tree)

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
            self._save_session(session_id, tree)
        return {"session_id": session_id, "node": _public_node(root_node)}

    def get_current_node(self, session_id: str) -> dict:
        """Return current node with text and available choices."""
        with self._lock:
            tree = self._get_session(session_id)
            node = self._walk_to_current(tree)
        return _public_node(node)

    def choose_branch(self, session_id: str, choice_index: int) -> Optional[dict]:
        """Select a choice; return child node if already generated, else None."""
        node_id = None
        with self._lock:
            tree = self._get_session(session_id)
            node = self._walk_to_current(tree)
            node_id = node["id"]
            key = str(choice_index)
            child_id = node["children"].get(key)
            if child_id:
                # Push current to undo stack before moving
                self._push_undo(session_id, node["id"])
                child = tree["nodes"][child_id]
                tree["current"] = child_id
                self._save_session(session_id, tree)
                # Track analytics outside lock
                self._track_choice(session_id, node_id, choice_index)
                return _public_node(child)
        return None  # needs LLM generation

    def add_generated_node(
        self, session_id: str, choice_index: int, text: str, choices: list[str],
        character_states: Optional[dict] = None,
    ) -> dict:
        """Add LLM-generated continuation as child node; move current pointer."""
        node_id = None
        with self._lock:
            tree = self._get_session(session_id)
            node = self._walk_to_current(tree)
            node_id = node["id"]
            # Push current to undo stack before moving
            self._push_undo(session_id, node["id"])
            new_id = str(uuid.uuid4())
            new_node = self._make_node(new_id, text, choices, node["id"], character_states)
            tree["nodes"][new_id] = new_node
            node["children"][str(choice_index)] = new_id
            tree["current"] = new_id
            self._save_session(session_id, tree)
        # Track analytics outside lock
        self._track_choice(session_id, node_id, choice_index)
        return _public_node(new_node)

    def go_back(self, session_id: str) -> dict:
        """Navigate to parent node. Raises ValueError if already at root."""
        with self._lock:
            tree = self._get_session(session_id)
            node = self._walk_to_current(tree)
            if node["parent"] is None:
                raise ValueError("Already at root node")
            tree["current"] = node["parent"]
            self._save_session(session_id, tree)
            parent = tree["nodes"][node["parent"]]
        return _public_node(parent)

    def undo(self, session_id: str) -> dict:
        """Undo navigation — return to previous node, preserve redo stack."""
        with self._lock:
            tree = self._get_session(session_id)
            undo_stack = self._undo_stacks.get(session_id, [])
            if not undo_stack:
                raise ValueError("Nothing to undo")

            current_id = tree["current"]
            prev_id = undo_stack.pop()

            # Push current to redo stack
            if session_id not in self._redo_stacks:
                self._redo_stacks[session_id] = []
            self._redo_stacks[session_id].append(current_id)

            tree["current"] = prev_id
            self._save_session(session_id, tree)
            node = tree["nodes"][prev_id]
        return _public_node(node, tree["nodes"])

    def redo(self, session_id: str) -> dict:
        """Redo navigation — go forward to previously undone node."""
        with self._lock:
            tree = self._get_session(session_id)
            redo_stack = self._redo_stacks.get(session_id, [])
            if not redo_stack:
                raise ValueError("Nothing to redo")

            current_id = tree["current"]
            next_id = redo_stack.pop()

            # Push current to undo stack
            if session_id not in self._undo_stacks:
                self._undo_stacks[session_id] = []
            self._undo_stacks[session_id].append(current_id)

            tree["current"] = next_id
            self._save_session(session_id, tree)
            node = tree["nodes"][next_id]
        return _public_node(node, tree["nodes"])

    def can_undo(self, session_id: str) -> bool:
        """Check if undo is available."""
        with self._lock:
            return bool(self._undo_stacks.get(session_id))

    def can_redo(self, session_id: str) -> bool:
        """Check if redo is available."""
        with self._lock:
            return bool(self._redo_stacks.get(session_id))

    def _push_undo(self, session_id: str, node_id: str) -> None:
        """Push node to undo stack and clear redo stack (internal use)."""
        if session_id not in self._undo_stacks:
            self._undo_stacks[session_id] = []
        self._undo_stacks[session_id].append(node_id)
        # Clear redo stack when new navigation happens
        self._redo_stacks[session_id] = []

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

    def get_path_to_current(self, session_id: str) -> list[dict]:
        """Return list of nodes from root to current (inclusive)."""
        with self._lock:
            tree = self._get_session(session_id)
            node = self._walk_to_current(tree)
            path = []
            current = node
            while current is not None:
                path.append({
                    "id": current["id"],
                    "text": current["text"],
                    "depth": _depth(current, tree["nodes"]),
                })
                if current["parent"] is None:
                    break
                current = tree["nodes"].get(current["parent"])
            return list(reversed(path))  # root first

    def get_path_summary(self, session_id: str, max_tokens: int = 500) -> str:
        """Generate condensed summary of path from root to current.

        Uses progressive summarization:
        - Recent nodes (last 2): full text
        - Middle nodes: first 200 chars
        - Early nodes: just "Chapter N: [title extracted]"
        """
        path = self.get_path_to_current(session_id)
        if len(path) <= 2:
            return ""  # No summary needed for shallow paths

        parts = []
        total_len = 0
        target_chars = max_tokens * 4  # ~4 chars per token estimate

        for i, node in enumerate(path[:-1]):  # Exclude current node
            depth = node["depth"]
            text = node["text"]

            if i >= len(path) - 3:
                # Recent nodes: include more text
                excerpt = text[:800] + "..." if len(text) > 800 else text
            elif i >= len(path) - 5:
                # Middle nodes: brief excerpt
                excerpt = text[:300] + "..." if len(text) > 300 else text
            else:
                # Early nodes: minimal summary
                first_line = text.split('\n')[0][:100]
                excerpt = f"[Earlier: {first_line}...]"

            part = f"[Depth {depth}] {excerpt}"
            if total_len + len(part) > target_chars:
                parts.append("[...earlier content truncated...]")
                break
            parts.append(part)
            total_len += len(part)

        return "\n\n".join(parts)

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

    def get_tree_layout(self, session_id: str) -> dict:
        """Return tree with computed layout positions for visualization.

        Uses a simple tree layout algorithm:
        - X position based on sibling order
        - Y position based on depth
        """
        with self._lock:
            tree = self._get_session(session_id)
            root_id = tree["root"]
            nodes = tree["nodes"]

            # Compute layout
            layout = {}
            self._compute_layout(root_id, nodes, layout, x=0, y=0, x_offset=[0])

            # Compute bounds for minimap
            if layout:
                min_x = min(pos["x"] for pos in layout.values())
                max_x = max(pos["x"] for pos in layout.values())
                max_y = max(pos["y"] for pos in layout.values())
            else:
                min_x, max_x, max_y = 0, 0, 0

            return {
                "session_id": session_id,
                "root": root_id,
                "current": tree["current"],
                "layout": layout,
                "bounds": {
                    "min_x": min_x,
                    "max_x": max_x,
                    "max_y": max_y,
                    "width": max_x - min_x + 1,
                    "height": max_y + 1,
                },
                "stats": {
                    "total_nodes": len(nodes),
                    "max_depth": max_y,
                    "leaf_count": sum(1 for n in nodes.values() if not n.get("children")),
                },
            }

    def _compute_layout(
        self, node_id: str, nodes: dict, layout: dict,
        x: int, y: int, x_offset: list
    ) -> int:
        """Recursively compute node positions. Returns width of subtree."""
        node = nodes.get(node_id)
        if not node:
            return 0

        children = node.get("children", {})
        if not children:
            # Leaf node
            layout[node_id] = {"x": x_offset[0], "y": y}
            x_offset[0] += 1
            return 1

        # Layout children first
        start_x = x_offset[0]
        child_ids = list(children.values())
        for child_id in child_ids:
            self._compute_layout(child_id, nodes, layout, x_offset[0], y + 1, x_offset)

        # Center parent above children
        if child_ids:
            child_xs = [layout[cid]["x"] for cid in child_ids if cid in layout]
            if child_xs:
                parent_x = (min(child_xs) + max(child_xs)) / 2
            else:
                parent_x = start_x
        else:
            parent_x = start_x

        layout[node_id] = {"x": parent_x, "y": y}
        return x_offset[0] - start_x

    def get_minimap_data(self, session_id: str) -> dict:
        """Get simplified tree data for minimap rendering."""
        layout_data = self.get_tree_layout(session_id)

        # Simplify for minimap - just positions and connections
        nodes = []
        edges = []

        with self._lock:
            tree = self._get_session(session_id)
            all_nodes = tree["nodes"]

            for node_id, pos in layout_data["layout"].items():
                node = all_nodes.get(node_id)
                if not node:
                    continue
                nodes.append({
                    "id": node_id,
                    "x": pos["x"],
                    "y": pos["y"],
                    "is_current": node_id == tree["current"],
                    "is_leaf": not node.get("children"),
                    "has_bookmark": node_id in [
                        b["node_id"] for b in tree.get("bookmarks", {}).values()
                    ],
                })

                # Add edges to children
                for child_id in node.get("children", {}).values():
                    if child_id in layout_data["layout"]:
                        edges.append({
                            "from": node_id,
                            "to": child_id,
                        })

        return {
            "nodes": nodes,
            "edges": edges,
            "bounds": layout_data["bounds"],
            "current": layout_data["current"],
        }

    def goto_node(self, session_id: str, node_id: str) -> dict:
        """Jump to any existing node in the session tree."""
        with self._lock:
            tree = self._get_session(session_id)
            if node_id not in tree["nodes"]:
                raise ValueError(f"Node {node_id!r} not found in session")
            # Push current to undo stack before jumping
            current_id = tree["current"]
            if current_id != node_id:
                self._push_undo(session_id, current_id)
            tree["current"] = node_id
            self._save_session(session_id, tree)
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

            self._save_session(session_id, tree)

        return {
            "merged_node": _public_node(merged_node, tree["nodes"]),
            "conflicts_resolved": resolved,
            "conflicts_unresolved": unresolved,
            "common_ancestor": common_ancestor,
        }

    # ── Bookmarks ──────────────────────────────────────────────────────────

    def add_bookmark(
        self, session_id: str, node_id: str, label: str = ""
    ) -> dict:
        """Bookmark a node for later reference."""
        with self._lock:
            tree = self._get_session(session_id)
            if node_id not in tree["nodes"]:
                raise ValueError(f"Node {node_id!r} not found")

            if "bookmarks" not in tree:
                tree["bookmarks"] = {}

            bookmark_id = str(uuid.uuid4())[:8]
            tree["bookmarks"][bookmark_id] = {
                "id": bookmark_id,
                "node_id": node_id,
                "label": label or f"Bookmark at depth {_depth(tree['nodes'][node_id], tree['nodes'])}",
                "created_at": time.time(),
            }
            self._save_session(session_id, tree)
            return tree["bookmarks"][bookmark_id]

    def remove_bookmark(self, session_id: str, bookmark_id: str) -> bool:
        """Remove a bookmark. Returns True if existed."""
        with self._lock:
            tree = self._get_session(session_id)
            bookmarks = tree.get("bookmarks", {})
            if bookmark_id not in bookmarks:
                return False
            del bookmarks[bookmark_id]
            self._save_session(session_id, tree)
            return True

    def list_bookmarks(self, session_id: str) -> list[dict]:
        """List all bookmarks for a session."""
        with self._lock:
            tree = self._get_session(session_id)
            bookmarks = tree.get("bookmarks", {})
            result = []
            for bm in bookmarks.values():
                node = tree["nodes"].get(bm["node_id"])
                if node:
                    result.append({
                        **bm,
                        "preview": node["text"][:100] + "..." if len(node["text"]) > 100 else node["text"],
                        "depth": _depth(node, tree["nodes"]),
                    })
            return sorted(result, key=lambda x: x["created_at"], reverse=True)

    def goto_bookmark(self, session_id: str, bookmark_id: str) -> dict:
        """Navigate to a bookmarked node."""
        with self._lock:
            tree = self._get_session(session_id)
            bookmarks = tree.get("bookmarks", {})
            if bookmark_id not in bookmarks:
                raise ValueError(f"Bookmark {bookmark_id!r} not found")
            node_id = bookmarks[bookmark_id]["node_id"]
        # Use goto_node which handles undo stack
        return self.goto_node(session_id, node_id)

    # ── Analytics ──────────────────────────────────────────────────────────

    def _track_choice(self, session_id: str, node_id: str, choice_index: int) -> None:
        """Track a choice selection for analytics (internal)."""
        with self._lock:
            tree = self._store.get(session_id)
            if not tree:
                return

            if "analytics" not in tree:
                tree["analytics"] = {"choices": {}, "total_choices": 0}

            analytics = tree["analytics"]
            key = f"{node_id}:{choice_index}"
            analytics["choices"][key] = analytics["choices"].get(key, 0) + 1
            analytics["total_choices"] = analytics.get("total_choices", 0) + 1
            self._store.put(session_id, tree)

    def auto_explore(
        self, session_id: str, num_paths: int = 3, depth: int = 2, llm=None
    ) -> list[dict]:
        """Auto-generate multiple branch paths in parallel for preview.

        Args:
            session_id: Session to explore
            num_paths: Number of parallel paths to generate (2-5)
            depth: How deep to explore each path (1-3)
            llm: LLM client for generation

        Returns:
            List of generated paths, each with nodes and final node text
        """
        if llm is None:
            raise ValueError("LLM client required for auto-explore")

        num_paths = max(2, min(5, num_paths))
        depth = max(1, min(3, depth))

        with self._lock:
            tree = self._get_session(session_id)
            start_node = self._walk_to_current(tree)
            choices = start_node.get("choices", [])
            context = tree.get("context", {})

        if len(choices) < num_paths:
            num_paths = len(choices)

        paths = []
        for i in range(num_paths):
            choice_text = choices[i] if i < len(choices) else f"Choice {i+1}"
            path_nodes = []
            current_text = start_node["text"]

            for d in range(depth):
                try:
                    result = llm.generate_json(
                        system_prompt=f"You are a creative storyteller. Genre: {context.get('genre', 'general')}. "
                                      "Return JSON with 'continuation' (200-300 words) and 'choices' (2-3 options).",
                        user_prompt=f"Story so far:\n{current_text[-2000:]}\n\n"
                                    f"The reader chose: {choice_text}\n\nContinue the story.",
                        temperature=0.9,
                    )
                    continuation = result.get("continuation") or result.get("text", "")
                    new_choices = result.get("choices", ["Continue", "Take a different path"])
                    if not isinstance(new_choices, list):
                        new_choices = ["Continue", "Take a different path"]

                    path_nodes.append({
                        "depth": d + 1,
                        "choice_made": choice_text,
                        "text": continuation,
                        "preview": continuation[:150] + "..." if len(continuation) > 150 else continuation,
                        "choices": new_choices[:3],
                    })
                    current_text = continuation
                    choice_text = new_choices[0] if new_choices else "Continue"
                except Exception as e:
                    path_nodes.append({
                        "depth": d + 1,
                        "choice_made": choice_text,
                        "text": f"[Generation failed: {e}]",
                        "preview": "[Generation failed]",
                        "choices": [],
                    })
                    break

            paths.append({
                "path_id": f"path_{i}",
                "initial_choice": choices[i] if i < len(choices) else f"Choice {i+1}",
                "initial_choice_index": i,
                "nodes": path_nodes,
                "final_preview": path_nodes[-1]["preview"] if path_nodes else "",
                "total_depth": len(path_nodes),
            })

        return paths

    # ── State Variables ─────────────────────────────────────────────────────

    def get_state_variables(self, session_id: str) -> dict:
        """Get current accumulated state variables for the session.

        State is computed by walking from root to current node and
        applying all state_changes along the path.
        """
        with self._lock:
            tree = self._get_session(session_id)
            path = self._get_path_to_node(tree["current"], tree["nodes"])

            state = {}
            for node_id in path:
                node = tree["nodes"].get(node_id)
                if node:
                    changes = node.get("state_changes", {})
                    for key, delta in changes.items():
                        state[key] = state.get(key, 0) + delta

            return state

    def _get_path_to_node(self, node_id: str, all_nodes: dict) -> list[str]:
        """Get path from root to node (inclusive)."""
        path = []
        current = all_nodes.get(node_id)
        while current:
            path.append(current["id"])
            if current["parent"] is None:
                break
            current = all_nodes.get(current["parent"])
        return list(reversed(path))

    def set_state_changes(
        self, session_id: str, node_id: str, state_changes: dict
    ) -> dict:
        """Set state changes for a node (e.g., {"gold": 10, "reputation": -5})."""
        with self._lock:
            tree = self._get_session(session_id)
            if node_id not in tree["nodes"]:
                raise ValueError(f"Node {node_id!r} not found")
            tree["nodes"][node_id]["state_changes"] = state_changes
            self._save_session(session_id, tree)
            return tree["nodes"][node_id]["state_changes"]

    def set_choice_conditions(
        self, session_id: str, node_id: str, conditions: list[dict]
    ) -> list[dict]:
        """Set conditions for choices (e.g., [{"index": 0, "requires": {"gold": 50}}])."""
        with self._lock:
            tree = self._get_session(session_id)
            if node_id not in tree["nodes"]:
                raise ValueError(f"Node {node_id!r} not found")
            tree["nodes"][node_id]["choice_conditions"] = conditions
            self._save_session(session_id, tree)
            return conditions

    def get_available_choices(self, session_id: str) -> list[dict]:
        """Get current node's choices with availability based on state conditions.

        Returns list of {index, text, available, requires, missing}.
        """
        with self._lock:
            tree = self._get_session(session_id)
            node = self._walk_to_current(tree)
            choices = node.get("choices", [])
            conditions = node.get("choice_conditions", [])
            current_state = {}

            # Compute current state
            path = self._get_path_to_node(tree["current"], tree["nodes"])
            for nid in path:
                n = tree["nodes"].get(nid)
                if n:
                    for key, delta in n.get("state_changes", {}).items():
                        current_state[key] = current_state.get(key, 0) + delta

            # Build condition lookup
            cond_lookup = {c.get("index"): c.get("requires", {}) for c in conditions}

            result = []
            for i, choice_text in enumerate(choices):
                requires = cond_lookup.get(i, {})
                missing = {}
                available = True

                for key, required_value in requires.items():
                    current_value = current_state.get(key, 0)
                    if current_value < required_value:
                        available = False
                        missing[key] = {"required": required_value, "current": current_value}

                result.append({
                    "index": i,
                    "text": choice_text,
                    "available": available,
                    "requires": requires,
                    "missing": missing,
                })

            return result

    def get_analytics(self, session_id: str) -> dict:
        """Get analytics for a session.

        Returns:
            dict with choice popularity, total choices, popular paths
        """
        with self._lock:
            tree = self._get_session(session_id)
            analytics = tree.get("analytics", {"choices": {}, "total_choices": 0})

            # Compute choice popularity per node
            node_popularity = {}
            for key, count in analytics.get("choices", {}).items():
                parts = key.rsplit(":", 1)
                if len(parts) != 2:
                    continue
                node_id, choice_idx = parts[0], int(parts[1])
                if node_id not in node_popularity:
                    node_popularity[node_id] = {"choices": {}, "total": 0}
                node_popularity[node_id]["choices"][choice_idx] = count
                node_popularity[node_id]["total"] += count

            # Find most popular choices per node
            popular_choices = []
            for node_id, data in node_popularity.items():
                node = tree["nodes"].get(node_id)
                if not node:
                    continue
                choices = node.get("choices", [])
                for idx, count in data["choices"].items():
                    if idx < len(choices):
                        popular_choices.append({
                            "node_id": node_id,
                            "choice_index": idx,
                            "choice_text": choices[idx],
                            "count": count,
                            "percentage": round(count / data["total"] * 100, 1) if data["total"] > 0 else 0,
                        })

            popular_choices.sort(key=lambda x: x["count"], reverse=True)

            return {
                "total_choices": analytics.get("total_choices", 0),
                "unique_paths": len(tree.get("nodes", {})),
                "popular_choices": popular_choices[:10],
                "node_popularity": {
                    nid: {"total": d["total"]} for nid, d in node_popularity.items()
                },
            }

    def get_merge_preview(
        self, session_id: str, node_a_id: str, node_b_id: str
    ) -> dict:
        """Get preview diff of two nodes before merging.

        Returns:
            dict with node_a, node_b, conflicts, common_ancestor, and path info
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
            common_ancestor_id = None
            for anc_id in ancestors_a:
                if anc_id in ancestors_b:
                    common_ancestor_id = anc_id
                    break

            # Get paths from common ancestor to each node
            path_a = self._get_path_from(common_ancestor_id, node_a_id, tree["nodes"]) if common_ancestor_id else []
            path_b = self._get_path_from(common_ancestor_id, node_b_id, tree["nodes"]) if common_ancestor_id else []

            # Detect conflicts
            conflicts = self._detect_conflicts(node_a, node_b, tree.get("context", {}))

            return {
                "node_a": {
                    "id": node_a_id,
                    "text": node_a["text"],
                    "choices": node_a["choices"],
                    "depth": _depth(node_a, tree["nodes"]),
                    "character_states": node_a.get("character_states", {}),
                },
                "node_b": {
                    "id": node_b_id,
                    "text": node_b["text"],
                    "choices": node_b["choices"],
                    "depth": _depth(node_b, tree["nodes"]),
                    "character_states": node_b.get("character_states", {}),
                },
                "common_ancestor": {
                    "id": common_ancestor_id,
                    "text": tree["nodes"][common_ancestor_id]["text"][:200] + "..." if common_ancestor_id else None,
                } if common_ancestor_id else None,
                "path_a": path_a,
                "path_b": path_b,
                "conflicts": conflicts,
                "can_merge": True,
            }

    def _get_path_from(self, from_id: str | None, to_id: str, all_nodes: dict) -> list[dict]:
        """Get path from one node to another (via parent chain)."""
        if from_id is None:
            return []
        path = []
        current = all_nodes.get(to_id)
        while current and current["id"] != from_id:
            path.append({
                "id": current["id"],
                "preview": current["text"][:80] + "..." if len(current["text"]) > 80 else current["text"],
            })
            if current["parent"] is None:
                break
            current = all_nodes.get(current["parent"])
        return list(reversed(path))

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
