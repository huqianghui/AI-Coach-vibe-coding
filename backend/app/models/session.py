"""Coaching Session ORM model for training session lifecycle."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class CoachingSession(Base, TimestampMixin):
    """Training session tracking lifecycle: created -> in_progress -> completed -> scored."""

    __tablename__ = "coaching_sessions"
    __table_args__ = (
        Index("ix_sessions_user_status", "user_id", "status"),
        Index("ix_sessions_status", "status"),
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

    # Relationships
    scenario = relationship("Scenario")
    user = relationship("User")
    messages = relationship("SessionMessage", back_populates="session")
    score = relationship("SessionScore", back_populates="session", uselist=False)
    skill = relationship("Skill", foreign_keys=[skill_id])

    @property
    def scenario_name(self) -> str | None:
        """Derive scenario name from relationship for API response."""
        return self.scenario.name if self.scenario else None

    @property
    def message_count(self) -> int:
        """Count of messages in this session."""
        return len(self.messages) if self.messages else 0
