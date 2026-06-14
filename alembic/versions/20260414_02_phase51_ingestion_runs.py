"""phase 5.1 ingestion runs

Revision ID: 20260414_02
Revises: 20260411_01
Create Date: 2026-04-14 22:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260414_02"
down_revision = "20260411_01"
branch_labels = None
depends_on = None


ingestion_run_status_enum = sa.Enum(
    "processing",
    "completed",
    "failed",
    name="ingestionrunstatus",
    native_enum=False,
    create_constraint=True,
    length=50,
)


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("route", sa.String(length=255), nullable=False),
        sa.Column("status", ingestion_run_status_enum, nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("extracted_payload", sa.JSON(), nullable=True),
        sa.Column("missing_fields", sa.JSON(), nullable=True),
        sa.Column("load_order_id", sa.Uuid(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["load_order_id"],
            ["load_orders.id"],
            name="fk_ingestion_runs_load_order_id__load_orders",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ingestion_runs_user_id__users",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ingestion_runs")
