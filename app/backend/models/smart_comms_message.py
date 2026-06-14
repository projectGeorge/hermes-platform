"""Smart Comms message within a conversation."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.backend.core.domain_enums import SmartCommsMessageRole
from app.backend.db.base import Base


class SmartCommsMessage(Base):
    """A single message in a Smart Comms conversation."""

    __tablename__ = "smart_comms_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "smart_comms_conversations.id",
            name="fk_smart_comms_msg_conv_id",
        ),
        nullable=False,
    )
    role: Mapped[SmartCommsMessageRole] = mapped_column(
        Enum(
            SmartCommsMessageRole,
            native_enum=False,
            create_constraint=True,
            length=50,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extra_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(),
        default=datetime.now,
        server_default=func.current_timestamp(),
        nullable=False,
    )

    conversation: Mapped["SmartCommsConversation"] = relationship(  # noqa: F821
        back_populates="messages",
        lazy="selectin",
    )
