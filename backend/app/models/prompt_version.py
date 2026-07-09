"""PromptVersion ORM model: an immutable content revision of a PromptTemplate."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PromptVersion(Base, TimestampMixin):
    """One immutable version of a prompt's content.

    ``source`` is one of ``seed`` | ``manual`` | ``optimized`` | ``iterate``.
    Only one version per template is active at a time (enforced by the service layer).
    """

    __tablename__ = "prompt_versions"

    template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("prompt_templates.id"), index=True, nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(20), default="seed")
    parent_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
