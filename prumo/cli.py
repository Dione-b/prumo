"""Prumo CLI — entry point that orchestrates crawler and exporter.

Only module that does disk IO. Validates inputs, shows progress
with Rich and resolves API keys.

Available commands:
  prumo init   → interactive wizard that creates .env with required credentials
  prumo fetch  → crawls documentation and generates llms.txt

Fetch operation modes:
  - Standard: static HTTP crawling (httpx + BeautifulSoup)
  - --github: reads via GitHub Contents API (.md/.mdx), bypasses JS-Wall

Credential resolution (priority order):
  1. CLI Flag        (--api-key, --github-token)
  2. .env file       (loaded automatically from current directory)
  3. Shell env var
  4. Error with clear instructions — run `prumo init` to configure
"""

from __future__ import annotations

import functools
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import httpx
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from prumo.crawler import Page, crawl, crawl_github
from prumo.exporter import export_llms_txt

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
# Credential resolution helpers
# ---------------------------------------------------------------------------


def _resolve_api_key(provider: str, api_key_flag: str | None) -> str:
    """Resolves the API key: CLI flag → env var → error."""
    if api_key_flag:
        return api_key_flag

    env_var = API_KEY_ENV_VARS.get(provider, "")
    if value := os.environ.get(env_var, ""):
        return value

    console.print(
        f"\n[bold red]Error:[/] API key not found for provider '[cyan]{provider}[/cyan]'.\n\n"
        f"  Quickly configure it by running:\n"
        f"    [bold green]prumo init[/bold green]\n\n"
        f"  Or manually add to [bold].env[/bold]:\n"
        f"    [green]{env_var}=your-key-here[/green]"
    )
    raise typer.Exit(code=1)


def _resolve_github_token(github_token_flag: str | None) -> str:
    """Resolves the GitHub token: CLI flag → GITHUB_TOKEN env → error."""
    if github_token_flag:
        return github_token_flag

    if value := os.environ.get("GITHUB_TOKEN", ""):
        return value

    console.print(
        "\n[bold red]Error:[/] GitHub token not found.\n\n"
        "  Quickly configure it by running:\n"
        "    [bold green]prumo init[/bold green]\n\n"
        "  Or manually add to [bold].env[/bold]:\n"
        "    [green]GITHUB_TOKEN=your-token-here[/green]"
    )
    raise typer.Exit(code=1)


def _validate_url(url: str) -> None:
    """Validates that the URL is accessible before crawling."""
    try:
        with httpx.Client(timeout=10) as client:
            response = client.head(url, follow_redirects=True)
            response.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        console.print(f"[bold red]Error:[/] URL inaccessible: {url}")
        console.print(f"  Detail: {exc}")
        raise typer.Exit(code=1) from exc


def _run_with_progress(
    description: str,
    total: int,
    crawl_fn: Callable[..., list[Page]],
) -> list[Page]:
    """Executes a crawl function displaying a Rich progress bar.

    Args:
        description: Text displayed on the progress bar.
        total: Maximum number of items (bar ceiling).
        crawl_fn: Partially applied crawl function — must accept
                  `on_progress` as the only pending argument.

    Returns:
        List of pages returned by the crawler.
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[filename]}"),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task(description, total=total, filename="")

        def on_progress(count: int, name: str) -> None:
            progress.update(task, completed=count, filename=name)

        pages = crawl_fn(on_progress=on_progress)
        progress.update(task, completed=len(pages), filename="")

    return pages


# ---------------------------------------------------------------------------
# Command: prumo init
# ---------------------------------------------------------------------------


@app.command()
def init(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrites the existing .env without prompting"),
    ] = False,
) -> None:
    """Configures Prumo credentials by interactively creating a .env file."""

    env_path = Path.cwd() / ".env"

    console.print()
    console.print(Panel(
        "[bold cyan]Prumo[/bold cyan] — Initial Setup\n\n"
        "This wizard will create a [bold].env[/bold] file with your credentials.\n"
        "Keys are stored [bold]locally[/bold] and never leave your machine.",
        expand=False,
    ))
    console.print()

    if env_path.exists() and not force:
        if not typer.confirm(
            f"  The .env file already exists at {env_path}. Do you want to overwrite it?",
            default=False,
        ):
            console.print(
                "\n[yellow]Operation cancelled.[/yellow] "
                "Use [bold]--force[/bold] to overwrite without confirmation.\n"
            )
            raise typer.Exit()
        console.print()

    lines: list[str] = ["# Prumo — credentials\n# Generated by `prumo init`\n"]
    step = 1

    # ------------------------------------------------------------------
    # LLM Provider
    # ------------------------------------------------------------------
    console.print(f"[bold]{step}. LLM Provider[/bold]")
    console.print("   Which provider do you want to use to generate the llms.txt?\n")
    step += 1

    provider_choice = typer.prompt(
        "   Provider",
        default="gemini",
        prompt_suffix=" [gemini/claude/both]: ",
        show_default=False,
    ).strip().lower()

    while provider_choice not in ("gemini", "claude", "both"):
        console.print("   [red]Invalid option.[/red] Type gemini, claude or both.")
        provider_choice = typer.prompt(
            "   Provider",
            default="gemini",
            prompt_suffix=" [gemini/claude/both]: ",
            show_default=False,
        ).strip().lower()

    console.print()

    if provider_choice in ("gemini", "both"):
        console.print(f"[bold]{step}. Gemini API Key[/bold]")
        console.print("   Get it from: [link]https://aistudio.google.com/app/apikey[/link]\n")
        gemini_key = typer.prompt("   GEMINI_API_KEY", hide_input=True).strip()
        lines.append(f"\n# Google Gemini\nGEMINI_API_KEY={gemini_key}")
        step += 1
        console.print()

    if provider_choice in ("claude", "both"):
        console.print(f"[bold]{step}. Anthropic API Key[/bold]")
        console.print("   Get it from: [link]https://console.anthropic.com/settings/keys[/link]\n")
        anthropic_key = typer.prompt("   ANTHROPIC_API_KEY", hide_input=True).strip()
        lines.append(f"\n# Anthropic Claude\nANTHROPIC_API_KEY={anthropic_key}")
        step += 1
        console.print()

    # ------------------------------------------------------------------
    # GitHub Token (optional)
    # ------------------------------------------------------------------
    console.print(
        f"[bold]{step}. GitHub Token[/bold] "
        "[dim](optional — only required for --github)[/dim]"
    )
    console.print("   Used to read .md/.mdx directly from the GitHub repository.")
    console.print(
        "   Get it from: [link]https://github.com/settings/tokens[/link] "
        "(scope: repo or public_repo)\n"
    )

    if typer.confirm("   Do you want to configure the GitHub token now?", default=True):
        console.print()
        github_token = typer.prompt("   GITHUB_TOKEN", hide_input=True).strip()
        lines.append(f"\n# GitHub (required for --github)\nGITHUB_TOKEN={github_token}")

    console.print()
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    console.print(Panel(
        f"[bold green]✅ .env successfully created![/bold green]\n\n"
        f"  Location: [cyan]{env_path}[/cyan]\n\n"
        f"  Next step:\n"
        f"    [bold]prumo fetch <docs-url>[/bold]\n\n"
        f"  With GitHub mode:\n"
        f"    [bold]prumo fetch <repo-url> --github[/bold]",
        expand=False,
    ))
    console.print()


# ---------------------------------------------------------------------------
# Command: prumo fetch
# ---------------------------------------------------------------------------


@app.command()
def fetch(
    url: Annotated[str, typer.Argument(help="Documentation URL or GitHub repository")],
    output: Annotated[
        str, typer.Option("--output", "-o", help="Output directory")
    ] = "./output",
    provider: Annotated[
        str,
        typer.Option("--provider", "-p", help="LLM provider: gemini or claude"),
    ] = "gemini",
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", "-k", help="LLM provider API key"),
    ] = None,
    max_pages: Annotated[
        int,
        typer.Option("--max-pages", "-m", help="Maximum pages/files to process"),
    ] = 50,
    github: Annotated[
        bool,
        typer.Option(
            "--github",
            help=(
                "Uses the GitHub Contents API to read .md/.mdx from the repository. "
                "Ideal for sites with JS-Wall (Docusaurus, VitePress, Next.js). "
                "Requires GITHUB_TOKEN or --github-token."
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
            "--docs-base-url", "-d",
            help=(
                "Base URL of the published documentation. When provided, links in "
                "the llms.txt will point to the docs site instead of the GitHub source. "
                "Example: --docs-base-url https://developers.stellar.org/docs"
            ),
        ),
    ] = None,
) -> None:
    """Fetch documentation and generate an llms.txt file for AI agents."""
    if provider not in ("gemini", "claude"):
        console.print(
            f"[bold red]Error:[/] Invalid provider: '{provider}'. Use 'gemini' or 'claude'."
        )
        raise typer.Exit(code=1)

    resolved_key = _resolve_api_key(provider, api_key)

    # -----------------------------------------------------------------------
    # GitHub Mode
    # -----------------------------------------------------------------------
    if github:
        resolved_github_token = _resolve_github_token(github_token)

        console.print(f"\n[bold]🐙 GitHub mode:[/] [cyan]{url}[/cyan]")
        if docs_base_url:
            console.print(f"   [dim]Links will point to:[/dim] [cyan]{docs_base_url}[/cyan]")
        console.print()

        pages = _run_with_progress(
            "Collecting files...",
            max_pages,
            functools.partial(
                crawl_github,
                url,
                resolved_github_token,
                max_pages=max_pages,
                docs_base_url=docs_base_url,
            ),
        )

        if not pages:
            console.print(
                "\n[bold yellow]Warning:[/] No .md/.mdx files found in the repository.\n"
                "  Verify that the URL points to a valid GitHub repository and that the\n"
                "  GITHUB_TOKEN has read permission. Run [bold]prumo init[/bold] to reconfigure."
            )
            raise typer.Exit(code=1)

        console.print(f"\n  ✅ {len(pages)} files found\n")

    # -----------------------------------------------------------------------
    # Static HTTP Mode (default)
    # -----------------------------------------------------------------------
    else:
        console.print(f"\n[bold]🔍 Validating URL:[/] {url}")
        _validate_url(url)
        console.print(f"[bold]🕷️  Crawling [cyan]{url}[/cyan]...[/]\n")

        pages = _run_with_progress(
            "Crawling pages...",
            max_pages,
            functools.partial(crawl, url, max_pages=max_pages),
        )

        if not pages:
            console.print(
                "\n[bold yellow]Warning:[/] No pages found.\n"
                "  [dim]Tip: if the site uses JavaScript to render content "
                "(Docusaurus, VitePress, Next.js), use the [bold]--github[/bold] flag "
                "with the documentation repository URL.[/dim]"
            )
            raise typer.Exit(code=1)

        console.print(f"\n  ✅ {len(pages)} pages processed\n")

    # -----------------------------------------------------------------------
    # Export — same for both modes
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