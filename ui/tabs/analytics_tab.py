"""Analytics tab — reading metrics, emotion arcs, pacing visualization."""
import gradio as gr
import logging

logger = logging.getLogger(__name__)

_HAS_PLOTLY = False
try:
    import plotly  # noqa: F401
    _HAS_PLOTLY = True
except ImportError:
    pass

_PLOTLY_MISSING_MSG = (
    "Chưa cài đặt Plotly. Chạy: `pip install plotly` để xem biểu đồ.\n"
    "Thống kê vẫn hiển thị bình thường."
)


def _create_pacing_chart(analytics: dict) -> object:
    """Create pacing chart (word count + dialogue ratio per chapter)."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        pacing = analytics.get("pacing_data", {})
        chapters = pacing.get("chapter_numbers", [])
        words = pacing.get("word_counts", [])
        dialogue = pacing.get("dialogue_ratios", [])

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(x=chapters, y=words, name="Số từ", marker_color="#6366f1", opacity=0.7),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(x=chapters, y=[d * 100 for d in dialogue], name="% Đối thoại",
                       mode="lines+markers", line=dict(color="#e74c3c", width=2)),
            secondary_y=True,
        )
        fig.update_layout(
            title="Nhịp độ truyện theo chương",
            xaxis_title="Chương",
            height=400,
            template="plotly_white",
        )
        fig.update_yaxes(title_text="Số từ", secondary_y=False)
        fig.update_yaxes(title_text="% Đối thoại", secondary_y=True)
        return fig
    except ImportError:
        logger.warning("Plotly not installed — chart generation skipped")
        return None


def _create_emotion_chart(emotion_data: dict) -> object:
    """Create emotion arc visualization."""
    try:
        import plotly.graph_objects as go

        chapters = emotion_data.get("chapter_numbers", [])
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chapters, y=emotion_data.get("positivity", []),
            name="Tích cực", mode="lines+markers",
            line=dict(color="#2ecc71", width=2), fill="tozeroy",
            fillcolor="rgba(46,204,113,0.1)",
        ))
        fig.add_trace(go.Scatter(
            x=chapters, y=emotion_data.get("negativity", []),
            name="Tiêu cực", mode="lines+markers",
            line=dict(color="#e74c3c", width=2), fill="tozeroy",
            fillcolor="rgba(231,76,60,0.1)",
        ))
        fig.add_trace(go.Scatter(
            x=chapters, y=emotion_data.get("tension", []),
            name="Căng thẳng", mode="lines+markers",
            line=dict(color="#f39c12", width=2, dash="dash"),
        ))
        fig.update_layout(
            title="Cung bậc cảm xúc theo chương",
            xaxis_title="Chương",
            yaxis_title="Tần suất (%)",
            height=400,
            template="plotly_white",
        )
        return fig
    except ImportError:
        logger.warning("Plotly not installed — chart generation skipped")
        return None


def _create_valence_chart(emotion_data: dict) -> object:
    """Create emotional valence chart (positive vs negative balance)."""
    try:
        import plotly.graph_objects as go

        chapters = emotion_data.get("chapter_numbers", [])
        valence = emotion_data.get("emotional_valence", [])
        colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in valence]

        fig = go.Figure(go.Bar(
            x=chapters, y=valence, marker_color=colors,
            name="Cân bằng cảm xúc",
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.update_layout(
            title="Cân bằng cảm xúc (Tích cực ↑ / Tiêu cực ↓)",
            xaxis_title="Chương",
            yaxis_title="Valence (-1 đến +1)",
            height=350,
            template="plotly_white",
        )
        return fig
    except ImportError:
        logger.warning("Plotly not installed — chart generation skipped")
        return None


def _create_llm_emotion_chart(llm_data: dict) -> object:
    """Create detailed emotion chart from LLM data."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        chapters = llm_data.get("chapter_numbers", [])
        if not chapters:
            return None

        fig = make_subplots(rows=2, cols=1, subplot_titles=("Cảm xúc theo chương", "Tổng hợp cảm xúc"),
                            row_heights=[0.65, 0.35], vertical_spacing=0.12)

        emotions = {
            "Vui": ("joy", "#2ecc71"),
            "Buồn": ("sadness", "#3498db"),
            "Giận": ("anger", "#e74c3c"),
            "Sợ": ("fear", "#9b59b6"),
            "Bất ngờ": ("surprise", "#f39c12"),
            "Căng thẳng": ("tension", "#e67e22"),
            "Lãng mạn": ("romance", "#e91e63"),
        }

        for label, (key, color) in emotions.items():
            values = llm_data.get(key, [])
            if values:
                fig.add_trace(
                    go.Scatter(x=chapters, y=values, name=label, mode="lines+markers",
                               line=dict(color=color, width=2)),
                    row=1, col=1,
                )

        # Average emotions bar chart
        avg_emotions = {}
        for label, (key, color) in emotions.items():
            values = llm_data.get(key, [])
            if values:
                avg_emotions[label] = sum(values) / len(values)

        if avg_emotions:
            fig.add_trace(
                go.Bar(x=list(avg_emotions.keys()), y=list(avg_emotions.values()),
                       marker_color=[emotions[k][1] for k in avg_emotions.keys()],
                       name="Trung bình"),
                row=2, col=1,
            )

        fig.update_layout(height=700, template="plotly_white", showlegend=True)
        fig.update_xaxes(title_text="Chương", row=1, col=1)
        fig.update_yaxes(title_text="Cường độ (0-10)", row=1, col=1)
        fig.update_yaxes(title_text="Trung bình", row=2, col=1)
        return fig
    except ImportError:
        logger.warning("Plotly not installed — chart generation skipped")
        return None


def build_analytics_tab(_t, orchestrator_state):
    """Build the analytics dashboard tab.

    Args:
        _t: i18n translation callable
        orchestrator_state: gr.State holding the PipelineOrchestrator instance

    Returns:
        dict of components.
    """
    gr.Markdown(_t("analytics.title"))

    if not _HAS_PLOTLY:
        gr.Markdown(
            f"**Warning:** {_t('analytics.plotly_missing')}",
        )

    analyze_btn = gr.Button(_t("analytics.analyze_btn"), variant="primary")

    with gr.Row():
        with gr.Column(scale=1):
            stats_json = gr.JSON(label="Thống kê tổng quan")
        with gr.Column(scale=1):
            reading_info = gr.Markdown(_t("analytics.placeholder"))

    with gr.Row():
        pacing_plot = gr.Plot(label="Nhịp độ truyện")
    with gr.Row():
        emotion_plot = gr.Plot(label="Cung bậc cảm xúc")
    with gr.Row():
        valence_plot = gr.Plot(label="Cân bằng cảm xúc")

    gr.Markdown("---")
    gr.Markdown("#### Phân tích cảm xúc chi tiết (LLM)")
    llm_emotion_btn = gr.Button(_t("analytics.llm_btn"), variant="secondary")
    llm_emotion_plot = gr.Plot(label="Cảm xúc chi tiết (LLM)")
    llm_emotion_table = gr.Dataframe(
        label="Chi tiết cảm xúc theo chương",
        headers=["Chương", "Cảm xúc chính", "Tóm tắt"],
        visible=True,
    )

    def _run_llm_emotions(orch_state):
        if orch_state is None:
            return None, []
        try:
            from services.story_analytics import StoryAnalytics
            story = orch_state.output.enhanced_story or orch_state.output.story_draft
            if not story or not story.chapters:
                return None, []

            llm_data = StoryAnalytics.extract_emotion_arc_llm(story.chapters)
            chart = _create_llm_emotion_chart(llm_data)

            # Build table data
            table_data = []
            for i, ch_num in enumerate(llm_data.get("chapter_numbers", [])):
                dominant = llm_data["dominant_emotions"][i] if i < len(llm_data["dominant_emotions"]) else ""
                summary = llm_data["summaries"][i] if i < len(llm_data["summaries"]) else ""
                table_data.append([f"Ch.{ch_num}", dominant, summary])

            return chart, table_data
        except Exception as e:
            logger.error(f"LLM emotion error: {e}")
            return None, [[f"Lỗi: {e}", "", ""]]

    llm_emotion_btn.click(
        fn=_run_llm_emotions,
        inputs=[orchestrator_state],
        outputs=[llm_emotion_plot, llm_emotion_table],
    )

    def _run_analytics(orch_state):
        if orch_state is None:
            return {}, "*Chưa có truyện*", None, None, None
        try:
            from services.story_analytics import StoryAnalytics

            story = orch_state.output.enhanced_story or orch_state.output.story_draft
            if not story or not story.chapters:
                return {}, "*Chưa có truyện*", None, None, None

            analytics = StoryAnalytics.analyze_story(story)
            emotion_data = StoryAnalytics.extract_emotion_arc(story.chapters)

            # Summary markdown
            summary = (
                f"**Tổng số từ:** {analytics['total_words']:,}\n\n"
                f"**Số chương:** {analytics['total_chapters']}\n\n"
                f"**Thời gian đọc:** ~{analytics['reading_time_minutes']} phút\n\n"
                f"**TB từ/chương:** {analytics['avg_words_per_chapter']:,}\n\n"
                f"**TB từ/câu:** {analytics['avg_sentence_length']:.1f}\n\n"
                f"**Tỷ lệ đối thoại:** {analytics['dialogue_ratio']:.1%}\n\n"
            )

            # Overview stats (without chapter_stats to keep JSON clean)
            overview = {k: v for k, v in analytics.items() if k not in ("chapter_stats", "pacing_data")}

            if not _HAS_PLOTLY:
                return overview, summary + f"\n\n**Lưu ý:** {_PLOTLY_MISSING_MSG}", None, None, None

            pacing_fig = _create_pacing_chart(analytics)
            emotion_fig = _create_emotion_chart(emotion_data)
            valence_fig = _create_valence_chart(emotion_data)

            return overview, summary, pacing_fig, emotion_fig, valence_fig
        except Exception as e:
            logger.error(f"Analytics error: {e}")
            return {"error": str(e)}, f"*Lỗi: {e}*", None, None, None

    analyze_btn.click(
        fn=_run_analytics,
        inputs=[orchestrator_state],
        outputs=[stats_json, reading_info, pacing_plot, emotion_plot, valence_plot],
    )

    return {
        "stats_json": stats_json,
        "reading_info": reading_info,
        "pacing_plot": pacing_plot,
        "emotion_plot": emotion_plot,
        "valence_plot": valence_plot,
        "llm_emotion_plot": llm_emotion_plot,
        "llm_emotion_table": llm_emotion_table,
    }
