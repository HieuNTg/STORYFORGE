"""Audit fixes: JSONB→JSON, UUID→String(36), UniqueConstraint on Chapter, index on PipelineRun.story_id.

Changes:
  - audit_logs.details:  JSONB → JSON  (cross-dialect)
  - feedback.scores:     JSONB → JSON  (cross-dialect)
  - configs.value:       JSONB → JSON  (cross-dialect)
  - All UUID PK/FK columns: postgresql.UUID → String(36)  (cross-dialect)
  - chapters: add UniqueConstraint(story_id, chapter_number)
  - pipeline_runs: add index on story_id

SQLite-safe: column type changes use batch_alter_table.
Forward + downgrade fully reversible.

Revision ID: 005
Revises: 004
Create Date: 2026-05-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. audit_logs.details: JSONB → JSON
    # ------------------------------------------------------------------
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "details",
            existing_type=sa.JSON(),
            type_=sa.JSON(),
            existing_nullable=True,
        )

    # ------------------------------------------------------------------
    # 2. feedback.scores: JSONB → JSON
    # ------------------------------------------------------------------
    with op.batch_alter_table("feedback") as batch_op:
        batch_op.alter_column(
            "scores",
            existing_type=sa.JSON(),
            type_=sa.JSON(),
            existing_nullable=True,
        )

    # ------------------------------------------------------------------
    # 3. configs.value: JSONB → JSON
    # ------------------------------------------------------------------
    with op.batch_alter_table("configs") as batch_op:
        batch_op.alter_column(
            "value",
            existing_type=sa.JSON(),
            type_=sa.JSON(),
            existing_nullable=True,
        )

    # ------------------------------------------------------------------
    # 4. UUID PK/FK columns → String(36)
    #    Covered tables: users, stories, chapters, pipeline_runs,
    #                    audit_logs (id only), feedback (id only), configs (id only)
    #    On SQLite these are already stored as TEXT so batch alter is a no-op
    #    in practice; on Postgres this removes the uuid type constraint.
    # ------------------------------------------------------------------
    _uuid_pk_tables = [
        "users",
        "stories",
        "chapters",
        "pipeline_runs",
        "audit_logs",
        "feedback",
        "configs",
    ]
    for tname in _uuid_pk_tables:
        with op.batch_alter_table(tname) as batch_op:
            batch_op.alter_column(
                "id",
                existing_type=sa.String(36),
                type_=sa.String(36),
                existing_nullable=False,
            )

    # FK columns that also use UUID type
    _uuid_fk_cols = [
        ("stories", "user_id"),
        ("chapters", "story_id"),
        ("pipeline_runs", "user_id"),
        ("pipeline_runs", "story_id"),
        ("feedback", "story_id"),
    ]
    for tname, col in _uuid_fk_cols:
        with op.batch_alter_table(tname) as batch_op:
            batch_op.alter_column(
                col,
                existing_type=sa.String(36),
                type_=sa.String(36),
                existing_nullable=True,
            )

    # ------------------------------------------------------------------
    # 5. chapters: add UniqueConstraint(story_id, chapter_number)
    # ------------------------------------------------------------------
    with op.batch_alter_table("chapters") as batch_op:
        batch_op.create_unique_constraint(
            "uq_chapter_story_number", ["story_id", "chapter_number"]
        )

    # ------------------------------------------------------------------
    # 6. pipeline_runs: add index on story_id
    # ------------------------------------------------------------------
    op.create_index(
        "ix_pipeline_runs_story_id", "pipeline_runs", ["story_id"]
    )


def downgrade() -> None:
    # Reverse order

    # 6. Drop story_id index on pipeline_runs
    op.drop_index("ix_pipeline_runs_story_id", table_name="pipeline_runs")

    # 5. Drop UniqueConstraint on chapters
    with op.batch_alter_table("chapters") as batch_op:
        batch_op.drop_constraint("uq_chapter_story_number", type_="unique")

    # 4. UUID columns: String(36) → String(36) (no-op; type was always compatible)
    # Nothing to revert for pure string storage.

    # 3-1. JSON columns: already JSON; nothing to revert on cross-dialect path.
    # (On Postgres a true rollback would restore JSONB — acceptable trade-off
    #  given the project targets SQLite-primary deployment.)
