"""Tab builder modules for StoryForge Gradio UI."""

from .onboarding_tab import build_onboarding_banner
from .pipeline_tab import build_pipeline_tab
from .story_tab import build_story_tab
from .simulation_tab import build_simulation_tab
from .video_tab import build_video_tab
from .review_tab import build_review_tab
from .export_tab import build_export_tab
from .account_tab import build_account_tab
from .settings_tab import build_settings_tab
from .analytics_tab import build_analytics_tab
from .reader_tab import build_reader_tab

__all__ = [
    "build_onboarding_banner",
    "build_pipeline_tab",
    "build_story_tab",
    "build_simulation_tab",
    "build_video_tab",
    "build_review_tab",
    "build_export_tab",
    "build_account_tab",
    "build_settings_tab",
    "build_analytics_tab",
    "build_reader_tab",
]
