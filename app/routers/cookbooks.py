from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.cookbook import CookbookRecipeRead
from app.services.cookbook_service import CookbookService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cookbooks", tags=["Cookbook Recipes"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_model=list[CookbookRecipeRead])
async def list_cookbooks(
    domain: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[CookbookRecipeRead]:
    """Lista as receitas via API JSON."""
    svc = CookbookService(db)
    recipes = await svc.list_recipes(domain=domain, limit=limit, offset=offset)
    return [CookbookRecipeRead.model_validate(r) for r in recipes]


@router.post("/search/ui", response_class=HTMLResponse)
async def search_cookbooks_ui(
    request: Request,
    question: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Retorna cards HTML das receitas buscando por similaridade semântica (UI)."""
    if not question.strip():
        return HTMLResponse("<div class='text-gray-500'>Digite algo para buscar.</div>")

    svc = CookbookService(db)
    results = await svc.search_recipes(question, limit=5)

    if not results:
        return HTMLResponse(
            "<div class='text-amber-600'>Nenhuma receita encontrada. Ingeste documentos primeiro.</div>"
        )

    # Render results via quick snippet definition or inline logic
    template_str = """
    <div class='space-y-4'>
        {% for recipe, dist in results %}
        <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition hover:shadow-md">
            <div class="flex items-center justify-between mb-2">
                <h3 class="font-bold text-gray-900 text-lg">{{ recipe.title }}</h3>
                <span class="inline-flex rounded-full bg-violet-100 px-2.5 py-0.5 text-xs font-medium text-violet-800 uppercase tracking-widest">
                    {{ recipe.domain }}
                </span>
            </div>
            <p class="text-sm text-gray-600 mb-4">{{ recipe.description }}</p>
            
            {% if recipe.prerequisites %}
            <div class="mb-3 text-sm">
                <strong class="text-gray-900 block text-xs uppercase mb-1">Pré-requisitos:</strong>
                <p class="text-gray-700 whitespace-pre-wrap">{{ recipe.prerequisites }}</p>
            </div>
            {% endif %}
            
            <div class="mb-3 text-sm">
                <strong class="text-gray-900 block text-xs uppercase mb-1">Passo a Passo:</strong>
                <p class="text-gray-700 whitespace-pre-wrap">{{ recipe.steps }}</p>
            </div>

            {% if recipe.code_snippets %}
                <div class="mt-4 space-y-3">
                {% for snippet in recipe.code_snippets %}
                    <div class="rounded bg-gray-900 p-3 overflow-x-auto shadow-inner relative">
                        <span class="absolute top-2 right-2 text-[10px] text-gray-400 font-mono">{{ snippet.language }}</span>
                        {% if snippet.description %}
                            <p class="text-xs text-gray-400 mb-2">// {{ snippet.description }}</p>
                        {% endif %}
                        <pre><code class="text-sm font-mono text-green-400 leading-relaxed">{{ snippet.code }}</code></pre>
                    </div>
                {% endfor %}
                </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    """
    html = templates.env.from_string(template_str).render(results=results)
    return HTMLResponse(content=html)


@router.delete("/{recipe_id}")
async def delete_cookbook(
    recipe_id: UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    svc = CookbookService(db)
    success = await svc.delete_recipe(recipe_id)
    if not success:
        raise HTTPException(status_code=404, detail="Cookbook not found")
    return {"status": "deleted"}
