"""CLI do Prumo — entry point que orquestra crawler e exporter.

Único módulo que faz IO de disco. Valida inputs, exibe progresso
com Rich e resolve API keys.

Comandos disponíveis:
  prumo init   → wizard interativo que cria o .env com as credenciais necessárias
  prumo fetch  → crawlea documentação e gera llms.txt

Modos de operação do fetch:
  - Padrão:    crawling HTTP estático (httpx + BeautifulSoup)
  - --github:  leitura via GitHub Contents API (.md/.mdx), contorna JS-Wall

Resolução de credenciais (ordem de prioridade):
  1. Flag CLI        (--api-key, --github-token)
  2. Arquivo .env    (carregado automaticamente do diretório atual)
  3. Variável de ambiente do shell
  4. Erro com instrução clara — rode `prumo init` para configurar
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated

import httpx
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from prumo.crawler import crawl, crawl_github
from prumo.exporter import export_llms_txt

# Carrega o .env do diretório onde o comando é executado.
# override=False garante que variáveis já definidas no shell têm precedência.
load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)

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


@app.callback()
def _callback() -> None:
    pass


# ---------------------------------------------------------------------------
# Helpers de resolução de credenciais
# ---------------------------------------------------------------------------


def _resolve_api_key(provider: str, api_key_flag: str | None) -> str:
    """Resolve a API key: flag CLI → variável de ambiente → erro."""
    if api_key_flag:
        return api_key_flag

    env_var = API_KEY_ENV_VARS.get(provider, "")
    env_value = os.environ.get(env_var, "")
    if env_value:
        return env_value

    console.print(
        f"\n[bold red]Erro:[/] API key não encontrada para o provider '[cyan]{provider}[/cyan]'.\n\n"
        f"  Configure rapidamente rodando:\n"
        f"    [bold green]prumo init[/bold green]\n\n"
        f"  Ou adicione manualmente ao [bold].env[/bold]:\n"
        f"    [green]{env_var}=sua-chave-aqui[/green]"
    )
    raise typer.Exit(code=1)


def _resolve_github_token(github_token_flag: str | None) -> str:
    """Resolve o GitHub token: flag CLI → GITHUB_TOKEN env → erro."""
    if github_token_flag:
        return github_token_flag

    env_value = os.environ.get("GITHUB_TOKEN", "")
    if env_value:
        return env_value

    console.print(
        "\n[bold red]Erro:[/] GitHub token não encontrado.\n\n"
        "  Configure rapidamente rodando:\n"
        "    [bold green]prumo init[/bold green]\n\n"
        "  Ou adicione manualmente ao [bold].env[/bold]:\n"
        "    [green]GITHUB_TOKEN=seu-token-aqui[/green]"
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


# ---------------------------------------------------------------------------
# Comando: prumo init
# ---------------------------------------------------------------------------


@app.command()
def init(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Sobrescreve o .env existente sem perguntar"),
    ] = False,
) -> None:
    """Configura as credenciais do Prumo criando um arquivo .env interativamente."""

    env_path = Path.cwd() / ".env"

    console.print()
    console.print(Panel(
        "[bold cyan]Prumo[/bold cyan] — Configuração inicial\n\n"
        "Este wizard vai criar um arquivo [bold].env[/bold] com suas credenciais.\n"
        "As chaves são armazenadas [bold]localmente[/bold] e nunca saem da sua máquina.",
        expand=False,
    ))
    console.print()

    # Avisa se o .env já existe
    if env_path.exists() and not force:
        overwrite = typer.confirm(
            f"  O arquivo .env já existe em {env_path}. Deseja sobrescrevê-lo?",
            default=False,
        )
        if not overwrite:
            console.print("\n[yellow]Operação cancelada.[/yellow] Use [bold]--force[/bold] para sobrescrever sem confirmação.\n")
            raise typer.Exit()
        console.print()

    lines: list[str] = ["# Prumo — credenciais\n# Gerado por `prumo init`\n"]

    # ------------------------------------------------------------------
    # LLM Provider
    # ------------------------------------------------------------------
    console.print("[bold]1. Provider de LLM[/bold]")
    console.print("   Qual provider você quer usar para gerar o llms.txt?\n")

    provider_choice = typer.prompt(
        "   Provider",
        default="gemini",
        prompt_suffix=" [gemini/claude/ambos]: ",
        show_default=False,
    ).strip().lower()

    while provider_choice not in ("gemini", "claude", "ambos"):
        console.print("   [red]Opção inválida.[/red] Digite gemini, claude ou ambos.")
        provider_choice = typer.prompt(
            "   Provider",
            default="gemini",
            prompt_suffix=" [gemini/claude/ambos]: ",
            show_default=False,
        ).strip().lower()

    console.print()

    if provider_choice in ("gemini", "ambos"):
        console.print("[bold]2. Gemini API Key[/bold]")
        console.print("   Obtenha em: [link]https://aistudio.google.com/app/apikey[/link]\n")
        gemini_key = typer.prompt("   GEMINI_API_KEY", hide_input=True).strip()
        lines.append(f"\n# Google Gemini\nGEMINI_API_KEY={gemini_key}")
        console.print()

    if provider_choice in ("claude", "ambos"):
        console.print("[bold]3. Anthropic API Key[/bold]" if provider_choice == "claude" else "[bold]3. Anthropic API Key[/bold]")
        console.print("   Obtenha em: [link]https://console.anthropic.com/settings/keys[/link]\n")
        anthropic_key = typer.prompt("   ANTHROPIC_API_KEY", hide_input=True).strip()
        lines.append(f"\n# Anthropic Claude\nANTHROPIC_API_KEY={anthropic_key}")
        console.print()

    # ------------------------------------------------------------------
    # GitHub Token (opcional)
    # ------------------------------------------------------------------
    next_num = 3 if provider_choice == "ambos" else 2
    console.print(f"[bold]{next_num + 1}. GitHub Token[/bold] [dim](opcional — necessário apenas para --github)[/dim]")
    console.print("   Usado para ler .md/.mdx diretamente do repositório GitHub.")
    console.print("   Obtenha em: [link]https://github.com/settings/tokens[/link] (escopo: repo ou public_repo)\n")

    use_github = typer.confirm("   Deseja configurar o GitHub token agora?", default=True)

    if use_github:
        console.print()
        github_token = typer.prompt("   GITHUB_TOKEN", hide_input=True).strip()
        lines.append(f"\n# GitHub (necessário para --github)\nGITHUB_TOKEN={github_token}")

    console.print()

    # ------------------------------------------------------------------
    # Escreve o arquivo
    # ------------------------------------------------------------------
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    console.print(Panel(
        f"[bold green]✅ .env criado com sucesso![/bold green]\n\n"
        f"  Localização: [cyan]{env_path}[/cyan]\n\n"
        f"  Próximo passo:\n"
        f"    [bold]prumo fetch <url-da-docs>[/bold]\n\n"
        f"  Com GitHub mode:\n"
        f"    [bold]prumo fetch <url-do-repo> --github[/bold]",
        expand=False,
    ))
    console.print()


# ---------------------------------------------------------------------------
# Comando: prumo fetch
# ---------------------------------------------------------------------------


@app.command()
def fetch(
    url: Annotated[str, typer.Argument(help="URL da documentação ou repositório GitHub")],
    output: Annotated[
        str, typer.Option("--output", "-o", help="Diretório de saída")
    ] = "./output",
    provider: Annotated[
        str,
        typer.Option("--provider", "-p", help="LLM provider: gemini ou claude"),
    ] = "gemini",
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", "-k", help="API key do provider LLM"),
    ] = None,
    max_pages: Annotated[
        int,
        typer.Option("--max-pages", "-m", help="Máximo de páginas/arquivos a processar"),
    ] = 50,
    github: Annotated[
        bool,
        typer.Option(
            "--github",
            help=(
                "Usa a GitHub Contents API para ler .md/.mdx do repositório. "
                "Ideal para sites com JS-Wall (Docusaurus, VitePress, Next.js). "
                "Requer GITHUB_TOKEN ou --github-token."
            ),
        ),
    ] = False,
    github_token: Annotated[
        str | None,
        typer.Option("--github-token", help="GitHub Personal Access Token"),
    ] = None,
    docs_base_url: Annotated[
        str | None,
        typer.Option(
            "--docs-base-url",
            "-d",
            help=(
                "URL base da documentação publicada. Quando fornecida, os links no "
                "llms.txt apontarão para o site da docs em vez do código-fonte no GitHub. "
                "Exemplo: --docs-base-url https://developers.stellar.org/docs"
            ),
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Habilita output verbose para debugging"),
    ] = False,
) -> None:
    """Fetch documentation and generate an llms.txt file for AI agents."""
    log_level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, show_path=verbose, rich_tracebacks=True)],
    )

    if provider not in ("gemini", "claude"):
        console.print(
            f"[bold red]Erro:[/] Provider inválido: '{provider}'. "
            "Use 'gemini' ou 'claude'."
        )
        raise typer.Exit(code=1)

    resolved_key = _resolve_api_key(provider, api_key)

    # -----------------------------------------------------------------------
    # Modo GitHub
    # -----------------------------------------------------------------------
    if github:
        resolved_github_token = _resolve_github_token(github_token)

        console.print(f"\n[bold]🐙 GitHub mode:[/] [cyan]{url}[/cyan]")
        if docs_base_url:
            console.print(f"   [dim]Links apontarão para:[/dim] [cyan]{docs_base_url}[/cyan]")
        console.print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=30),
            TaskProgressColumn(),
            TextColumn("[dim]{task.fields[filename]}"),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("Coletando arquivos...", total=max_pages, filename="")

            def on_progress(count: int, name: str) -> None:
                progress.update(task, completed=count, filename=name)

            pages = crawl_github(
                url,
                resolved_github_token,
                max_pages=max_pages,
                docs_base_url=docs_base_url,
                on_progress=on_progress,
            )
            progress.update(task, completed=len(pages), filename="")

        if not pages:
            console.print(
                "\n[bold yellow]Aviso:[/] Nenhum arquivo .md/.mdx encontrado no repositório.\n"
                "  Verifique se a URL aponta para um repositório GitHub válido e se o\n"
                "  GITHUB_TOKEN tem permissão de leitura. Rode [bold]prumo init[/bold] para reconfigurar."
            )
            raise typer.Exit(code=1)

        console.print(f"\n  ✅ {len(pages)} arquivos encontrados\n")

    # -----------------------------------------------------------------------
    # Modo HTTP estático (padrão)
    # -----------------------------------------------------------------------
    else:
        console.print(f"\n[bold]🔍 Validating URL:[/] {url}")
        _validate_url(url)

        console.print(f"[bold]🕷️  Crawling [cyan]{url}[/cyan]...[/]")
        pages = crawl(url, max_pages=max_pages)

        if not pages:
            console.print(
                "\n[bold yellow]Aviso:[/] Nenhuma página encontrada.\n"
                "  [dim]Dica: se o site usa JavaScript para renderizar o conteúdo "
                "(Docusaurus, VitePress, Next.js), use a flag [bold]--github[/bold] "
                "com a URL do repositório da documentação.[/dim]"
            )
            raise typer.Exit(code=1)

        console.print(f"  ✅ {len(pages)} pages found\n")

    # -----------------------------------------------------------------------
    # Export — igual nos dois modos
    # -----------------------------------------------------------------------
    console.print(f"[bold]📝 Exporting to llms.txt via [cyan]{provider}[/cyan]...[/]")
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