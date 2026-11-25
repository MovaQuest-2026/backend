"""Database model for administrative audit events."""

from typing import Any

from sqlalchemy import JSON, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class AdminAuditLog(Base, TimestampMixin):
    """An immutable record of a successful mutation performed in the admin panel."""

    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, init=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    entity: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(128), default=None, nullable=True)
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, default_factory=dict, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), default=None, nullable=True)

    __table_args__ = (
        Index("ix_admin_audit_logs_created", "created_at", "id"),
        Index("ix_admin_audit_logs_entity", "entity", "entity_id"),
        Index("ix_admin_audit_logs_actor", "actor", "created_at"),
    )
