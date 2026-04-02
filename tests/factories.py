"""
tests/factories.py — StoryForge test data factories

Provides reusable factory functions and pytest fixtures for building
well-formed test objects without repeating boilerplate across test files.

Usage in test files
───────────────────
    from tests.factories import create_test_story, create_test_config

    def test_something():
        story = create_test_story("My Story", chapters=3)
        cfg   = create_test_config(model="gpt-4o-mini")

Or use the pytest fixtures directly:

    def test_something(mock_story, mock_config):
        ...

Design principles
─────────────────
- Every factory has sensible defaults so callers only override what matters.
- Factories return real model/dataclass instances (not MagicMocks) so
  validation logic runs and type checkers are happy.
- Fixtures call the factories, keeping fixture code minimal.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional
from unittest.mock import MagicMock

import pytest

from config import LLMConfig, PipelineConfig
from models.schemas import (
    Chapter,
    Character,
    ChapterOutline,
    EnhancedStory,
    PipelineOutput,
    StoryDraft,
    WorldSetting,
)
from models.schemas import UserProfile


# ============================================================================
# Low-level object builders (not fixtures — call directly from test code)
# ============================================================================


def build_character(
    name: str = "Test Character",
    role: str = "protagonist",
    personality: str = "Brave and curious",
    motivation: str = "Seek the truth",
    background: str = "Orphan raised by monks",
    relationships: Optional[list[str]] = None,
) -> Character:
    """Return a minimal valid Character instance."""
    return Character(
        name=name,
        role=role,
        personality=personality,
        motivation=motivation,
        background=background,
        relationships=relationships or [],
    )


def build_chapter(
    number: int = 1,
    title: str = "Chapter One",
    content: str = "The hero stepped forward.",
    summary: str = "The hero begins their journey.",
) -> Chapter:
    """Return a minimal valid Chapter instance."""
    return Chapter(
        chapter_number=number,
        title=title,
        content=content,
        summary=summary,
        word_count=len(content.split()),
    )


def build_world(
    name: str = "Test World",
    description: str = "A world of endless possibility.",
    rules: Optional[list[str]] = None,
    locations: Optional[list[str]] = None,
    era: str = "Fantasy age",
) -> WorldSetting:
    """Return a minimal valid WorldSetting instance."""
    return WorldSetting(
        name=name,
        description=description,
        rules=rules or ["Magic exists", "Technology is rare"],
        locations=locations or ["The Capital", "The Dark Forest"],
        era=era,
    )


# ============================================================================
# High-level factory functions (primary API for test authors)
# ============================================================================


def create_test_story(
    title: str = "Test Story",
    genre: str = "fantasy",
    chapters: int = 5,
    synopsis: str = "A hero's journey through an enchanted land.",
) -> StoryDraft:
    """
    Build a StoryDraft with `chapters` auto-generated chapters.

    Example
    -------
        story = create_test_story("Dragon Quest", chapters=3)
        assert len(story.chapters) == 3
    """
    protagonist = build_character(name="Hero", role="protagonist")
    antagonist = build_character(name="Villain", role="antagonist")
    world = build_world()

    outlines = [
        ChapterOutline(
            chapter_number=i,
            title=f"Chapter {i}",
            summary=f"Events of chapter {i}.",
        )
        for i in range(1, chapters + 1)
    ]

    chapter_list = [
        build_chapter(
            number=i,
            title=f"Chapter {i}",
            content=f"Chapter {i} content. The story progresses significantly.",
            summary=f"Summary of chapter {i}.",
        )
        for i in range(1, chapters + 1)
    ]

    return StoryDraft(
        title=title,
        genre=genre,
        synopsis=synopsis,
        characters=[protagonist, antagonist],
        world=world,
        outlines=outlines,
        chapters=chapter_list,
    )


def create_test_config(
    model: str = "gpt-4o-mini",
    api_key: str = "test-api-key",
    num_chapters: int = 5,
    language: str = "en",
) -> MagicMock:
    """
    Build a MagicMock that quacks like a ConfigManager instance.

    The mock exposes `.llm` (LLMConfig) and `.pipeline` (PipelineConfig) as
    real dataclass instances so attribute access works naturally.

    Example
    -------
        cfg = create_test_config(model="gpt-4o")
        assert cfg.llm.model == "gpt-4o"
    """
    llm = LLMConfig(
        api_key=api_key,
        model=model,
        cache_enabled=False,
        fallback_models=[],
    )
    pipeline = PipelineConfig(
        num_chapters=num_chapters,
        language=language,
    )

    cfg = MagicMock()
    cfg.llm = llm
    cfg.pipeline = pipeline
    return cfg


def create_test_user(
    user_id: str = "test-user-001",
    username: str = "testuser",
    credits: int = 20,
    tier: str = "free",
    total_stories_created: int = 0,
) -> UserProfile:
    """
    Return a UserProfile suitable for credit/auth tests.

    Example
    -------
        user = create_test_user(credits=100, tier="pro")
    """
    return UserProfile(
        user_id=user_id,
        username=username,
        credits=credits,
        tier=tier,
        total_stories_created=total_stories_created,
    )


def create_enhanced_story(
    base_story: Optional[StoryDraft] = None,
    drama_score: float = 0.75,
) -> EnhancedStory:
    """
    Wrap a StoryDraft in an EnhancedStory with a configurable drama score.

    Example
    -------
        enhanced = create_enhanced_story(drama_score=0.9)
    """
    story = base_story or create_test_story()
    return EnhancedStory(
        title=story.title + " (Enhanced)",
        genre=story.genre,
        chapters=story.chapters,
        drama_score=drama_score,
        enhancement_notes=["Conflict intensified", "Pacing improved"],
    )


# ============================================================================
# Pytest fixtures — thin wrappers around the factory functions
# ============================================================================


@pytest.fixture
def mock_story() -> StoryDraft:
    """Provide a default 5-chapter StoryDraft."""
    return create_test_story()


@pytest.fixture
def mock_chapter() -> Chapter:
    """Provide a single Chapter instance."""
    return build_chapter()


@pytest.fixture
def mock_user() -> UserProfile:
    """Provide a default free-tier UserProfile."""
    return create_test_user()


@pytest.fixture
def mock_config() -> MagicMock:
    """Provide a ConfigManager-like mock with gpt-4o-mini defaults."""
    return create_test_config()


@pytest.fixture
def mock_llm_response() -> MagicMock:
    """
    Provide a MagicMock LLM client whose generate/generate_json methods
    return predictable values.

    Useful for services that accept a client rather than instantiating one.
    """
    client = MagicMock()
    client.generate.return_value = "Mocked LLM response text."
    client.generate_json.return_value = {
        "score": 0.8,
        "issues": [],
        "suggestions": ["Looks good"],
    }
    return client


@pytest.fixture
def five_chapter_story() -> StoryDraft:
    """Alias fixture — explicit about chapter count for readability."""
    return create_test_story(chapters=5)


@pytest.fixture
def ten_chapter_story() -> StoryDraft:
    """Provide a larger story for pagination / performance tests."""
    return create_test_story(title="Long Saga", chapters=10)
