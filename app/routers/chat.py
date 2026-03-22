from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import StellarChatService

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/stellar", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def stellar_chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Chat conversacional sobre a rede Stellar usando docs oficiais e SDKs.
    """
    if not settings.stellar_project_id:
        raise HTTPException(
            status_code=503,
            detail="STELLAR_PROJECT_ID is not configured.",
        )

    chat_service = StellarChatService(db)
    answer, sources = await chat_service.answer(
        question=request.question,
        history=request.history,
        project_id=settings.stellar_project_id,
    )
    return ChatResponse(
        answer=answer,
        sources=sources,
        session_id=request.session_id,
    )
