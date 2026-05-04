"""SQLAlchemy ORM models for PostgreSQL storage.

Uses SQLAlchemy 2.0+ declarative style with mapped_column and type annotations.
All tables include UUID primary keys and audit timestamps.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared declarative base — all ORM models inherit from this."""
    pass


# ---------------------------------------------------------------------------
# Helper: default UUID factory
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

class User(Base):
    """Application users."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    credits: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    # Valid values: viewer | creator | admin | superadmin  (see middleware/rbac.py)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="creator")
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    stories: Mapped[list["Story"]] = relationship("Story", back_populates="user", lazy="select")
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(
        "PipelineRun", back_populates="user", lazy="select"
    )

    __table_args__ = (
        Index("ix_users_username", "username"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!r} username={self.username!r}>"


class Story(Base):
    """Stories created by users."""

    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    genre: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    synopsis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # status: draft | enhanced | complete
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    chapter_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drama_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="stories")
    chapters: Mapped[list["Chapter"]] = relationship(
        "Chapter", back_populates="story", lazy="select", cascade="all, delete-orphan"
    )
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(
        "PipelineRun", back_populates="story", lazy="select"
    )
    feedback_entries: Mapped[list["Feedback"]] = relationship(
        "Feedback", back_populates="story", lazy="select", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_stories_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<Story id={self.id!r} title={self.title!r}>"


class Chapter(Base):
    """Individual chapters belonging to a story."""

    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    story_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Sprint 1 P6: per-chapter negotiated contract (nullable; set after reconciliation)
    negotiated_contract: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    contract_reconciliation_warnings: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Sprint 2 P3: per-chapter semantic verification findings (nullable; set by foreshadowing_verifier)
    semantic_findings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    story: Mapped["Story"] = relationship("Story", back_populates="chapters")

    __table_args__ = (
        Index("ix_chapters_story_id", "story_id"),
    )

    def __repr__(self) -> str:
        return f"<Chapter story={self.story_id!r} num={self.chapter_number}>"


class PipelineRun(Base):
    """Records each pipeline execution for auditing and analytics."""

    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    story_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("stories.id", ondelete="SET NULL"), nullable=True
    )
    genre: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    # status: running | completed | failed
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="running")
    layer_reached: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    duration_seconds: Mapped[Optional[float]] = mapped_column(nullable=True)
    token_usage: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Sprint 1 P6: L1→L2 handoff observability (all nullable; NULL for pre-migration rows)
    handoff_envelope: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    handoff_health: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    handoff_signals_version: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="pipeline_runs")
    story: Mapped[Optional["Story"]] = relationship("Story", back_populates="pipeline_runs")

    __table_args__ = (
        Index("ix_pipeline_runs_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<PipelineRun id={self.id!r} status={self.status!r}>"


class AuditLog(Base):
    """Immutable audit trail for security-relevant events."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    timestamp: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    result: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_audit_logs_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog action={self.action!r} user={self.user_id!r}>"


class Feedback(Base):
    """User feedback on individual chapters or full stories."""

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    story_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("stories.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    chapter_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # scores stored as JSONB: {"coherence": 4, "drama": 5, ...}
    scores: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    overall_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationships
    story: Mapped[Optional["Story"]] = relationship("Story", back_populates="feedback_entries")

    def __repr__(self) -> str:
        return f"<Feedback story={self.story_id!r} score={self.overall_score}>"


class EmbeddingCacheEntry(Base):
    """ORM mirror of the `embedding_cache` SQLite table (Sprint 2, P2).

    Note: the canonical storage is the separate `data/embedding_cache.db`
    SQLite file managed by `services/embedding_cache.py`. This model is here
    so P5/P7 diagnostics queries and any future migration tooling can reference
    the schema through SQLAlchemy without duplicating the column definitions.
    """

    __tablename__ = "embedding_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    vec: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_embedding_cache_model_id", "model_id"),
    )

    def __repr__(self) -> str:
        return f"<EmbeddingCacheEntry key={self.key[:8]!r}... model={self.model_id!r}>"


class Config(Base):
    """Key-value configuration store backed by PostgreSQL JSONB."""

    __tablename__ = "configs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("key", name="uq_configs_key"),
    )

    def __repr__(self) -> str:
        return f"<Config key={self.key!r}>"
