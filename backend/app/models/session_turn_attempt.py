"""Immutable pre-dispatch provider attempt facts for Session turns."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SessionTurnAttempt(Base):
    """Request-start fact committed before any external provider call."""

    __tablename__ = "session_turn_attempts"
    __table_args__ = (
        UniqueConstraint("turn_id", "attempt_number", name="uq_session_turn_attempt_number"),
        CheckConstraint("attempt_number > 0", name="ck_session_turn_attempt_number_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("session_turns.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_token: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_operation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    turn = relationship("SessionTurn", back_populates="attempts", foreign_keys=[turn_id])
    events = relationship("SessionTurnAttemptEvent", back_populates="attempt")


def _reject_attempt_mutation(_mapper: object, _connection: object, _target: object) -> None:
    raise ValueError("SessionTurnAttempt rows are immutable")


event.listen(SessionTurnAttempt, "before_update", _reject_attempt_mutation)
event.listen(SessionTurnAttempt, "before_delete", _reject_attempt_mutation)
