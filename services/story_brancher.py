"""Interactive story branching — generate decision points and branch content."""

import json
import logging
import os
import re
import time
import uuid
from models.schemas import StoryNode, BranchChoice, StoryTree, Chapter
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

BRANCHES_DIR = "data/branches"

BRANCH_POINT_PROMPT = """Dua tren noi dung chuong sau, tao 2-3 lua chon
cho nguoi doc de tiep tuc cau truyen theo huong khac nhau.

Chuong {chapter_number}: {title}
---
{content_excerpt}
---
The loai: {genre}

Tra ve JSON:
{{
  "choices": [
    {{"text": "<lua chon 1>", "direction": "<mo ta ngan huong di>"}},
    {{"text": "<lua chon 2>", "direction": "<mo ta ngan huong di>"}}
  ]
}}"""

BRANCH_CONTENT_PROMPT = """Viet tiep chuong truyen theo huong da chon.

Boi canh truoc do:
{previous_content_excerpt}

Lua chon cua nguoi doc: {choice_text}
Huong di: {direction}
The loai: {genre}

Yeu cau:
- Khoang {word_count} tu
- Tiep noi tu nhien tu noi dung truoc
- Ket thuc o mot diem co the tao them lua chon

Bat dau viet:"""


class StoryBrancher:
    """Generate and manage branching story paths."""

    def __init__(self):
        self.llm = LLMClient()

    def create_tree_from_chapter(self, chapter: Chapter, genre: str) -> StoryTree:
        """Initialize a story tree from an existing chapter."""
        root = StoryNode(
            node_id="root",
            chapter_number=chapter.chapter_number,
            title=chapter.title,
            content=chapter.content,
        )
        tree = StoryTree(
            root_id="root",
            nodes={"root": root},
            title=chapter.title,
            genre=genre,
        )
        return tree

    def generate_choices(self, tree: StoryTree, node_id: str) -> list[BranchChoice]:
        """Generate decision choices for a node."""
        node = tree.nodes.get(node_id)
        if not node:
            return []
        try:
            result = self.llm.generate_json(
                system_prompt="Ban la nha van interactive fiction. Tra ve JSON.",
                user_prompt=BRANCH_POINT_PROMPT.format(
                    chapter_number=node.chapter_number,
                    title=node.title,
                    content_excerpt=node.content[-2000:],
                    genre=tree.genre,
                ),
                temperature=0.8,
                model_tier="cheap",
            )
            choices = []
            for i, c in enumerate(result.get("choices", [])[:3]):
                choice = BranchChoice(
                    choice_id=f"{node_id}_c{i}",
                    text=c.get("text", f"Lua chon {i+1}"),
                    next_node_id="",
                    state_delta={"direction": c.get("direction", "")},
                )
                choices.append(choice)
            node.choices = choices
            return choices
        except Exception as e:
            logger.warning(f"Choice generation failed: {e}")
            return []

    def generate_branch(
        self,
        tree: StoryTree,
        parent_id: str,
        choice: BranchChoice,
        word_count: int = 1500,
    ) -> StoryNode:
        """Generate content for a branch choice. Returns new node."""
        parent = tree.nodes.get(parent_id)
        if not parent:
            raise ValueError(f"Parent node {parent_id} not found")

        new_id = f"node_{uuid.uuid4().hex[:8]}"
        direction = choice.state_delta.get("direction", choice.text)

        try:
            content = self.llm.generate(
                system_prompt="Ban la nha van interactive fiction.",
                user_prompt=BRANCH_CONTENT_PROMPT.format(
                    previous_content_excerpt=parent.content[-1500:],
                    choice_text=choice.text,
                    direction=direction,
                    genre=tree.genre,
                    word_count=word_count,
                ),
                temperature=0.8,
            )
        except Exception as e:
            logger.error(f"Branch generation failed: {e}")
            content = f"[Loi tao nhanh: {e}]"

        new_node = StoryNode(
            node_id=new_id,
            chapter_number=parent.chapter_number + 1,
            title=f"Nhanh: {choice.text[:50]}",
            content=content.strip(),
            parent_id=parent_id,
        )
        tree.nodes[new_id] = new_node
        choice.next_node_id = new_id
        tree.current_node_id = new_id
        return new_node

    @staticmethod
    def save_tree(tree: StoryTree, filename: str = "") -> str:
        """Save StoryTree to JSON. Returns file path."""
        os.makedirs(BRANCHES_DIR, exist_ok=True)
        if not filename:
            safe_title = re.sub(r'[^\w\-]', '_', tree.title)[:30]
            filename = f"{safe_title}_{int(time.time())}.json"
        path = os.path.join(BRANCHES_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(tree.model_dump(), f, ensure_ascii=False, indent=2)
        logger.info(f"Tree saved: {path}")
        return path

    @staticmethod
    def load_tree(path: str) -> StoryTree:
        """Load StoryTree from JSON file. Raises ValueError on corrupt data."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Corrupt tree file '{path}': {e}") from e
        if not isinstance(data, dict) or "root_id" not in data:
            raise ValueError(f"Invalid tree format in '{path}': missing required fields")
        return StoryTree.model_validate(data)

    @staticmethod
    def list_saved_trees() -> list:
        """List saved trees. Returns [(display_name, path), ...]."""
        if not os.path.isdir(BRANCHES_DIR):
            return []
        results = []
        for fname in sorted(os.listdir(BRANCHES_DIR), reverse=True):
            if fname.endswith(".json"):
                path = os.path.join(BRANCHES_DIR, fname)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    title = data.get("title", fname)
                    nodes = len(data.get("nodes", {}))
                    results.append((f"{title} ({nodes} nodes)", path))
                except Exception:
                    results.append((fname, path))
        return results
