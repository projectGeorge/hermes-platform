from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.backend.db.base import Base

if TYPE_CHECKING:
    from app.backend.models.carrier import Carrier
    from app.backend.models.load_order import LoadOrder


class TruckType(Base):
    __tablename__ = "truck_types"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    carriers: Mapped[list["Carrier"]] = relationship(
        back_populates="truck_type",
        lazy="selectin",
    )
    load_orders: Mapped[list["LoadOrder"]] = relationship(
        back_populates="truck_type",
        lazy="selectin",
    )
