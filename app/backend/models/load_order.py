import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.backend.core.domain_enums import LoadOrderStatus
from app.backend.db.base import Base

if TYPE_CHECKING:
    from app.backend.models.address import Address
    from app.backend.models.customer import Customer
    from app.backend.models.trip import Trip
    from app.backend.models.truck_type import TruckType
    from app.backend.models.user import User


class LoadOrder(Base):
    __tablename__ = "load_orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id"),
        nullable=True,
    )
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[LoadOrderStatus] = mapped_column(
        Enum(
            LoadOrderStatus,
            native_enum=False,
            length=50,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=LoadOrderStatus.PENDING_INGESTION,
    )
    selected_trip_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trips.id"),
        nullable=True,
    )

    origin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("addresses.id"), nullable=True)
    origin_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin_load_date: Mapped[datetime | None] = mapped_column(nullable=True)
    destination_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("addresses.id"),
        nullable=True,
    )
    destination_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination_unload_date: Mapped[datetime | None] = mapped_column(nullable=True)
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    cargo_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    truck_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("truck_types.id"),
        nullable=True,
    )
    adr_required: Mapped[bool] = mapped_column(default=False, nullable=False)
    missing_fields: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    customer_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="load_orders", lazy="selectin")
    customer: Mapped["Customer | None"] = relationship(
        back_populates="load_orders",
        lazy="selectin",
    )
    truck_type: Mapped["TruckType | None"] = relationship(
        back_populates="load_orders",
        lazy="selectin",
    )
    origin: Mapped["Address | None"] = relationship(
        back_populates="origin_load_orders",
        foreign_keys=[origin_id],
        lazy="selectin",
    )
    destination: Mapped["Address | None"] = relationship(
        back_populates="destination_load_orders",
        foreign_keys=[destination_id],
        lazy="selectin",
    )
    trips: Mapped[list["Trip"]] = relationship(
        back_populates="load_order",
        foreign_keys="Trip.load_order_id",
        lazy="selectin",
    )
    selected_trip: Mapped["Trip | None"] = relationship(
        foreign_keys=[selected_trip_id],
        lazy="selectin",
        post_update=True,
    )
