"""phase 7.2C ingestion trace runtime

Revision ID: 20260502_01
Revises: 20260427_01
Create Date: 2026-05-02 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260502_01"
down_revision = "20260427_01"
branch_labels = None
depends_on = None

_TRACE_COLUMNS: list[sa.Column[object]] = [
    sa.Column("provider", sa.String(50), nullable=True),
    sa.Column("model_name", sa.String(255), nullable=True),
    sa.Column("execution_path", sa.String(50), nullable=True),
    sa.Column("trace_steps", sa.JSON, nullable=True),
    sa.Column("raw_model_response", sa.Text, nullable=True),
    sa.Column("confidence_summary", sa.JSON, nullable=True),
    sa.Column("normalization_warnings", sa.JSON, nullable=True),
]


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("ingestion_runs", recreate="always") as batch_op:
            for column in _TRACE_COLUMNS:
                batch_op.add_column(column)
        return

    for column in _TRACE_COLUMNS:
        op.add_column("ingestion_runs", column)


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("ingestion_runs", recreate="always") as batch_op:
            batch_op.drop_column("normalization_warnings")
            batch_op.drop_column("confidence_summary")
            batch_op.drop_column("raw_model_response")
            batch_op.drop_column("trace_steps")
            batch_op.drop_column("execution_path")
            batch_op.drop_column("model_name")
            batch_op.drop_column("provider")
        return

    op.drop_column("ingestion_runs", "normalization_warnings")
    op.drop_column("ingestion_runs", "confidence_summary")
    op.drop_column("ingestion_runs", "raw_model_response")
    op.drop_column("ingestion_runs", "trace_steps")
    op.drop_column("ingestion_runs", "execution_path")
    op.drop_column("ingestion_runs", "model_name")
    op.drop_column("ingestion_runs", "provider")
