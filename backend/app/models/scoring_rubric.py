"""Scoring Rubric ORM model for customizable scoring criteria."""

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ScoringRubric(Base, TimestampMixin):
    """Admin-configurable scoring rubric with dimensions, weights, and criteria."""

    __tablename__ = "scoring_rubrics"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    scenario_type: Mapped[str] = mapped_column(String(50), default="f2f")  # f2f / conference
    dimensions: Mapped[str] = mapped_column(
        Text, default="[]"
    )  # JSON: [{name, weight, criteria[], max_score}]
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
