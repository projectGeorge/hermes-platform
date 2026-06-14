"""load order formalized status

Revision ID: 20260530_01
Revises: 20260517_01
Create Date: 2026-05-30 17:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260530_01"
down_revision = "20260517_01"
branch_labels = None
depends_on = None


UPDATED_LOAD_ORDER_STATUS_ENUM = sa.Enum(
    "pending_ingestion",
    "viability_pending",
    "viability_confirmed",
    "searching_carrier",
    "ready_for_formalization",
    "formalized",
    "cancelled",
    name="loadorderstatus",
    native_enum=False,
    length=50,
)

PREVIOUS_LOAD_ORDER_STATUS_ENUM = sa.Enum(
    "pending_ingestion",
    "viability_pending",
    "viability_confirmed",
    "searching_carrier",
    "ready_for_formalization",
    "cancelled",
    name="loadorderstatus",
    native_enum=False,
    length=50,
)


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("load_orders", recreate="always") as batch_op:
            batch_op.alter_column(
                "status",
                existing_type=PREVIOUS_LOAD_ORDER_STATUS_ENUM,
                type_=UPDATED_LOAD_ORDER_STATUS_ENUM,
                existing_nullable=False,
            )
        return

    op.alter_column(
        "load_orders",
        "status",
        existing_type=PREVIOUS_LOAD_ORDER_STATUS_ENUM,
        type_=UPDATED_LOAD_ORDER_STATUS_ENUM,
        existing_nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("load_orders", recreate="always") as batch_op:
            batch_op.alter_column(
                "status",
                existing_type=UPDATED_LOAD_ORDER_STATUS_ENUM,
                type_=PREVIOUS_LOAD_ORDER_STATUS_ENUM,
                existing_nullable=False,
            )
        return

    op.alter_column(
        "load_orders",
        "status",
        existing_type=UPDATED_LOAD_ORDER_STATUS_ENUM,
        type_=PREVIOUS_LOAD_ORDER_STATUS_ENUM,
        existing_nullable=False,
    )
