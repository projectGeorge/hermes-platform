"""phase 8A agent runtime foundation

Revision ID: 20260508_01
Revises: 20260502_01
Create Date: 2026-05-08 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260508_01"
down_revision = "20260502_01"
branch_labels = None
depends_on = None

agent_kind_enum = sa.Enum(
    "orchestrator",
    "ingestion",
    "carrier_search",
    "smart_comms",
    "monitoring",
    name="agentkind",
    create_constraint=True,
    native_enum=False,
    length=50,
)

agent_activity_state_enum = sa.Enum(
    "running",
    "completed",
    "awaiting_operator",
    "warning",
    "error",
    name="agentactivitystate",
    create_constraint=True,
    native_enum=False,
    length=50,
)

monitoring_alert_severity_enum = sa.Enum(
    "info",
    "warning",
    "critical",
    name="monitoringalertseverity",
    create_constraint=True,
    native_enum=False,
    length=50,
)

monitoring_alert_type_enum = sa.Enum(
    "status_changed",
    "deadline_approaching",
    "missing_route_data",
    "stalled_workflow",
    "margin_risk",
    name="monitoringalerttype",
    create_constraint=True,
    native_enum=False,
    length=50,
)

monitoring_alert_status_enum = sa.Enum(
    "open",
    "resolved",
    name="monitoringalertstatus",
    create_constraint=True,
    native_enum=False,
    length=50,
)

smart_comms_context_type_enum = sa.Enum(
    "dashboard",
    "orders_list",
    "load_order",
    "carrier_match",
    "intake_review",
    name="smartcommscontexttype",
    create_constraint=True,
    native_enum=False,
    length=50,
)

smart_comms_message_role_enum = sa.Enum(
    "user",
    "assistant",
    "system",
    name="smartcommsmessagerole",
    create_constraint=True,
    native_enum=False,
    length=50,
)


def upgrade() -> None:
    agent_kind_enum.create(op.get_bind(), checkfirst=True)
    agent_activity_state_enum.create(op.get_bind(), checkfirst=True)
    monitoring_alert_severity_enum.create(op.get_bind(), checkfirst=True)
    monitoring_alert_type_enum.create(op.get_bind(), checkfirst=True)
    monitoring_alert_status_enum.create(op.get_bind(), checkfirst=True)
    smart_comms_context_type_enum.create(op.get_bind(), checkfirst=True)
    smart_comms_message_role_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "agent_activities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_kind", agent_kind_enum, nullable=False),
        sa.Column("activity_state", agent_activity_state_enum, nullable=False),
        sa.Column(
            "load_order_id",
            sa.Uuid(),
            sa.ForeignKey("load_orders.id", name="fk_agent_activities_load_order_id__load_orders"),
            nullable=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("activity_key", sa.String(100), nullable=False),
        sa.Column("next_action", sa.String(255), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )

    op.create_table(
        "smart_comms_conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey(
                "users.id",
                name="fk_smart_comms_conversations_user_id__users",
            ),
            nullable=False,
        ),
        sa.Column("context_type", smart_comms_context_type_enum, nullable=False),
        sa.Column("context_id", sa.Uuid(), nullable=True),
        sa.Column("route_path", sa.String(500), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )

    op.create_table(
        "smart_comms_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey(
                "smart_comms_conversations.id",
                name="fk_smart_comms_msg_conv_id",
            ),
            nullable=False,
        ),
        sa.Column("role", smart_comms_message_role_enum, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )

    op.create_table(
        "monitoring_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "load_order_id",
            sa.Uuid(),
            sa.ForeignKey(
                "load_orders.id",
                name="fk_monitoring_alerts_load_order_id__load_orders",
            ),
            nullable=True,
        ),
        sa.Column("alert_type", monitoring_alert_type_enum, nullable=False),
        sa.Column("severity", monitoring_alert_severity_enum, nullable=False),
        sa.Column("status", monitoring_alert_status_enum, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.String(255), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("monitoring_alerts")
    op.drop_table("smart_comms_messages")
    op.drop_table("smart_comms_conversations")
    op.drop_table("agent_activities")

    smart_comms_message_role_enum.drop(op.get_bind(), checkfirst=True)
    smart_comms_context_type_enum.drop(op.get_bind(), checkfirst=True)
    monitoring_alert_status_enum.drop(op.get_bind(), checkfirst=True)
    monitoring_alert_type_enum.drop(op.get_bind(), checkfirst=True)
    monitoring_alert_severity_enum.drop(op.get_bind(), checkfirst=True)
    agent_activity_state_enum.drop(op.get_bind(), checkfirst=True)
    agent_kind_enum.drop(op.get_bind(), checkfirst=True)
