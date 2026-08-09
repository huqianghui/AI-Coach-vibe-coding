"""Immutable committed context and result audit for Session turns."""

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


class SessionTurnContextAudit(Base):
    """Append-only audit retained with its parent Session and winning turn."""

    __tablename__ = "session_turn_context_audits"
    __table_args__ = (
        UniqueConstraint("session_id", "turn_key", name="uq_session_turn_context_audit"),
        UniqueConstraint("turn_id", name="uq_session_turn_context_audit_turn"),
        CheckConstraint(
            "terminal_status IN ('succeeded', 'failed_terminal', 'cancelled')",
            name="ck_session_turn_context_audit_terminal_status",
        ),
        CheckConstraint("applied_step >= 0", name="ck_session_turn_audit_step_nonnegative"),
        CheckConstraint(
            "applied_context_revision >= 0", name="ck_session_turn_audit_revision_nonnegative"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coaching_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("session_turns.id", ondelete="RESTRICT"), nullable=False
    )
    turn_key: Mapped[str] = mapped_column(String(36), nullable=False)
    terminal_status: Mapped[str] = mapped_column(String(32), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(50), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(36), nullable=False)
    skill_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sop_snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    focus_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    context_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    context_schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    applied_step: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_context_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    user_message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("session_messages.id", ondelete="RESTRICT"), nullable=True
    )
    assistant_message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("session_messages.id", ondelete="RESTRICT"), nullable=True
    )
    conversation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    winning_attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("session_turn_attempts.id", ondelete="RESTRICT"), nullable=True
    )
    provider_response_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    iq_correlation_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    progression_result: Mapped[str] = mapped_column(String(32), nullable=False)
    progression_from_step: Mapped[int] = mapped_column(Integer, nullable=False)
    progression_to_step: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    session = relationship("CoachingSession", back_populates="turn_context_audits")
    turn = relationship("SessionTurn", back_populates="context_audit")
    winning_attempt = relationship("SessionTurnAttempt", foreign_keys=[winning_attempt_id])


def _reject_context_audit_mutation(_mapper: object, _connection: object, _target: object) -> None:
    raise ValueError("SessionTurnContextAudit rows are immutable")


event.listen(SessionTurnContextAudit, "before_update", _reject_context_audit_mutation)
event.listen(SessionTurnContextAudit, "before_delete", _reject_context_audit_mutation)
