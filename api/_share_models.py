"""Request models for the share routes + library-payload conversion.

Internal module for api/share_routes.py: the Pydantic request bodies and the
serialized-library-story → StoryDraft conversion live here so the route
handlers stay thin.
"""

from pydantic import BaseModel, Field


class CreateShareRequest(BaseModel):
    """Request body for creating a share from an active pipeline session."""

    session_id: str
    is_public: bool = False
    expires_days: int = 30


class LibraryCharacterPayload(BaseModel):
    """Character card data from a localStorage library story."""

    name: str = Field(max_length=200)
    role: str = Field(default="", max_length=200)
    personality: str = Field(default="", max_length=2000)
    motivation: str = Field(default="", max_length=2000)


class LibraryChapterPayload(BaseModel):
    """Chapter data from a localStorage library story (incl. comic pages)."""

    title: str = Field(max_length=500)
    content: str = Field(default="", max_length=400_000)
    summary: str = Field(default="", max_length=10_000)
    images: list[str] = Field(default_factory=list, max_length=200)


class LibraryShareRequest(BaseModel):
    """Share a library story (localStorage-only, no server session) to the
    public gallery. The frontend serializes the story and POSTs it here."""

    title: str = Field(min_length=1, max_length=500)
    genre: str = Field(default="", max_length=200)
    synopsis: str = Field(default="", max_length=10_000)
    chapters: list[LibraryChapterPayload] = Field(min_length=1, max_length=500)
    characters: list[LibraryCharacterPayload] = Field(
        default_factory=list, max_length=50
    )
    is_public: bool = True
    expires_days: int = Field(default=30, ge=1, le=365)
    replace_share_id: str = Field(default="", max_length=36)


def build_story_draft(req: LibraryShareRequest):
    """Convert a LibraryShareRequest payload into a StoryDraft."""
    from models.schemas import Character, Chapter, StoryDraft

    chapters = []
    for i, ch in enumerate(req.chapters, start=1):
        # Only same-origin /media/ URLs survive — anything else is dropped so
        # shared HTML can never embed external or traversal image sources.
        safe_images = [
            u.strip()
            for u in ch.images
            if isinstance(u, str) and u.strip().startswith("/media/") and ".." not in u
        ]
        chapters.append(
            Chapter(
                chapter_number=i,
                title=ch.title,
                content=ch.content,
                summary=ch.summary,
                images=safe_images,
            )
        )

    return StoryDraft(
        title=req.title,
        genre=req.genre or "Khác",
        synopsis=req.synopsis,
        characters=[
            Character(
                name=c.name,
                role=c.role or "phụ",
                personality=c.personality or "Chưa xác định",
                motivation=c.motivation,
            )
            for c in req.characters
        ],
        chapters=chapters,
    )
