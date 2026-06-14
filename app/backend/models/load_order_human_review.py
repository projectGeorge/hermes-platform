"""Audit model for Human-in-the-Loop load-order reviews."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.core.domain_enums import LoadOrderHumanReviewStatus
from app.backend.db.base import Base


class LoadOrderHumanReview(Base):
    """Persist a human review event linked to an ingested load order."""

    __tablename__ = "load_order_human_reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    load_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("load_orders.id", name="fk_load_order_human_reviews_load_order_id__load_orders"),
        nullable=False,
    )
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "ingestion_runs.id",
            name="fk_load_order_human_reviews_ingestion_run_id__ingestion_runs",
        ),
        nullable=False,
    )
    reviewed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", name="fk_load_order_human_reviews_reviewed_by_user_id__users"),
        nullable=False,
    )
    review_status: Mapped[LoadOrderHumanReviewStatus] = mapped_column(
        Enum(
            LoadOrderHumanReviewStatus,
            native_enum=False,
            create_constraint=True,
            length=50,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    submitted_fields: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    remaining_missing_fields: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(),
        default=datetime.now,
        server_default=func.current_timestamp(),
        nullable=False,
    )
