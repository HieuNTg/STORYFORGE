"""Branching story tab — interactive story path selection."""

import gradio as gr
import logging

logger = logging.getLogger(__name__)


def build_branching_tab(_t, orchestrator_state):
    """Build the interactive story branching tab."""
    gr.Markdown("### Truyện Rẽ Nhánh (Interactive)")
    gr.Markdown("Tạo các lựa chọn để người đọc quyết định hướng đi của câu truyện.")

    tree_state = gr.State(None)

    with gr.Row():
        chapter_selector = gr.Dropdown(label="Chọn chương làm gốc", choices=[])
        init_btn = gr.Button("Tải danh sách chương", variant="secondary")

    create_btn = gr.Button("Tạo cây truyện", variant="primary")

    current_content = gr.Textbox(
        label="Nội dung hiện tại", lines=10, interactive=False
    )

    gen_choices_btn = gr.Button("Tạo lựa chọn", variant="secondary")
    choice_display = gr.Radio(label="Lựa chọn của bạn", choices=[], interactive=True)

    with gr.Row():
        follow_btn = gr.Button("Theo hướng này", variant="primary")
        word_count = gr.Slider(500, 3000, value=1500, step=100, label="Số từ")

    branch_status = gr.Textbox(label="Trạng thái", interactive=False)
    path_display = gr.Textbox(label="Đường đi đã chọn", interactive=False, lines=3)

    gr.Markdown("---")
    gr.Markdown("### Lưu / Tải cây truyện")

    with gr.Row():
        save_tree_btn = gr.Button(_t("branch.save"), variant="secondary")
        load_dropdown = gr.Dropdown(label=_t("branch.saved_trees"), choices=[], scale=2)
        refresh_btn = gr.Button("↻", variant="secondary", scale=0)
        load_tree_btn = gr.Button(_t("branch.load"), variant="secondary")

    save_load_status = gr.Textbox(label="", interactive=False)

    def _load_chapters(orch_state):
        if not orch_state:
            return gr.update(choices=[]), "Chưa có truyện"
        output = getattr(orch_state, "output", None)
        if not output:
            return gr.update(choices=[]), "Chưa có dữ liệu"
        story = output.enhanced_story or output.story_draft
        if not story or not story.chapters:
            return gr.update(choices=[]), "Chưa có chương nào"
        choices = [f"Ch.{ch.chapter_number}: {ch.title}" for ch in story.chapters]
        return gr.update(choices=choices, value=choices[0] if choices else None), "Sẵn sàng"

    def _create_tree(orch_state, ch_selection, tree):
        if not orch_state or not ch_selection:
            return tree, "", "Chọn chương trước"
        output = getattr(orch_state, "output", None)
        if not output:
            return tree, "", "Chưa có dữ liệu"
        story = output.enhanced_story or output.story_draft
        if not story:
            return tree, "", "Chưa có truyện"
        try:
            ch_num = int(ch_selection.split(":")[0].replace("Ch.", "").strip())
        except (ValueError, IndexError):
            return tree, "", "Lựa chọn không hợp lệ"
        chapter = next((c for c in story.chapters if c.chapter_number == ch_num), None)
        if not chapter:
            return tree, "", "Không tìm thấy chương"
        from services.story_brancher import StoryBrancher
        brancher = StoryBrancher()
        new_tree = brancher.create_tree_from_chapter(chapter, story.genre)
        return new_tree, chapter.content[:3000], f"Đã tạo cây từ chương {ch_num}"

    def _gen_choices(tree):
        if not tree:
            return tree, gr.update(choices=[]), "Tạo cây truyện trước"
        from services.story_brancher import StoryBrancher
        brancher = StoryBrancher()
        choices = brancher.generate_choices(tree, tree.current_node_id)
        if not choices:
            return tree, gr.update(choices=[]), "Không tạo được lựa chọn"
        labels = [f"{c.choice_id}: {c.text}" for c in choices]
        return tree, gr.update(choices=labels, value=labels[0]), f"Đã tạo {len(choices)} lựa chọn"

    def _follow_choice(tree, choice_label, wc):
        if not tree or not choice_label:
            return tree, "", "", "Chọn lựa chọn trước"
        choice_id = choice_label.split(":")[0].strip()
        node = tree.nodes.get(tree.current_node_id)
        if not node:
            return tree, "", "", "Lỗi: không tìm thấy node"
        choice = next((c for c in node.choices if c.choice_id == choice_id), None)
        if not choice:
            return tree, "", "", "Lỗi: lựa chọn không hợp lệ"
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
        return tree, new_node.content[:3000], path, f"Đã tạo nhánh mới: {new_node.title}"

    def _save_tree(tree):
        if not tree:
            return tree, _t("branch.no_trees")
        from services.story_brancher import StoryBrancher
        try:
            path = StoryBrancher.save_tree(tree)
            return tree, _t("branch.saved").format(path=path)
        except Exception as e:
            logger.error(f"Save tree failed: {e}")
            return tree, f"Lỗi lưu: {e}"

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
            return None, "", f"Lỗi tải: {e}"

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
