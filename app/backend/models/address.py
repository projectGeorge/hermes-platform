import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.backend.db.base import Base

if TYPE_CHECKING:
    from app.backend.models.customer import Customer
    from app.backend.models.load_order import LoadOrder


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id"),
        nullable=True,
    )
    full_address: Mapped[str] = mapped_column(String(500), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)

    customer: Mapped["Customer | None"] = relationship(
        back_populates="addresses",
        lazy="selectin",
    )
    origin_load_orders: Mapped[list["LoadOrder"]] = relationship(
        back_populates="origin",
        foreign_keys="[LoadOrder.origin_id]",
        lazy="selectin",
    )
    destination_load_orders: Mapped[list["LoadOrder"]] = relationship(
        back_populates="destination",
        foreign_keys="[LoadOrder.destination_id]",
        lazy="selectin",
    )
