"""Formatting functions for StoryForge pipeline output.

Each function accepts a PipelineOutput object and a translation callable (_t),
and returns a formatted string for display in the Gradio UI.
"""


def format_story_output(output, _t) -> str:
    """Format story draft (Layer 1) output."""
    if not output or not output.story_draft:
        return ""
    d = output.story_draft
    text = f"# {d.title}\n\n"
    text += f"**Thể loại:** {d.genre}\n"
    text += f"**Tóm tắt:** {d.synopsis}\n\n"
    text += f"**Nhân vật:** {', '.join(c.name for c in d.characters)}\n\n"
    for ch in d.chapters:
        text += f"\n---\n## Chương {ch.chapter_number}: {ch.title}\n\n"
        text += ch.content[:2000] + "...\n"
    return text


def format_simulation_output(output, _t) -> str:
    """Format simulation result (Layer 2) output."""
    if not output or not output.simulation_result:
        return ""
    s = output.simulation_result
    text = "## Kết quả Mô phỏng\n\n"
    text += f"**Số sự kiện kịch tính:** {len(s.events)}\n"
    text += f"**Số bài viết agent:** {len(s.agent_posts)}\n\n"
    text += "### Sự kiện nổi bật:\n"
    for e in s.events[:10]:
        text += (
            f"- [{e.event_type}] {e.description} "
            f"(kịch tính: {e.drama_score:.1f})\n"
        )
    text += "\n### Gợi ý tăng kịch tính:\n"
    for sug in s.drama_suggestions[:5]:
        text += f"- {sug}\n"
    return text


def format_enhanced_output(output, _t) -> str:
    """Format enhanced story (Layer 2 output) display."""
    if not output or not output.enhanced_story:
        return ""
    es = output.enhanced_story
    text = f"# {es.title} (Phiên bản kịch tính)\n"
    text += f"**Điểm kịch tính:** {es.drama_score:.2f}/1.0\n\n"
    for ch in es.chapters:
        text += f"\n---\n## Chương {ch.chapter_number}: {ch.title}\n\n"
        text += ch.content[:2000] + "...\n"
    return text


def format_video_output(output, _t) -> str:
    """Format video script / storyboard (Layer 3) output."""
    if not output or not output.video_script:
        return ""
    vs = output.video_script
    text = f"# Kịch bản Video: {vs.title}\n"
    text += f"**Tổng thời lượng:** ~{vs.total_duration_seconds/60:.1f} phút\n"
    text += f"**Tổng panels:** {len(vs.panels)}\n"
    text += f"**Dòng thoại:** {len(vs.voice_lines)}\n\n"
    for p in vs.panels[:20]:
        text += (
            f"### Panel {p.panel_number} (Ch.{p.chapter_number})\n"
            f"- **Shot:** {p.shot_type.value} | **Camera:** {p.camera_movement}\n"
            f"- **Mô tả:** {p.description}\n"
        )
        if p.dialogue:
            text += f"- **Thoại:** {p.dialogue}\n"
        if p.image_prompt:
            text += f"- **Image prompt:** {p.image_prompt}\n"
        text += "\n"
    return text


def format_agent_output(output, _t) -> str:
    """Format agent review results."""
    if not output or not output.reviews:
        return ""
    text = "## Kết quả Đánh giá Agent\n\n"
    for r in output.reviews:
        status = "PASS" if r.approved else "FAIL"
        text += f"### {r.agent_name} (Layer {r.layer}, Vòng {r.iteration})\n"
        text += f"- Điểm: {r.score:.1f}/1.0 [{status}]\n"
        if r.issues:
            text += f"- Vấn đề: {'; '.join(r.issues[:3])}\n"
        if r.suggestions:
            text += f"- Gợi ý: {'; '.join(r.suggestions[:3])}\n"
        text += "\n"
    return text


def format_quality_output(output, _t) -> str:
    """Format quality scores display."""
    if not output or not output.quality_scores:
        return "*Chưa có điểm chất lượng. Chạy pipeline với 'Chấm điểm tự động' bật.*"
    text = "## Điểm Chất Lượng Truyện\n\n"
    for qs in output.quality_scores:
        text += f"### Layer {qs.scoring_layer} — Tổng: {qs.overall:.1f}/5\n\n"
        text += (
            f"| Chỉ tiêu | Điểm |\n|---|---|\n"
            f"| Mạch lạc | {qs.avg_coherence:.1f} |\n"
            f"| Nhân vật | {qs.avg_character:.1f} |\n"
            f"| Kịch tính | {qs.avg_drama:.1f} |\n"
            f"| Văn phong | {qs.avg_writing:.1f} |\n\n"
        )
        text += f"**Chương yếu nhất:** {qs.weakest_chapter}\n\n"
        text += "| Chương | Mạch lạc | Nhân vật | Kịch tính | Văn phong | Tổng | Ghi chú |\n"
        text += "|---|---|---|---|---|---|---|\n"
        for cs in qs.chapter_scores:
            text += (
                f"| {cs.chapter_number} | {cs.coherence:.1f} | "
                f"{cs.character_consistency:.1f} | {cs.drama:.1f} | "
                f"{cs.writing_quality:.1f} | {cs.overall:.1f} | "
                f"{cs.notes[:50]} |\n"
            )
        text += "\n---\n\n"

    if len(output.quality_scores) >= 2:
        l1 = output.quality_scores[0].overall
        l2 = output.quality_scores[1].overall
        diff = l2 - l1
        sign = "+" if diff > 0 else ""
        text += f"**Cải thiện Layer 1 → 2:** {sign}{diff:.1f} điểm\n"
    return text
