"""phase 8A carrier intelligence extension

Revision ID: 20260508_02
Revises: 20260508_01
Create Date: 2026-05-08 11:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260508_02"
down_revision = "20260508_01"
branch_labels = None
depends_on = None

carrier_pricing_model_enum = sa.Enum(
    "per_km",
    "flat_rate",
    "market_adjusted",
    name="carrierpricingmodel",
    create_constraint=True,
    native_enum=False,
    length=50,
)

_CARRIER_COLUMNS: list[sa.Column[object]] = [
    sa.Column("home_base_text", sa.Text(), nullable=True),
    sa.Column("service_countries", sa.JSON(), nullable=True),
    sa.Column("preferred_lanes", sa.JSON(), nullable=True),
    sa.Column("pricing_model", carrier_pricing_model_enum, nullable=False, server_default="per_km"),
    sa.Column("flat_rate_amount", sa.Numeric(12, 2), nullable=True),
    sa.Column("fuel_surcharge_pct", sa.Numeric(5, 2), nullable=True),
]

_TRIP_COLUMNS: list[sa.Column[object]] = [
    sa.Column("ranking_score", sa.Numeric(5, 2), nullable=True),
    sa.Column("score_breakdown", sa.JSON(), nullable=True),
    sa.Column("agent_reasoning", sa.Text(), nullable=True),
]


def upgrade() -> None:
    carrier_pricing_model_enum.create(op.get_bind(), checkfirst=True)

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("carriers", recreate="always") as batch_op:
            for column in _CARRIER_COLUMNS:
                batch_op.add_column(column)
        with op.batch_alter_table("trips", recreate="always") as batch_op:
            for column in _TRIP_COLUMNS:
                batch_op.add_column(column)
        return

    for column in _CARRIER_COLUMNS:
        op.add_column("carriers", column)
    for column in _TRIP_COLUMNS:
        op.add_column("trips", column)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("trips", recreate="always") as batch_op:
            batch_op.drop_column("agent_reasoning")
            batch_op.drop_column("score_breakdown")
            batch_op.drop_column("ranking_score")
        with op.batch_alter_table("carriers", recreate="always") as batch_op:
            batch_op.drop_column("fuel_surcharge_pct")
            batch_op.drop_column("flat_rate_amount")
            batch_op.drop_column("pricing_model")
            batch_op.drop_column("preferred_lanes")
            batch_op.drop_column("service_countries")
            batch_op.drop_column("home_base_text")
        return

    op.drop_column("trips", "agent_reasoning")
    op.drop_column("trips", "score_breakdown")
    op.drop_column("trips", "ranking_score")
    op.drop_column("carriers", "fuel_surcharge_pct")
    op.drop_column("carriers", "flat_rate_amount")
    op.drop_column("carriers", "pricing_model")
    op.drop_column("carriers", "preferred_lanes")
    op.drop_column("carriers", "service_countries")
    op.drop_column("carriers", "home_base_text")
    carrier_pricing_model_enum.drop(op.get_bind(), checkfirst=True)
