"""phase 8B execution monitoring snapshots

Revision ID: 20260517_01
Revises: 20260508_02
Create Date: 2026-05-17 20:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260517_01"
down_revision = "20260508_02"
branch_labels = None
depends_on = None


execution_monitoring_status_enum = sa.Enum(
    "planned",
    "in_transit",
    "delayed",
    "delivered",
    name="executionmonitoringstatus",
    create_constraint=True,
    native_enum=False,
    length=50,
)


def upgrade() -> None:
    execution_monitoring_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "execution_monitoring_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "load_order_id",
            sa.Uuid(),
            sa.ForeignKey(
                "load_orders.id",
                name="fk_execution_monitoring_snapshots_load_order_id__load_orders",
            ),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", execution_monitoring_status_enum, nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_checkpoint", sa.String(length=255), nullable=True),
        sa.Column("route_points", sa.JSON(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("alerts", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "last_refreshed_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("execution_monitoring_snapshots")
    execution_monitoring_status_enum.drop(op.get_bind(), checkfirst=True)
