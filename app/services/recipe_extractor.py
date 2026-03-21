from __future__ import annotations

import asyncio
from typing import Any

import structlog
from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.schemas.cookbook import RecipeExtractionResponse

logger = structlog.get_logger(__name__)
client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

SYSTEM_PROMPT = """Você é um especialista altamente qualificado no ecossistema Stellar.
Seu objetivo é analisar textos fornecidos (documentações, newsletters, RFCs) e extrair REGRAS ou TUTORIAIS no formato de "Cookbooks" (Receitas de Bolo) voltados a desenvolvedores.

Regras para extração:
1. Retorne APENAS um objeto JSON com uma chave `recipes` que contém a lista de receitas extraídas.
2. Cada receita deve conter:
   - title: Título claro da receita.
   - description: Descrição sucinta.
   - domain: DEVE ser um dos seguintes: payments, zk, smart-contracts, sdk, tooling.
   - prerequisites: Lista de dependências / conhecimentos prévios em texto.
   - steps: Passo a passo claro explicando o tutorial em texto.
   - code_snippets: Pode ser uma lista de dicionários contendo `language`, `code`, e opcionalmente `description`.
   - references: Lista de URLs referenciadas no próprio texto.
3. Se não encontrar nenhuma receita útil para devs, retorne {"recipes": []}.
4. NUNCA adicione blocos de markdown no início ou no fim da resposta, retorne apenas o JSON limpo.
"""


def _log_retry(retry_state: Any) -> None:
    logger.warning("recipe_extractor_retry", attempt=retry_state.attempt_number)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    before_sleep=_log_retry,
    reraise=True,
)
async def extract_recipes_from_text(raw_text: str) -> RecipeExtractionResponse:
    """Extrai receitas de cookbook via Gemini 2.5 Flash de forma assíncrona."""
    prompt = f"Extraia as receitas baseadas neste texto:\n\n{raw_text}"

    def sync_call() -> Any:
        return client.models.generate_content(
            model=settings.gemini_extraction_model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RecipeExtractionResponse,
                temperature=0.2,
                system_instruction=SYSTEM_PROMPT,
            ),
        )

    response = await asyncio.to_thread(sync_call)

    usage = getattr(response, "usage_metadata", None)
    if usage:
        logger.info(
            "gemini_cookbook_extraction",
            prompt_tokens=usage.prompt_token_count,
            completion_tokens=usage.candidates_token_count,
        )

    return RecipeExtractionResponse.model_validate_json(str(response.text))


async def generate_embedding(text: str) -> list[float]:
    """Gera um único vetor de embedding via text-embedding-004."""
    if not text.strip():
        # Fallback to zero vector to avoid crashing or return specific exception
        return [0.0] * settings.gemini_embedding_dim

    def sync_embed() -> list[float]:
        result = client.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=text,
            config=genai.types.EmbedContentConfig(
                output_dimensionality=settings.gemini_embedding_dim,
            ),
        )
        # return list of floats
        return result.embeddings[0].values  # type: ignore

    return await asyncio.to_thread(sync_embed)
