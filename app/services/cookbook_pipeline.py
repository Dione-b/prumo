from __future__ import annotations

import logging
from uuid import UUID

from pypdf import PdfReader
from sqlalchemy import select, update

from app.database import async_session_maker
from app.models.cookbook import CookbookRecipe
from app.models.knowledge import KnowledgeDocument
from app.services.recipe_extractor import extract_recipes_from_text, generate_embedding

logger = logging.getLogger(__name__)


def _extract_pdf_text(path: str) -> str:
    """Sincrono: extrai texto bruto de um PDF. Chamado via to_thread."""
    try:
        reader = PdfReader(path)
        pages = [p.extract_text() for p in reader.pages]
        return "\n\n".join(t for t in pages if t)
    except Exception as e:
        logger.error("Falha ao extrair texto do PDF: %s", e)
        return ""


async def process_document_to_cookbooks(document_id: UUID) -> None:
    """
    Carrega o texto, gera embedding do documento e extrai cookbooks via Gemini.
    """

    # 1. Busca documento e valida conteúdo
    async with async_session_maker() as db:
        doc = await db.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        )
        if not doc:
            return

        content = doc.content

        if doc.source_type == "application/pdf" and not content:
            await db.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(
                    status="ERROR", error_message="PDF sem conteúdo textual extraído."
                )
            )
            await db.commit()
            return

        if not content or not content.strip():
            await db.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(status="ERROR", error_message="Documento sem conteúdo textual.")
            )
            await db.commit()
            return

    try:
        # 2. Embedding do Documento via Gemini
        doc_emb = await generate_embedding(content)

        async with async_session_maker() as db:
            await db.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(embedding=doc_emb)
            )
            await db.commit()

        # 3. Extrair receitas do texto (Gemini 2.5 Flash / JSON)
        extracted = await extract_recipes_from_text(content)
        recipes_to_insert = []

        # 4. Processar receitas gerando Embedding individual para busca semântica
        for recipe_data in extracted.recipes:
            # Concatena titulo + descrição pra ser o kernel de busca
            search_text = "\n".join(
                [
                    f"Title: {recipe_data.title}",
                    f"Desc: {recipe_data.description}",
                    f"Prerequisites: {recipe_data.prerequisites}",
                ]
            )
            recipe_emb = await generate_embedding(search_text)

            new_recipe = CookbookRecipe(
                title=recipe_data.title,
                description=recipe_data.description,
                domain=recipe_data.domain,
                prerequisites=recipe_data.prerequisites,
                steps=recipe_data.steps,
                code_snippets=[s.model_dump() for s in recipe_data.code_snippets]
                if recipe_data.code_snippets
                else None,
                references=recipe_data.references,
                source_document_ids=[str(document_id)],
                embedding=recipe_emb,
                status="published",
            )
            recipes_to_insert.append(new_recipe)

        # 5. Salva Receitas no Banco de Dados
        async with async_session_maker() as db:
            if recipes_to_insert:
                db.add_all(recipes_to_insert)

            await db.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(status="READY")
            )
            await db.commit()

        logger.info(
            "document_transformed_to_cookbooks doc_id=%s recipes=%s",
            document_id,
            len(recipes_to_insert),
        )

    except Exception as exc:
        async with async_session_maker() as db:
            await db.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(status="ERROR", error_message=str(exc)[:500])
            )
            await db.commit()
        logger.exception("Fala ao processar doc to cookbooks", exc_info=exc)
