import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.backend.db.base import Base

if TYPE_CHECKING:
    from app.backend.models.load_order import LoadOrder


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    operator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now, nullable=False)

    load_orders: Mapped[list["LoadOrder"]] = relationship(
        back_populates="user",
        lazy="selectin",
    )
