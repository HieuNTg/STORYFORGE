"""Branching story tab — interactive story path selection."""

import gradio as gr
import logging

logger = logging.getLogger(__name__)


def build_branching_tab(_t, orchestrator_state):
    """Build the interactive story branching tab."""
    gr.Markdown("### Truyen Re Nhanh (Interactive)")
    gr.Markdown("Tao cac lua chon de nguoi doc quyet dinh huong di cua cau truyen.")

    tree_state = gr.State(None)

    with gr.Row():
        chapter_selector = gr.Dropdown(label="Chon chuong lam goc", choices=[])
        init_btn = gr.Button("Tai danh sach chuong", variant="secondary")

    create_btn = gr.Button("Tao cay truyen", variant="primary")

    current_content = gr.Textbox(
        label="Noi dung hien tai", lines=10, interactive=False
    )

    gen_choices_btn = gr.Button("Tao lua chon", variant="secondary")
    choice_display = gr.Radio(label="Lua chon cua ban", choices=[], interactive=True)

    with gr.Row():
        follow_btn = gr.Button("Theo huong nay", variant="primary")
        word_count = gr.Slider(500, 3000, value=1500, step=100, label="So tu")

    branch_status = gr.Textbox(label="Trang thai", interactive=False)
    path_display = gr.Textbox(label="Duong di da chon", interactive=False, lines=3)

    gr.Markdown("---")
    gr.Markdown("### Luu / Tai cay truyen")

    with gr.Row():
        save_tree_btn = gr.Button(_t("branch.save"), variant="secondary")
        load_dropdown = gr.Dropdown(label=_t("branch.saved_trees"), choices=[], scale=2)
        refresh_btn = gr.Button("↻", variant="secondary", scale=0)
        load_tree_btn = gr.Button(_t("branch.load"), variant="secondary")

    save_load_status = gr.Textbox(label="", interactive=False)

    def _load_chapters(orch_state):
        if not orch_state:
            return gr.update(choices=[]), "Chua co truyen"
        output = getattr(orch_state, "output", None)
        if not output:
            return gr.update(choices=[]), "Chua co du lieu"
        story = output.enhanced_story or output.story_draft
        if not story or not story.chapters:
            return gr.update(choices=[]), "Chua co chuong nao"
        choices = [f"Ch.{ch.chapter_number}: {ch.title}" for ch in story.chapters]
        return gr.update(choices=choices, value=choices[0] if choices else None), "San sang"

    def _create_tree(orch_state, ch_selection, tree):
        if not orch_state or not ch_selection:
            return tree, "", "Chon chuong truoc"
        output = getattr(orch_state, "output", None)
        if not output:
            return tree, "", "Chua co du lieu"
        story = output.enhanced_story or output.story_draft
        if not story:
            return tree, "", "Chua co truyen"
        try:
            ch_num = int(ch_selection.split(":")[0].replace("Ch.", "").strip())
        except (ValueError, IndexError):
            return tree, "", "Lua chon khong hop le"
        chapter = next((c for c in story.chapters if c.chapter_number == ch_num), None)
        if not chapter:
            return tree, "", "Khong tim thay chuong"
        from services.story_brancher import StoryBrancher
        brancher = StoryBrancher()
        new_tree = brancher.create_tree_from_chapter(chapter, story.genre)
        return new_tree, chapter.content[:3000], f"Da tao cay tu chuong {ch_num}"

    def _gen_choices(tree):
        if not tree:
            return tree, gr.update(choices=[]), "Tao cay truyen truoc"
        from services.story_brancher import StoryBrancher
        brancher = StoryBrancher()
        choices = brancher.generate_choices(tree, tree.current_node_id)
        if not choices:
            return tree, gr.update(choices=[]), "Khong tao duoc lua chon"
        labels = [f"{c.choice_id}: {c.text}" for c in choices]
        return tree, gr.update(choices=labels, value=labels[0]), f"Da tao {len(choices)} lua chon"

    def _follow_choice(tree, choice_label, wc):
        if not tree or not choice_label:
            return tree, "", "", "Chon lua chon truoc"
        choice_id = choice_label.split(":")[0].strip()
        node = tree.nodes.get(tree.current_node_id)
        if not node:
            return tree, "", "", "Loi: khong tim thay node"
        choice = next((c for c in node.choices if c.choice_id == choice_id), None)
        if not choice:
            return tree, "", "", "Loi: lua chon khong hop le"
        from services.story_brancher import StoryBrancher
        brancher = StoryBrancher()
        new_node = brancher.generate_branch(tree, tree.current_node_id, choice, int(wc))
        path_parts = []
        nid = new_node.node_id
        while nid:
            n = tree.nodes.get(nid)
            if n:
                path_parts.append(n.title[:40])
                nid = n.parent_id
            else:
                break
        path = " -> ".join(reversed(path_parts))
        return tree, new_node.content[:3000], path, f"Da tao nhanh moi: {new_node.title}"

    def _save_tree(tree):
        if not tree:
            return tree, _t("branch.no_trees")
        from services.story_brancher import StoryBrancher
        try:
            path = StoryBrancher.save_tree(tree)
            return tree, _t("branch.saved").format(path=path)
        except Exception as e:
            logger.error(f"Save tree failed: {e}")
            return tree, f"Loi luu: {e}"

    def _refresh_trees():
        from services.story_brancher import StoryBrancher
        saved = StoryBrancher.list_saved_trees()
        if not saved:
            return gr.update(choices=[], value=None)
        choices = [label for label, _ in saved]
        return gr.update(choices=choices, value=choices[0])

    def _load_tree(selected_label):
        if not selected_label:
            return None, "", _t("branch.no_trees")
        from services.story_brancher import StoryBrancher
        saved = StoryBrancher.list_saved_trees()
        path = next((p for label, p in saved if label == selected_label), None)
        if not path:
            return None, "", _t("branch.no_trees")
        try:
            tree = StoryBrancher.load_tree(path)
            node = tree.nodes.get(tree.current_node_id)
            content = node.content[:3000] if node else ""
            return tree, content, _t("branch.loaded").format(title=tree.title)
        except Exception as e:
            logger.error(f"Load tree failed: {e}")
            return None, "", f"Loi tai: {e}"

    init_btn.click(
        fn=_load_chapters,
        inputs=[orchestrator_state],
        outputs=[chapter_selector, branch_status],
    )
    create_btn.click(
        fn=_create_tree,
        inputs=[orchestrator_state, chapter_selector, tree_state],
        outputs=[tree_state, current_content, branch_status],
    )
    gen_choices_btn.click(
        fn=_gen_choices,
        inputs=[tree_state],
        outputs=[tree_state, choice_display, branch_status],
    )
    follow_btn.click(
        fn=_follow_choice,
        inputs=[tree_state, choice_display, word_count],
        outputs=[tree_state, current_content, path_display, branch_status],
    )

    save_tree_btn.click(
        fn=_save_tree,
        inputs=[tree_state],
        outputs=[tree_state, save_load_status],
    )
    refresh_btn.click(
        fn=_refresh_trees,
        inputs=[],
        outputs=[load_dropdown],
    )
    load_tree_btn.click(
        fn=_load_tree,
        inputs=[load_dropdown],
        outputs=[tree_state, current_content, save_load_status],
    )

    return {"tree_state": tree_state, "branch_status": branch_status}
