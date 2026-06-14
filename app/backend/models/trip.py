import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.backend.core.domain_enums import TripProposalStatus
from app.backend.db.base import Base

if TYPE_CHECKING:
    from app.backend.models.carrier import Carrier
    from app.backend.models.load_order import LoadOrder


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    load_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("load_orders.id"),
        nullable=False,
    )
    carrier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("carriers.id"),
        nullable=False,
    )
    carrier_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    profit_margin: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    proposal_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=TripProposalStatus.CANDIDATE.value,
    )
    ai_rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ranking_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    score_breakdown: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    agent_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    load_order: Mapped["LoadOrder"] = relationship(
        back_populates="trips",
        foreign_keys=[load_order_id],
        lazy="selectin",
    )
    carrier: Mapped["Carrier"] = relationship(
        back_populates="trips",
        lazy="selectin",
    )
