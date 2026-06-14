"""Persisted shipment execution monitoring read model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.core.domain_enums import ExecutionMonitoringStatus
from app.backend.db.base import Base


class ExecutionMonitoringSnapshot(Base):
    """Cheap read model for shipment execution monitoring surfaces."""

    __tablename__ = "execution_monitoring_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    load_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("load_orders.id", name="fk_execution_monitoring_snapshots_load_order_id__load_orders"),
        nullable=False,
        unique=True,
    )
    status: Mapped[ExecutionMonitoringStatus] = mapped_column(
        Enum(
            ExecutionMonitoringStatus,
            native_enum=False,
            create_constraint=True,
            length=50,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    progress_percent: Mapped[int] = mapped_column(nullable=False, default=0)
    current_checkpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    route_points: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    events: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    alerts: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    extra_metadata: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    last_refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.current_timestamp(),
        nullable=False,
    )
