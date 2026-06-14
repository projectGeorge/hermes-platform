"""phase 6.2 carrier selection

Revision ID: 20260426_01
Revises: 20260422_01
Create Date: 2026-04-26 11:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260426_01"
down_revision = "20260422_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("load_orders", recreate="always") as batch_op:
            batch_op.add_column(sa.Column("selected_trip_id", sa.Uuid(), nullable=True))
            batch_op.create_foreign_key(
                "fk_load_orders_selected_trip_id__trips",
                "trips",
                ["selected_trip_id"],
                ["id"],
            )
        return

    op.add_column("load_orders", sa.Column("selected_trip_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_load_orders_selected_trip_id__trips",
        "load_orders",
        "trips",
        ["selected_trip_id"],
        ["id"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("load_orders", recreate="always") as batch_op:
            batch_op.drop_constraint(
                "fk_load_orders_selected_trip_id__trips",
                type_="foreignkey",
            )
            batch_op.drop_column("selected_trip_id")
        return

    op.drop_constraint(
        "fk_load_orders_selected_trip_id__trips",
        "load_orders",
        type_="foreignkey",
    )
    op.drop_column("load_orders", "selected_trip_id")
