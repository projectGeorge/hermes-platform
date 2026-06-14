import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.core.domain_enums import IngestionRunStatus
from app.backend.db.base import Base


class IngestionRun(Base):
    """Persisted runtime state for an ingestion execution."""

    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", name="fk_ingestion_runs_user_id__users"),
        nullable=False,
    )
    route: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[IngestionRunStatus] = mapped_column(
        Enum(
            IngestionRunStatus,
            native_enum=False,
            create_constraint=True,
            length=50,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=IngestionRunStatus.PROCESSING,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    missing_fields: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    load_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("load_orders.id", name="fk_ingestion_runs_load_order_id__load_orders"),
        nullable=True,
    )
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    execution_path: Mapped[str | None] = mapped_column(String(50), nullable=True)
    trace_steps: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    raw_model_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    normalization_warnings: Mapped[list[object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(),
        default=datetime.now,
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        default=datetime.now,
        onupdate=datetime.now,
        server_default=func.current_timestamp(),
        nullable=False,
    )
