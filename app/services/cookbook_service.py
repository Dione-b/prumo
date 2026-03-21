from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cookbook import CookbookRecipe
from app.services.recipe_extractor import generate_embedding


class CookbookService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_recipes(
        self,
        domain: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CookbookRecipe]:
        query = select(CookbookRecipe).order_by(CookbookRecipe.created_at.desc())

        if domain:
            query = query.where(CookbookRecipe.domain == domain)

        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def search_recipes(
        self, query: str, limit: int = 5
    ) -> list[tuple[CookbookRecipe, float]]:
        """Busca vetor usando pgvector L2 distance."""
        query_emb = await generate_embedding(query)

        # pgvector l2_distance -> order by embedding <-> Cast to vector
        stmt = (
            select(
                CookbookRecipe,
                CookbookRecipe.embedding.l2_distance(query_emb).label("dist"),
            )
            .order_by("dist")
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]

    async def get_recipe(self, recipe_id: UUID) -> CookbookRecipe | None:
        return await self.db.get(CookbookRecipe, recipe_id)

    async def delete_recipe(self, recipe_id: UUID) -> bool:
        recipe = await self.get_recipe(recipe_id)
        if not recipe:
            return False
        await self.db.delete(recipe)
        await self.db.commit()
        return True
