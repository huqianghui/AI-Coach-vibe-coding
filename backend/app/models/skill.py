"""Skill ORM models for coaching skill lifecycle management."""

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# Strict state transition matrix — the SOLE source of truth for lifecycle transitions.
# No ad-hoc transition logic elsewhere; all validation goes through this dict.
VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"review"},
    "review": {"draft", "published"},
    "published": {"archived"},
    "archived": {"draft"},
    "failed": {"draft"},
}


class Skill(Base, TimestampMixin):
    """A coaching skill package with lifecycle management and versioning."""

    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    product: Mapped[str] = mapped_column(String(255), default="", index=True)
    therapeutic_area: Mapped[str] = mapped_column(String(255), default="")
    compatibility: Mapped[str] = mapped_column(String(255), default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    tags: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)

    # Audit columns
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(36), default="")

    # Quality evaluation fields (L1 structure check)
    structure_check_passed: Mapped[bool | None] = mapped_column(Boolean, default=None)
    structure_check_details: Mapped[str] = mapped_column(Text, default="{}")

    # Quality evaluation fields (L2 AI quality)
    quality_score: Mapped[int | None] = mapped_column(Integer, default=None)
    quality_verdict: Mapped[str | None] = mapped_column(String(20), default=None)
    quality_details: Mapped[str] = mapped_column(Text, default="{}")

    # Conversion tracking
    conversion_status: Mapped[str | None] = mapped_column(String(20), default=None)
    conversion_error: Mapped[str] = mapped_column(Text, default="")
    conversion_job_id: Mapped[str | None] = mapped_column(String(36), default=None)

    # Foundry Skill sync (Phase 28: D-01, D-03, D-06)
    foundry_skill_name: Mapped[str] = mapped_column(String(64), default="")
    foundry_sync_status: Mapped[str] = mapped_column(String(20), default="none")  # none|pending|synced|failed
    foundry_sync_error: Mapped[str] = mapped_column(Text, default="")
    foundry_cloud_version: Mapped[str] = mapped_column(String(20), default="")

    # Relationships
    versions = relationship(
        "SkillVersion",
        back_populates="skill",
        order_by="SkillVersion.version_number.desc()",
        cascade="all, delete-orphan",
    )
    resources = relationship(
        "SkillResource",
        back_populates="skill",
        cascade="all, delete-orphan",
    )
    source_material_links = relationship(
        "SkillSourceMaterial",
        back_populates="skill",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_skills_status_product", "status", "product"),
        Index("ix_skills_created_at", "created_at"),
    )


class SkillVersion(Base, TimestampMixin):
    """An immutable snapshot of a skill version. Once created, only is_published can change."""

    __tablename__ = "skill_versions"

    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    change_notes: Mapped[str] = mapped_column(Text, default="")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(36), default="")

    # Relationships
    skill = relationship("Skill", back_populates="versions")


class SkillResource(Base, TimestampMixin):
    """A file resource attached to a skill (reference, script, or asset)."""

    __tablename__ = "skill_resources"

    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("skill_versions.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    text_content: Mapped[str] = mapped_column(Text, default="")
    extraction_status: Mapped[str | None] = mapped_column(String(20), default=None)

    # Relationships
    skill = relationship("Skill", back_populates="resources")

    __table_args__ = (Index("ix_skill_resources_skill_type", "skill_id", "resource_type"),)


class SkillSourceMaterial(Base, TimestampMixin):
    """Junction table linking Skills to their source Training Materials."""

    __tablename__ = "skill_source_materials"

    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("training_materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationships
    skill = relationship("Skill", back_populates="source_material_links")
    material = relationship("TrainingMaterial", back_populates="derived_skill_links")

    __table_args__ = (UniqueConstraint("skill_id", "material_id", name="uq_skill_source_material"),)
