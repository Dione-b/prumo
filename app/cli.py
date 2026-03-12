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


"""Prumo CLI — personal assistant for vibecoding.

Usage:
    prumo ingest <path> --project <name>
    prumo ask "<question>" --project <name>
    prumo generate "<task>" --project <name>
    prumo conversations list --project <name>
    prumo conversations show <id>
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import UUID

import click
import structlog

logger = structlog.get_logger()


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Run an async coroutine in a new event loop."""
    return asyncio.run(coro)


@click.group()
def main() -> None:
    """Prumo — Assistente pessoal para vibecoding."""


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--project", required=True, help="Nome do projeto.")
def ingest(path: str, project: str) -> None:
    """Ingerir um arquivo ou diretório no grafo de conhecimento."""

    async def _ingest() -> None:
        from app.database import async_session_factory
        from app.infrastructure.uow_sqlalchemy import SQLAlchemyUnitOfWork
        from app.services.gemini_client import GeminiClient
        from app.services.knowledge_gemini import process_document_task

        uow = SQLAlchemyUnitOfWork(async_session_factory)

        # Ensure project exists
        async with uow.transaction() as tx:
            existing = None
            # Try to find project by name
            from sqlalchemy import select

            from app.models.project import Project

            async with async_session_factory() as session:
                result = await session.execute(
                    select(Project).where(Project.name == project)
                )
                existing = result.scalar_one_or_none()

            if existing is None:
                from app.domain.entities import ProjectDraft

                record = await tx.projects.add(
                    ProjectDraft(name=project, stack="auto", description=None)
                )
                project_id = record.id
                click.echo(f"✅ Projeto '{project}' criado: {project_id}")
            else:
                project_id = existing.id
                click.echo(f"📂 Projeto '{project}' encontrado: {project_id}")

        # Ingest files
        target = Path(path)
        files = [target] if target.is_file() else sorted(target.rglob("*"))
        code_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go",
            ".java", ".kt", ".rb", ".php", ".c", ".cpp", ".h",
            ".css", ".html", ".sql", ".sh", ".yaml", ".yml",
            ".toml", ".json", ".md", ".txt",
        }

        ingested = 0
        for file_path in files:
            if not file_path.is_file():
                continue
            if file_path.suffix not in code_extensions:
                continue
            if any(
                part.startswith(".")
                or part in {"__pycache__", "node_modules", ".git", "venv"}
                for part in file_path.parts
            ):
                continue

            click.echo(f"  📄 {file_path.relative_to(target if target.is_dir() else target.parent)}")

            content = file_path.read_text(encoding="utf-8", errors="replace")
            source_type = file_path.suffix.lstrip(".")

            async with uow.transaction() as tx:
                from app.domain.entities import KnowledgeDocumentDraft

                draft = KnowledgeDocumentDraft(
                    project_id=project_id,
                    title=str(file_path.name),
                    source_type=source_type,
                    content=content,
                    status="PROCESSING",
                )
                doc_record = await tx.knowledge_documents.add(draft)

            # Process in background (extraction + embedding)
            await process_document_task(doc_record.id)
            ingested += 1

        click.echo(f"\n🎉 {ingested} arquivo(s) ingerido(s) no projeto '{project}'.")

    _run_async(_ingest())


@main.command()
@click.argument("question")
@click.option("--project", required=True, help="Nome do projeto.")
@click.option(
    "--conversation-id", default=None,
    help="ID de conversa existente (opcional).",
)
@click.option(
    "--mode", default="hybrid",
    type=click.Choice(["local", "global", "hybrid"]),
    help="Modo de query do Graph RAG.",
)
def ask(question: str, project: str, conversation_id: str | None, mode: str) -> None:
    """Perguntar sobre o código ingerido."""

    async def _ask() -> None:
        from app.database import async_session_factory, async_session_maker
        from app.domain.entities import MessageDraft
        from app.infrastructure.uow_sqlalchemy import SQLAlchemyUnitOfWork
        from app.services.graph_query_service import GraphQueryService

        uow = SQLAlchemyUnitOfWork(async_session_factory)

        # Find project
        from sqlalchemy import select

        from app.models.project import Project

        async with async_session_maker() as session:
            result = await session.execute(
                select(Project).where(Project.name == project)
            )
            proj = result.scalar_one_or_none()

        if proj is None:
            click.echo(f"❌ Projeto '{project}' não encontrado.", err=True)
            sys.exit(1)

        # Handle conversation
        conv_uuid = UUID(conversation_id) if conversation_id else None
        if conv_uuid is None:
            async with uow.transaction() as tx:
                conv = await tx.conversations.create(
                    proj.id, f"CLI: {question[:50]}"
                )
                conv_uuid = conv.id

        # Save user message
        async with uow.transaction() as tx:
            await tx.conversations.add_message(
                conv_uuid, MessageDraft(role="user", content=question)
            )

        # Query graph
        service = GraphQueryService()
        async with async_session_maker() as session:
            if mode == "local":
                answer = await service.local_query(session, proj.id, question)
            elif mode == "global":
                answer = await service.global_query(session, proj.id, question)
            else:
                answer = await service.hybrid_query(session, proj.id, question)

        # Save assistant response
        async with uow.transaction() as tx:
            await tx.conversations.add_message(
                conv_uuid,
                MessageDraft(role="assistant", content=answer.answer),
            )

        click.echo(f"\n💬 Conversa: {conv_uuid}")
        click.echo(f"📊 Confiança: {answer.confidence_level}")
        click.echo(f"\n{answer.answer}")

        if answer.citations:
            click.echo("\n📚 Citações:")
            for c in answer.citations:
                click.echo(f"  - {c.snippet}")

    _run_async(_ask())


@main.command()
@click.argument("task")
@click.option("--project", required=True, help="Nome do projeto.")
@click.option("--language", default="python", help="Linguagem alvo.")
def generate(task: str, project: str, language: str) -> None:
    """Gerar código com base no contexto do projeto."""

    async def _generate() -> None:
        from app.database import async_session_maker

        from sqlalchemy import select

        from app.models.project import Project
        from app.services.codegen import CodegenService

        async with async_session_maker() as session:
            result = await session.execute(
                select(Project).where(Project.name == project)
            )
            proj = result.scalar_one_or_none()

        if proj is None:
            click.echo(f"❌ Projeto '{project}' não encontrado.", err=True)
            sys.exit(1)

        service = CodegenService()
        async with async_session_maker() as session:
            code = await service.generate(session, task, proj.id, language)

        click.echo(code)

    _run_async(_generate())


@main.group()
def conversations() -> None:
    """Gerenciar conversas."""


@conversations.command("list")
@click.option("--project", required=True, help="Nome do projeto.")
def conversations_list(project: str) -> None:
    """Listar conversas de um projeto."""

    async def _list() -> None:
        from app.database import async_session_factory, async_session_maker
        from app.infrastructure.uow_sqlalchemy import SQLAlchemyUnitOfWork

        from sqlalchemy import select

        from app.models.project import Project

        async with async_session_maker() as session:
            result = await session.execute(
                select(Project).where(Project.name == project)
            )
            proj = result.scalar_one_or_none()

        if proj is None:
            click.echo(f"❌ Projeto '{project}' não encontrado.", err=True)
            sys.exit(1)

        uow = SQLAlchemyUnitOfWork(async_session_factory)
        async with uow.transaction() as tx:
            convs = await tx.conversations.list_by_project(proj.id)

        if not convs:
            click.echo("Nenhuma conversa encontrada.")
            return

        for c in convs:
            click.echo(
                f"  {c.id}  |  {c.title}  |  {c.created_at:%Y-%m-%d %H:%M}"
            )

    _run_async(_list())


@conversations.command("show")
@click.argument("conversation_id")
def conversations_show(conversation_id: str) -> None:
    """Mostrar histórico de uma conversa."""

    async def _show() -> None:
        from app.database import async_session_factory
        from app.infrastructure.uow_sqlalchemy import SQLAlchemyUnitOfWork

        uow = SQLAlchemyUnitOfWork(async_session_factory)
        conv_uuid = UUID(conversation_id)

        async with uow.transaction() as tx:
            messages = await tx.conversations.get_history(conv_uuid, limit=50)

        if not messages:
            click.echo("Nenhuma mensagem encontrada.")
            return

        for msg in messages:
            role_icon = "👤" if msg.role == "user" else "🤖"
            click.echo(f"\n{role_icon} [{msg.role}] ({msg.created_at:%H:%M}):")
            click.echo(f"  {msg.content}")

    _run_async(_show())


if __name__ == "__main__":
    main()
