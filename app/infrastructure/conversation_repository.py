# Copyright (C) 2026 Dione Bastos
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


"""SQLAlchemy implementation of ConversationRepository."""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities import ConversationRecord, MessageDraft, MessageRecord
from app.models.conversation import Conversation, Message

logger = structlog.get_logger()


class ConversationRepositorySQLAlchemy:
    """SQLAlchemy-backed conversation repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, project_id: UUID, title: str,
    ) -> ConversationRecord:
        """Create a new conversation."""
        conversation = Conversation(project_id=project_id, title=title)
        self._session.add(conversation)
        await self._session.flush()
        return ConversationRecord(
            id=conversation.id,
            project_id=conversation.project_id,
            title=conversation.title,
            created_at=conversation.created_at,
        )

    async def add_message(
        self, conversation_id: UUID, message: MessageDraft,
    ) -> MessageRecord:
        """Add a message to a conversation."""
        msg = Message(
            conversation_id=conversation_id,
            role=message.role,
            content=message.content,
        )
        self._session.add(msg)
        await self._session.flush()
        return MessageRecord(
            id=msg.id,
            conversation_id=msg.conversation_id,
            role=msg.role,
            content=msg.content,
            tokens_used=msg.tokens_used,
            created_at=msg.created_at,
        )

    async def get_history(
        self, conversation_id: UUID, limit: int = 20,
    ) -> list[MessageRecord]:
        """Get recent messages from a conversation."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        messages = result.scalars().all()
        return [
            MessageRecord(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                tokens_used=m.tokens_used,
                created_at=m.created_at,
            )
            for m in reversed(messages)  # Return in chronological order
        ]

    async def list_by_project(
        self, project_id: UUID,
    ) -> list[ConversationRecord]:
        """List all conversations for a project."""
        stmt = (
            select(Conversation)
            .where(Conversation.project_id == project_id)
            .order_by(Conversation.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [
            ConversationRecord(
                id=c.id,
                project_id=c.project_id,
                title=c.title,
                created_at=c.created_at,
            )
            for c in result.scalars().all()
        ]

    async def delete(self, conversation_id: UUID) -> bool:
        """Delete a conversation and all its messages."""
        stmt = delete(Conversation).where(
            Conversation.id == conversation_id,
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount and result.rowcount > 0)
