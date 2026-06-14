"""phase 5.2 human reviews

Revision ID: 20260418_01
Revises: 20260414_02
Create Date: 2026-04-18 18:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260418_01"
down_revision = "20260414_02"
branch_labels = None
depends_on = None


load_order_human_review_status_enum = sa.Enum(
    "fields_updated",
    "viability_confirmed",
    name="loadorderhumanreviewstatus",
    native_enum=False,
    create_constraint=True,
    length=50,
)


def upgrade() -> None:
    op.create_table(
        "load_order_human_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("load_order_id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("review_status", load_order_human_review_status_enum, nullable=False),
        sa.Column("submitted_fields", sa.JSON(), nullable=False),
        sa.Column("remaining_missing_fields", sa.JSON(), nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["load_order_id"],
            ["load_orders.id"],
            name="fk_load_order_human_reviews_load_order_id__load_orders",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name="fk_load_order_human_reviews_ingestion_run_id__ingestion_runs",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name="fk_load_order_human_reviews_reviewed_by_user_id__users",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("load_order_human_reviews")
