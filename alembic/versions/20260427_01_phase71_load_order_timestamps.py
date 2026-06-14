"""phase 7.1 load order timestamps

Revision ID: 20260427_01
Revises: 20260426_01
Create Date: 2026-04-27 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260427_01"
down_revision = "20260426_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    created_at_column = sa.Column(
        "created_at",
        sa.DateTime(),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    updated_at_column = sa.Column(
        "updated_at",
        sa.DateTime(),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("load_orders", recreate="always") as batch_op:
            batch_op.add_column(created_at_column)
            batch_op.add_column(updated_at_column)
        return

    op.add_column("load_orders", created_at_column)
    op.add_column("load_orders", updated_at_column)


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("load_orders", recreate="always") as batch_op:
            batch_op.drop_column("updated_at")
            batch_op.drop_column("created_at")
        return

    op.drop_column("load_orders", "updated_at")
    op.drop_column("load_orders", "created_at")
