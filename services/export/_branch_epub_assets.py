"""Static assets/helpers for the branch EPUB exporter.

Internal module for ``branch_epub_exporter``: path enumeration over the branch
tree and the EPUB stylesheet. Kept separate so the exporter module stays under
the 200-line rule.
"""


def enumerate_paths(root_id: str, nodes: dict) -> list[list[dict]]:
    """Enumerate all unique paths from root to leaves."""
    paths = []

    def dfs(node_id: str, current_path: list[dict], choice_made: str = ""):
        node = nodes.get(node_id)
        if not node:
            return

        current_path.append(
            {
                "node_id": node_id,
                "choice_made": choice_made,
            }
        )

        children = node.get("children", {})
        if not children:
            # Leaf node - save this path
            paths.append(list(current_path))
        else:
            # Continue to children
            choices = node.get("choices", [])
            for child_key, child_id in children.items():
                try:
                    choice_idx = int(child_key)
                    choice_text = (
                        choices[choice_idx] if choice_idx < len(choices) else ""
                    )
                except (ValueError, IndexError):
                    choice_text = child_key
                dfs(child_id, current_path, choice_text)

        current_path.pop()

    dfs(root_id, [])
    return paths


def get_css() -> str:
    return """
body {
    font-family: Georgia, serif;
    line-height: 1.8;
    margin: 1em;
    color: #333;
}
h1.chapter-title {
    font-size: 1.8em;
    color: #222;
    border-bottom: 2px solid #ccc;
    padding-bottom: 0.3em;
    margin-bottom: 1em;
}
.path-info {
    color: #666;
    font-style: italic;
    margin-bottom: 1.5em;
}
.story-section {
    margin: 1em 0;
    text-align: justify;
}
.choice-made {
    background: #f5f5f5;
    padding: 0.5em 1em;
    border-left: 3px solid #4a90d9;
    margin: 1em 0;
    color: #555;
}
.choices {
    background: #fffaed;
    padding: 1em;
    border: 1px solid #e0d5c0;
    margin-top: 2em;
}
.choices ul {
    margin: 0.5em 0;
    padding-left: 1.5em;
}
.choices li {
    margin: 0.3em 0;
}
"""
