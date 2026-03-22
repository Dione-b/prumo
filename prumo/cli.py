"""CLI do Prumo — entry point que orquestra crawler e exporter.

Único módulo que faz IO de disco. Valida inputs, exibe progresso
com Rich e resolve API keys.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich.console import Console

from prumo.crawler import crawl
from prumo.exporter import export_llms_txt

app = typer.Typer(
    name="prumo",
    help="Convert documentation sites into llms.txt files for AI agents.",
    add_completion=False,
)
console = Console()

API_KEY_ENV_VARS = {
    "gemini": "GEMINI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}


def _resolve_api_key(provider: str, api_key_flag: str | None) -> str:
    """Resolve a API key: flag CLI → variável de ambiente → erro."""
    if api_key_flag:
        return api_key_flag

    env_var = API_KEY_ENV_VARS.get(provider, "")
    env_value = os.environ.get(env_var, "")
    if env_value:
        return env_value

    console.print(
        f"[bold red]Erro:[/] API key não fornecida. "
        f"Use --api-key ou defina a variável de ambiente {env_var}.",
    )
    raise typer.Exit(code=1)


def _validate_url(url: str) -> None:
    """Valida que a URL é acessível antes de crawlear."""
    try:
        with httpx.Client(timeout=10) as client:
            response = client.head(url, follow_redirects=True)
            response.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        console.print(f"[bold red]Erro:[/] URL inacessível: {url}")
        console.print(f"  Detalhe: {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def fetch(
    url: Annotated[str, typer.Argument(help="Root URL of the documentation site")],
    output: Annotated[
        str, typer.Option("--output", "-o", help="Output directory")
    ] = "./output",
    provider: Annotated[
        str,
        typer.Option("--provider", "-p", help="LLM provider: gemini or claude"),
    ] = "gemini",
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", "-k", help="API key for the LLM provider"),
    ] = None,
    max_pages: Annotated[
        int,
        typer.Option("--max-pages", "-m", help="Maximum number of pages to crawl"),
    ] = 50,
) -> None:
    """Fetch documentation from a URL and generate an llms.txt file."""
    if provider not in ("gemini", "claude"):
        msg = f"Provider inválido: '{provider}'."
        console.print(
            f"[bold red]Erro:[/] {msg} "
            "Use 'gemini' ou 'claude'."
        )
        raise typer.Exit(code=1)

    resolved_key = _resolve_api_key(provider, api_key)

    console.print(f"\n[bold]🔍 Validating URL:[/] {url}")
    _validate_url(url)

    console.print(f"[bold]🕷️  Crawling [cyan]{url}[/cyan]...[/]")
    pages = crawl(url, max_pages=max_pages)

    if not pages:
        console.print("[bold yellow]Aviso:[/] Nenhuma página encontrada.")
        raise typer.Exit(code=1)

    console.print(f"  ✅ {len(pages)} pages found\n")

    console.print(
        f"[bold]📝 Exporting to llms.txt via [cyan]{provider}[/cyan]...[/]"
    )
    result = export_llms_txt(pages, provider, resolved_key)  # type: ignore[arg-type]

    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "llms.txt"
    output_file.write_text(result, encoding="utf-8")

    console.print(
        f"\n[bold green]✅ Done![/] llms.txt written to [cyan]{output_file}[/cyan]\n"
    )


if __name__ == "__main__":
    app()
