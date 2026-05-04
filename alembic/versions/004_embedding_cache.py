"""Sprint 2 P2 — embedding_cache table + per-chapter semantic columns.

Creates the `embedding_cache` table and adds two nullable JSON columns:
  - `chapters.semantic_findings`
  - `pipeline_runs.outline_metrics`

SQLite-safe: nullable additions only; no NOT NULL constraints on new columns.
Forward + downgrade fully reversible.

Revision ID: 004
Revises: 003
Create Date: 2026-05-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Embedding cache table
    op.create_table(
        "embedding_cache",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("model_id", sa.String(255), nullable=False),
        sa.Column("dim", sa.Integer, nullable=False),
        sa.Column("vec", sa.LargeBinary, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_embedding_cache_model_id", "embedding_cache", ["model_id"])

    # 2) Per-chapter semantic findings (extends Sprint 1 chapters table)
    op.add_column(
        "chapters",
        sa.Column("semantic_findings", sa.JSON(), nullable=True),
    )

    # 3) Per-pipeline-run outline metrics snapshot
    op.add_column(
        "pipeline_runs",
        sa.Column("outline_metrics", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pipeline_runs", "outline_metrics")
    op.drop_column("chapters", "semantic_findings")
    op.drop_index("ix_embedding_cache_model_id", table_name="embedding_cache")
    op.drop_table("embedding_cache")
