import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime as SADateTime
from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from . import Base


class GeneratedPromptModel(Base):
    """
    Registro histórico de um prompt gerado.
    Em ambientes containerizados, usado no lugar do disco com ttl nativo.
    """

    __tablename__ = "generated_prompts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    metadata_info: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'{}'::jsonb",
    )

    created_at: Mapped[datetime] = mapped_column(
        SADateTime(timezone=True),
        default=func.now(),
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        SADateTime(timezone=True),
        nullable=True,
    )
