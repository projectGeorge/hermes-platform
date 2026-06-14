import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.backend.core.domain_enums import CarrierPricingModel
from app.backend.db.base import Base

if TYPE_CHECKING:
    from app.backend.models.trip import Trip
    from app.backend.models.truck_type import TruckType


class Carrier(Base):
    __tablename__ = "carriers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    truck_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("truck_types.id"),
        nullable=True,
    )
    reliability_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    documentation_valid: Mapped[bool] = mapped_column(default=True, nullable=False)
    adr_capable: Mapped[bool] = mapped_column(default=False, nullable=False)
    base_price_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    home_base_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_countries: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    preferred_lanes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    pricing_model: Mapped[CarrierPricingModel] = mapped_column(
        Enum(
            CarrierPricingModel,
            native_enum=False,
            create_constraint=True,
            length=50,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=CarrierPricingModel.PER_KM,
    )
    flat_rate_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    fuel_surcharge_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    truck_type: Mapped["TruckType | None"] = relationship(
        back_populates="carriers",
        lazy="selectin",
    )
    trips: Mapped[list["Trip"]] = relationship(
        back_populates="carrier",
        lazy="selectin",
    )
