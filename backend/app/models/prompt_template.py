"""PromptTemplate ORM model for the unified prompt registry."""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PromptTemplate(Base, TimestampMixin):
    """A registered, versioned prompt identified by a stable ``key``.

    ``active_version_id`` points at the currently active :class:`PromptVersion`.
    It is stored as a plain id (no hard FK constraint) to avoid a circular
    foreign-key dependency with ``prompt_versions`` on SQLite batch migrations.
    """

    __tablename__ = "prompt_templates"

    key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(50), default="general")
    description: Mapped[str] = mapped_column(Text, default="")
    # JSON-encoded list of allowed placeholder names, e.g. ["hcp_name", "product"]
    variables: Mapped[str] = mapped_column(Text, default="[]")
    active_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
