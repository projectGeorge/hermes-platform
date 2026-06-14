import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.backend.db.base import Base

if TYPE_CHECKING:
    from app.backend.models.address import Address
    from app.backend.models.load_order import LoadOrder


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    load_orders: Mapped[list["LoadOrder"]] = relationship(
        back_populates="customer",
        lazy="selectin",
    )
    addresses: Mapped[list["Address"]] = relationship(
        back_populates="customer",
        lazy="selectin",
    )
