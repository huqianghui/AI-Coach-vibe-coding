"""Append-only post-dispatch events for immutable Session turn attempts."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SessionTurnAttemptEvent(Base):
    """One immutable provider outcome, reconciliation, winner, or cleanup observation."""

    __tablename__ = "session_turn_attempt_events"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id", "event_sequence", name="uq_session_turn_attempt_event_sequence"
        ),
        CheckConstraint(
            "event_kind IN ('dispatched', 'known_success', 'known_failure', 'timeout', "
            "'unknown', 'reconciled_success', 'reconciled_failure', 'winner_selected', "
            "'late_duplicate', 'cleanup_observed')",
            name="ck_session_turn_attempt_event_kind",
        ),
        CheckConstraint(
            "event_sequence > 0", name="ck_session_turn_attempt_event_sequence_positive"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("session_turn_attempts.id", ondelete="RESTRICT"), nullable=False
    )
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_response_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    terminal_classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sanitized_error_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    observed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    attempt = relationship("SessionTurnAttempt", back_populates="events")


def _reject_attempt_event_mutation(_mapper: object, _connection: object, _target: object) -> None:
    raise ValueError("SessionTurnAttemptEvent rows are immutable")


event.listen(SessionTurnAttemptEvent, "before_update", _reject_attempt_event_mutation)
event.listen(SessionTurnAttemptEvent, "before_delete", _reject_attempt_event_mutation)
