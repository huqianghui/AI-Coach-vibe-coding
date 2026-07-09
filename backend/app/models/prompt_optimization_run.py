"""PromptOptimizationRun ORM model: an auditable record of one AI optimization."""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PromptOptimizationRun(Base, TimestampMixin):
    """Records a single prompt-optimizer invocation (F3: optimization process).

    ``mode`` is one of ``system`` | ``user`` | ``iterate``. ``resulting_version_id``
    is backfilled when the run is adopted as a new :class:`PromptVersion`.
    """

    __tablename__ = "prompt_optimization_runs"

    template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("prompt_templates.id"), index=True, nullable=False
    )
    base_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    mode: Mapped[str] = mapped_column(String(20), default="system")
    optimizer_template: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    result_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(20), default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    resulting_version_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, default=None
    )
