"""Add L1→L2 handoff envelope columns (Sprint 1 P6).

Adds nullable JSON / String columns to pipeline_runs and chapters.
SQLite-safe: nullable, no constraints, no defaults.

Revision ID: 003
Revises: 002
Create Date: 2026-05-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pipeline_runs",
        sa.Column("handoff_envelope", sa.JSON(), nullable=True))
    op.add_column("pipeline_runs",
        sa.Column("handoff_health", sa.JSON(), nullable=True))
    op.add_column("pipeline_runs",
        sa.Column("handoff_signals_version", sa.String(16), nullable=True))

    op.add_column("chapters",
        sa.Column("negotiated_contract", sa.JSON(), nullable=True))
    op.add_column("chapters",
        sa.Column("contract_reconciliation_warnings", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chapters", "contract_reconciliation_warnings")
    op.drop_column("chapters", "negotiated_contract")
    op.drop_column("pipeline_runs", "handoff_signals_version")
    op.drop_column("pipeline_runs", "handoff_health")
    op.drop_column("pipeline_runs", "handoff_envelope")
