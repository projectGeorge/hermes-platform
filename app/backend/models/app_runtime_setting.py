from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.db.base import Base


class AppRuntimeSetting(Base):
    __tablename__ = "app_runtime_settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(),
        default=datetime.now,
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        default=datetime.now,
        onupdate=datetime.now,
        server_default=func.current_timestamp(),
        nullable=False,
    )
