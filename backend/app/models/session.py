"""Coaching Session ORM model for training session lifecycle."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class CoachingSession(Base, TimestampMixin):
    """Training session tracking lifecycle: created -> in_progress -> completed -> scored."""

    __tablename__ = "coaching_sessions"
    __table_args__ = (
        Index("ix_sessions_user_status", "user_id", "status"),
        Index("ix_sessions_status", "status"),
        Index(
            "ix_sessions_conversation_cleanup",
            "foundry_conversation_state",
            "foundry_conversation_next_cleanup_at",
        ),
        CheckConstraint(
            "foundry_conversation_state IN "
            "('unprovisioned', 'creating', 'active', 'create_unknown', "
            "'cleanup_pending', 'closed')",
            name="ck_sessions_foundry_conversation_state",
        ),
        CheckConstraint(
            "foundry_conversation_create_retry_count >= 0",
            name="ck_sessions_conversation_create_retries_nonnegative",
        ),
        CheckConstraint(
            "foundry_conversation_cleanup_retry_count >= 0",
            name="ck_sessions_conversation_cleanup_retries_nonnegative",
        ),
        CheckConstraint("context_revision >= 0", name="ck_sessions_context_revision_nonnegative"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="created"
    )  # created/in_progress/completed/scored
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(nullable=True)
    key_messages_status: Mapped[str] = mapped_column(
        Text, default="[]"
    )  # JSON: [{message, delivered, detected_at}]
    overall_score: Mapped[float | None] = mapped_column(nullable=True)
    passed: Mapped[bool | None] = mapped_column(nullable=True)

    # Interaction mode: 7 modes per D-06
    mode: Mapped[str] = mapped_column(String(40), default="text")

    # Immutable Foundry Prompt Agent snapshot and internal Responses continuation state
    agent_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    agent_response_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Conference fields
    session_type: Mapped[str] = mapped_column(String(20), default="f2f")  # f2f / conference
    sub_state: Mapped[str] = mapped_column(
        String(20), default=""
    )  # presenting / qa / empty for f2f
    presentation_topic: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    audience_config: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON string

    # Phase 23: Audio storage for voice scoring
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    voice_score_status: Mapped[str] = mapped_column(
        String(20), server_default="none"
    )  # none / pending / processing / completed / failed

    # Skill audit trail — snapshot of which Skill was active when session started
    skill_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="SET NULL"), nullable=True, default=None
    )
    skill_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("skill_versions.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    # Phase 24: Skill Focus instruction snapshot (D-03)
    focus_instruction: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    sop_current_step: Mapped[int | None] = mapped_column(nullable=True, default=0)

    # Phase 31: immutable structured SOP authority captured at Session creation.
    sop_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    sop_snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    context_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Phase 31: internal-only server-owned Foundry Conversation lifecycle.
    foundry_conversation_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    foundry_conversation_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unprovisioned", server_default="unprovisioned"
    )
    foundry_conversation_create_operation_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    foundry_conversation_create_idempotency_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    foundry_conversation_create_lease_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )
    foundry_conversation_create_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )
    foundry_conversation_delete_lease_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )
    foundry_conversation_delete_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )
    foundry_conversation_create_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    foundry_conversation_cleanup_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    foundry_conversation_next_cleanup_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )
    foundry_conversation_last_error: Mapped[str | None] = mapped_column(
        String(500), nullable=True, default=None
    )
    foundry_conversation_created_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )
    foundry_conversation_cleanup_started_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )
    foundry_conversation_closed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )

    # Relationships
    scenario = relationship("Scenario")
    user = relationship("User")
    messages = relationship("SessionMessage", back_populates="session")
    score = relationship("SessionScore", back_populates="session", uselist=False)
    voice_score = relationship("VoiceScore", back_populates="session", uselist=False)
    skill = relationship("Skill", foreign_keys=[skill_id])
    turns = relationship("SessionTurn", back_populates="session")
    turn_context_audits = relationship("SessionTurnContextAudit", back_populates="session")

    @property
    def scenario_name(self) -> str | None:
        """Derive scenario name from relationship for API response."""
        return self.scenario.name if self.scenario else None

    @property
    def message_count(self) -> int:
        """Count of messages in this session."""
        return len(self.messages) if self.messages else 0
