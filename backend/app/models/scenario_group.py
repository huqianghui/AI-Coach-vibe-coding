"""Scenario group models for weighted multi-scenario training."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ScenarioGroup(Base, TimestampMixin):
    """A reusable training group composed of multiple single scenarios."""

    __tablename__ = "scenario_groups"
    __table_args__ = (Index("ix_scenario_groups_status", "status"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    pass_threshold: Mapped[int] = mapped_column(default=70)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)

    items = relationship(
        "ScenarioGroupItem",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="ScenarioGroupItem.sort_order",
    )
    runs = relationship("ScenarioGroupRun", back_populates="group")


class ScenarioGroupItem(Base, TimestampMixin):
    """One weighted scenario inside a scenario group."""

    __tablename__ = "scenario_group_items"
    __table_args__ = (
        UniqueConstraint("group_id", "scenario_id", name="uq_scenario_group_items_group_scenario"),
        Index("ix_scenario_group_items_group_order", "group_id", "sort_order"),
    )

    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    weight: Mapped[int] = mapped_column(default=100)
    sort_order: Mapped[int] = mapped_column(default=0)

    group = relationship("ScenarioGroup", back_populates="items")
    scenario = relationship("Scenario")


class ScenarioGroupRun(Base, TimestampMixin):
    """A user's attempt at completing every scenario in a scenario group."""

    __tablename__ = "scenario_group_runs"
    __table_args__ = (
        Index("ix_scenario_group_runs_user_status", "user_id", "status"),
        Index("ix_scenario_group_runs_group", "group_id"),
    )

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_groups.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="created")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    overall_score: Mapped[float | None] = mapped_column(nullable=True)
    passed: Mapped[bool | None] = mapped_column(nullable=True)

    group = relationship("ScenarioGroup", back_populates="runs")
    user = relationship("User")
    items = relationship(
        "ScenarioGroupRunItem",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ScenarioGroupRunItem.sort_order",
    )

    @property
    def group_name(self) -> str | None:
        """Derive scenario group name from relationship for API response."""
        return self.group.name if self.group else None


class ScenarioGroupRunItem(Base, TimestampMixin):
    """Per-scenario progress inside a scenario group run."""

    __tablename__ = "scenario_group_run_items"
    __table_args__ = (
        UniqueConstraint("run_id", "group_item_id", name="uq_scenario_group_run_items_run_item"),
        Index("ix_scenario_group_run_items_run_order", "run_id", "sort_order"),
    )

    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scenario_group_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_group_items.id", ondelete="RESTRICT"), nullable=False
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("coaching_sessions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    weight: Mapped[int] = mapped_column(default=100)
    sort_order: Mapped[int] = mapped_column(default=0)
    score: Mapped[float | None] = mapped_column(nullable=True)
    passed: Mapped[bool | None] = mapped_column(nullable=True)

    run = relationship("ScenarioGroupRun", back_populates="items")
    group_item = relationship("ScenarioGroupItem")
    scenario = relationship("Scenario")
    session = relationship("CoachingSession")
