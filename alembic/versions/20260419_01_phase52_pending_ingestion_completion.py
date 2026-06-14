"""phase 5.2 pending ingestion completion

Revision ID: 20260419_01
Revises: 20260418_01
Create Date: 2026-04-19 11:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260419_01"
down_revision = "20260418_01"
branch_labels = None
depends_on = None


POSTGRESQL_BACKFILL_SQL = """
UPDATE load_orders
SET
    customer_name = COALESCE(
        load_orders.customer_name,
        ingestion_runs.extracted_payload ->> 'customer_name'
    ),
    origin_text = COALESCE(
        load_orders.origin_text,
        ingestion_runs.extracted_payload ->> 'origin_text'
    ),
    destination_text = COALESCE(
        load_orders.destination_text,
        ingestion_runs.extracted_payload ->> 'destination_text'
    )
FROM ingestion_runs
WHERE ingestion_runs.load_order_id = load_orders.id
"""


SQLITE_BACKFILL_SQL = """
UPDATE load_orders
SET
    customer_name = COALESCE(
        customer_name,
        json_extract(ingestion_runs.extracted_payload, '$.customer_name')
    ),
    origin_text = COALESCE(
        origin_text,
        json_extract(ingestion_runs.extracted_payload, '$.origin_text')
    ),
    destination_text = COALESCE(
        destination_text,
        json_extract(ingestion_runs.extracted_payload, '$.destination_text')
    )
FROM ingestion_runs
WHERE ingestion_runs.load_order_id = load_orders.id
"""


def upgrade() -> None:
    op.add_column("load_orders", sa.Column("customer_name", sa.String(length=255), nullable=True))
    op.add_column("load_orders", sa.Column("origin_text", sa.Text(), nullable=True))
    op.add_column("load_orders", sa.Column("destination_text", sa.Text(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(POSTGRESQL_BACKFILL_SQL))
        return

    op.execute(sa.text(SQLITE_BACKFILL_SQL))


def downgrade() -> None:
    op.drop_column("load_orders", "destination_text")
    op.drop_column("load_orders", "origin_text")
    op.drop_column("load_orders", "customer_name")
