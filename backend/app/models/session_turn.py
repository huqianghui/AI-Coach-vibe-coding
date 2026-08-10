"""Mutable durable outbox aggregate for one server-owned Session turn."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

SESSION_TURN_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"leased", "failed_terminal", "cancelled"}),
    "leased": frozenset({"pending", "provider_pending", "failed_terminal", "cancelled"}),
    "provider_pending": frozenset({"provider_unknown", "succeeded", "failed_terminal"}),
    "provider_unknown": frozenset({"reconciling", "failed_terminal"}),
    "reconciling": frozenset({"provider_unknown", "succeeded", "failed_terminal"}),
    "succeeded": frozenset(),
    "failed_terminal": frozenset(),
    "cancelled": frozenset(),
}


class SessionTurn(Base, TimestampMixin):
    """Mutable orchestration state with at most one committed application result.

    Provider execution may duplicate after unknown outcomes; attempts and events retain
    those facts while winner selection prevents a duplicate application-state commit.
    """

    __tablename__ = "session_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "turn_key", name="uq_session_turn_key"),
        CheckConstraint(
            "status IN ('pending', 'leased', 'provider_pending', 'provider_unknown', "
            "'reconciling', 'succeeded', 'failed_terminal', 'cancelled')",
            name="ck_session_turn_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_session_turn_attempt_count_nonnegative"),
        CheckConstraint("frozen_step >= 0", name="ck_session_turn_frozen_step_nonnegative"),
        CheckConstraint(
            "frozen_context_revision >= 0", name="ck_session_turn_revision_nonnegative"
        ),
        CheckConstraint(
            "winning_attempt_id IS NULL OR status = 'succeeded'",
            name="ck_session_turn_winner_requires_success",
        ),
        UniqueConstraint("provider_response_id", name="uq_session_turn_provider_response_id"),
        Index("ix_session_turns_session_status", "session_id", "status"),
        Index("ix_session_turns_retry", "status", "next_retry_at"),
    )

    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coaching_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    turn_key: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    frozen_step: Mapped[int] = mapped_column(Integer, nullable=False)
    frozen_context_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    frozen_context_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    provider_operation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_response_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    winning_attempt_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "session_turn_attempts.id",
            name="fk_session_turns_winning_attempt",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        nullable=True,
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reconcile_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    session = relationship("CoachingSession", back_populates="turns")
    attempts = relationship(
        "SessionTurnAttempt",
        back_populates="turn",
        foreign_keys="SessionTurnAttempt.turn_id",
    )
    winning_attempt = relationship(
        "SessionTurnAttempt", foreign_keys=[winning_attempt_id], post_update=True
    )
    context_audit = relationship("SessionTurnContextAudit", back_populates="turn", uselist=False)

    def can_transition_to(self, target: str) -> bool:
        """Return whether `target` is a legal next persisted state."""
        return target in SESSION_TURN_TRANSITIONS.get(self.status, frozenset())

    def transition_to(self, target: str) -> None:
        """Apply a legal state transition or fail before persistence."""
        if not self.can_transition_to(target):
            raise ValueError(f"Illegal SessionTurn transition: {self.status} -> {target}")
        self.status = target


@event.listens_for(SessionTurn, "before_update")
def _validate_session_turn_transition(
    _mapper: object, _connection: object, target: SessionTurn
) -> None:
    history = sa_inspect(target).attrs.status.history
    if not history.has_changes():
        return
    previous = history.deleted[0] if history.deleted else target.status
    if target.status not in SESSION_TURN_TRANSITIONS.get(previous, frozenset()):
        raise ValueError(f"Illegal SessionTurn transition: {previous} -> {target.status}")
