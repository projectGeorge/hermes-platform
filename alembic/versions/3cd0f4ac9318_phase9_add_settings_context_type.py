"""phase9_add_settings_context_type

Revision ID: 3cd0f4ac9318
Revises: ab14c5059df5
Create Date: 2026-06-07 12:40:02.308508

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '3cd0f4ac9318'
down_revision = 'ab14c5059df5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            DO $$
            DECLARE
                constraint_name text;
            BEGIN
                SELECT con.conname INTO constraint_name
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                WHERE rel.relname = 'smart_comms_conversations'
                  AND con.contype = 'c'
                  AND pg_get_constraintdef(con.oid) LIKE '%context_type%';

                IF constraint_name IS NOT NULL THEN
                    EXECUTE 'ALTER TABLE smart_comms_conversations DROP CONSTRAINT ' || constraint_name;
                END IF;
            END $$
        """)
        op.execute("""
            ALTER TABLE smart_comms_conversations
            ADD CONSTRAINT smart_comms_conversations_context_type_check
            CHECK (context_type IN ('dashboard', 'orders_list', 'load_order', 'carrier_match', 'intake_review', 'settings'))
        """)
    else:
        # SQLite: use batch alter to recreate the constraint
        with op.batch_alter_table("smart_comms_conversations") as batch_op:
            batch_op.alter_column(
                "context_type",
                type_=sa.String(50),
                nullable=False,
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE smart_comms_conversations DROP CONSTRAINT IF EXISTS smart_comms_conversations_context_type_check")
        op.execute("""
            ALTER TABLE smart_comms_conversations
            ADD CONSTRAINT smart_comms_conversations_context_type_check
            CHECK (context_type IN ('dashboard', 'orders_list', 'load_order', 'carrier_match', 'intake_review'))
        """)
    else:
        with op.batch_alter_table("smart_comms_conversations") as batch_op:
            batch_op.alter_column(
                "context_type",
                type_=sa.String(50),
                nullable=False,
            )
