"""Scenario ORM model for training session configuration."""

import json

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Scenario(Base, TimestampMixin):
    """Training scenario with HCP profile, key messages, and rubric-based scoring."""

    __tablename__ = "scenarios"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of tag strings
    mode: Mapped[str] = mapped_column(String(20), default="f2f")  # f2f / conference
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft / active / archived
    hcp_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hcp_profiles.id"), nullable=False, index=True
    )
    key_messages: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of strings
    conference_prompt_config: Mapped[str] = mapped_column(Text, default="{}")
    # Bumped whenever conference_prompt_config changes, for audit/version history (PROMPT-01)
    conference_prompt_version: Mapped[int] = mapped_column(default=1)

    # Skill association — version-pinned for deterministic agent behavior (D-21, D-22)
    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="RESTRICT"), nullable=False
    )
    skill_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("skill_versions.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    # Scoring rubric (NOT NULL — every scenario must have an explicit rubric per D-05)
    rubric_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scoring_rubrics.id"), nullable=False
    )

    pass_threshold: Mapped[int] = mapped_column(default=70)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)

    # Relationships
    hcp_profile = relationship("HcpProfile", back_populates="scenarios")
    rubric = relationship("ScoringRubric", foreign_keys=[rubric_id])
    skill = relationship("Skill", foreign_keys=[skill_id])
    skill_version = relationship("SkillVersion", foreign_keys=[skill_version_id])

    @property
    def product(self) -> str:
        """Extract product from tags for backward compatibility."""
        try:
            tag_list = json.loads(self.tags) if self.tags else []
            for tag in tag_list:
                if tag.startswith("product:"):
                    return tag.split(":", 1)[1]
        except (json.JSONDecodeError, TypeError):
            pass
        return ""

    @property
    def therapeutic_area(self) -> str:
        """Extract therapeutic_area from tags for backward compatibility."""
        try:
            tag_list = json.loads(self.tags) if self.tags else []
            for tag in tag_list:
                if tag.startswith("area:") or tag.startswith("therapeutic_area:"):
                    return tag.split(":", 1)[1]
        except (json.JSONDecodeError, TypeError):
            pass
        return ""
