"""foundation orders

Revision ID: 20260411_01
Revises:
Create Date: 2026-04-11 20:50:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260411_01"
down_revision = None
branch_labels = None
depends_on = None


load_order_status_enum = sa.Enum(
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
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("operator_name", sa.String(length=255), nullable=False),
        sa.Column("auth_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auth_id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("vat_id", sa.String(length=50), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "truck_types",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "addresses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("full_address", sa.String(length=500), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_addresses_customer_id__customers",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "carriers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("truck_type_id", sa.Integer(), nullable=True),
        sa.Column("reliability_rating", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("documentation_valid", sa.Boolean(), nullable=False),
        sa.Column("base_price_km", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.ForeignKeyConstraint(
            ["truck_type_id"],
            ["truck_types.id"],
            name="fk_carriers_truck_type_id__truck_types",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "load_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("status", load_order_status_enum, nullable=False),
        sa.Column("origin_id", sa.Uuid(), nullable=True),
        sa.Column("origin_load_date", sa.DateTime(), nullable=True),
        sa.Column("destination_id", sa.Uuid(), nullable=True),
        sa.Column("destination_unload_date", sa.DateTime(), nullable=True),
        sa.Column("distance_km", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("cargo_description", sa.Text(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("truck_type_id", sa.Integer(), nullable=True),
        sa.Column("adr_required", sa.Boolean(), nullable=False),
        sa.Column("missing_fields", sa.JSON(), nullable=True),
        sa.Column("customer_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_load_orders_customer_id__customers",
        ),
        sa.ForeignKeyConstraint(
            ["destination_id"],
            ["addresses.id"],
            name="fk_load_orders_destination_id__addresses",
        ),
        sa.ForeignKeyConstraint(
            ["origin_id"],
            ["addresses.id"],
            name="fk_load_orders_origin_id__addresses",
        ),
        sa.ForeignKeyConstraint(
            ["truck_type_id"],
            ["truck_types.id"],
            name="fk_load_orders_truck_type_id__truck_types",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_load_orders_user_id__users",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "trips",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("load_order_id", sa.Uuid(), nullable=False),
        sa.Column("carrier_id", sa.Uuid(), nullable=False),
        sa.Column("carrier_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("profit_margin", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("proposal_status", sa.String(length=50), nullable=False),
        sa.Column("ai_rejection_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["load_order_id"],
            ["load_orders.id"],
            name="fk_trips_load_order_id__load_orders",
        ),
        sa.ForeignKeyConstraint(
            ["carrier_id"],
            ["carriers.id"],
            name="fk_trips_carrier_id__carriers",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("trips")
    op.drop_table("load_orders")
    op.drop_table("carriers")
    op.drop_table("addresses")
    op.drop_table("truck_types")
    op.drop_table("customers")
    op.drop_table("users")
