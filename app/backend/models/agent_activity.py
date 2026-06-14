"""Append-only agent activity log for dashboard visibility."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.core.domain_enums import AgentActivityState, AgentKind
from app.backend.db.base import Base


class AgentActivity(Base):
    """One row per visible agent event. Immutable append-only log."""

    __tablename__ = "agent_activities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_kind: Mapped[AgentKind] = mapped_column(
        Enum(
            AgentKind,
            native_enum=False,
            create_constraint=True,
            length=50,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    activity_state: Mapped[AgentActivityState] = mapped_column(
        Enum(
            AgentActivityState,
            native_enum=False,
            create_constraint=True,
            length=50,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    load_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("load_orders.id", name="fk_agent_activities_load_order_id__load_orders"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    activity_key: Mapped[str] = mapped_column(String(100), nullable=False)
    next_action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extra_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.current_timestamp(),
        nullable=False,
    )
