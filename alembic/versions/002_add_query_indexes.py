"""Add indexes for common query filters.

Covers stories.status, stories.genre, pipeline_runs.status — columns
frequently used in WHERE clauses but missing indexes in initial schema.

Revision ID: 002
Revises: 001
Create Date: 2026-04-03
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_stories_status", "stories", ["status"])
    op.create_index("ix_stories_genre", "stories", ["genre"])
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_status", table_name="pipeline_runs")
    op.drop_index("ix_stories_genre", table_name="stories")
    op.drop_index("ix_stories_status", table_name="stories")
