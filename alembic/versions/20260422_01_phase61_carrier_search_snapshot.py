"""phase 6.1 carrier search snapshot

Revision ID: 20260422_01
Revises: 20260419_01
Create Date: 2026-04-22 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260422_01"
down_revision = "20260419_01"
branch_labels = None
depends_on = None


TRIP_PROPOSAL_STATUS_BACKFILL_SQL = """
UPDATE trips
SET proposal_status = 'candidate'
WHERE proposal_status = 'Evaluando'
"""


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        "carriers",
        sa.Column(
            "adr_capable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(sa.text(TRIP_PROPOSAL_STATUS_BACKFILL_SQL))
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("carriers", recreate="always") as batch_op:
            batch_op.alter_column(
                "adr_capable",
                existing_type=sa.Boolean(),
                server_default=None,
            )
        return

    op.alter_column(
        "carriers",
        "adr_capable",
        existing_type=sa.Boolean(),
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("carriers", "adr_capable")
