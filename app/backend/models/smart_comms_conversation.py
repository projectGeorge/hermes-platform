"""Smart Comms conversation scoped to a user and page context."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.backend.core.domain_enums import SmartCommsContextType
from app.backend.db.base import Base


class SmartCommsConversation(Base):
    """One active conversation per (user_id, context_type, context_id)."""

    __tablename__ = "smart_comms_conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", name="fk_smart_comms_conversations_user_id__users"),
        nullable=False,
    )
    context_type: Mapped[SmartCommsContextType] = mapped_column(
        Enum(
            SmartCommsContextType,
            native_enum=False,
            create_constraint=True,
            length=50,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    context_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    route_path: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    messages: Mapped[list["SmartCommsMessage"]] = relationship(  # noqa: F821
        back_populates="conversation",
        lazy="selectin",
        order_by="SmartCommsMessage.created_at",
    )
