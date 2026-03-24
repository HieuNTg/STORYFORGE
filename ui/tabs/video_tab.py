"""Video tab — storyboard display, video export, image prompts, and image generation."""

import gradio as gr


def build_video_tab(_t):
    """Build the video storyboard and export tab.

    Args:
        _t: i18n translation callable

    Returns:
        dict with video_output, video_export_btn, video_export_file,
        image_prompts_df, image_provider_dd, generate_images_btn,
        and image_gallery components.
    """
    video_output = gr.Textbox(
        label=_t("label.storyboard"), lines=20,
        interactive=False,
    )
    gr.Markdown(_t("output.video_export"))
    video_export_btn = gr.Button(
        _t("btn.export_video"), variant="secondary",
    )
    video_export_file = gr.File(
        label=_t("label.video_assets"),
    )

    with gr.Accordion(_t("label.image_prompts"), open=False):
        image_prompts_df = gr.Dataframe(
            headers=["Chapter", "DALL-E Prompt", "SD Prompt"],
            label=_t("label.image_prompts"),
            interactive=False,
        )

    gr.Markdown("---")
    with gr.Row():
        image_provider_dd = gr.Dropdown(
            choices=[
                (_t("provider_none"), "none"),
                (_t("provider_dalle"), "dalle"),
                (_t("provider_sd"), "sd-api"),
                ("Seedream 4.5", "seedream"),
            ],
            value="none",
            label=_t("label_image_provider"),
            scale=2,
        )
        generate_images_btn = gr.Button(
            _t("btn_generate_images"), variant="primary", scale=1,
        )

    image_gallery = gr.Gallery(
        label=_t("label_image_gallery"),
        columns=3,
        height="auto",
        visible=True,
    )

    character_gallery = gr.Gallery(
        label="Character References",
        columns=4,
        height="auto",
        visible=True,
    )

    gr.Markdown("---")
    gr.Markdown("### 🔊 Audio & Video")
    with gr.Row():
        tts_voice_dd = gr.Dropdown(
            choices=[("Nữ (HoaiMy)", "female"), ("Nam (NamMinh)", "male")],
            value="female",
            label="Giọng đọc",
            scale=1,
        )
        generate_tts_btn = gr.Button("Tạo Audio", variant="secondary", scale=1)
        compose_video_btn = gr.Button("Ghép Video MP4", variant="primary", scale=1)

    tts_audio_output = gr.File(label="Audio Files", file_count="multiple")
    video_output_file = gr.File(label="Video MP4")
    video_status = gr.Textbox(label="Trạng thái", lines=2, interactive=False)

    return {
        "video_output": video_output,
        "video_export_btn": video_export_btn,
        "video_export_file": video_export_file,
        "image_prompts_df": image_prompts_df,
        "image_provider_dd": image_provider_dd,
        "generate_images_btn": generate_images_btn,
        "image_gallery": image_gallery,
        "tts_voice_dd": tts_voice_dd,
        "generate_tts_btn": generate_tts_btn,
        "compose_video_btn": compose_video_btn,
        "tts_audio_output": tts_audio_output,
        "video_output_file": video_output_file,
        "video_status": video_status,
        "character_gallery": character_gallery,
    }
