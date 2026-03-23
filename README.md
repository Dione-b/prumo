<p align="center">
  <h1 align="center">🪸 Prumo</h1>
  <p align="center">
    Convert any documentation site into an <code>llms.txt</code> file —<br>
    structured context ready for AI coding agents.
  </p>
  <p align="center">
    <a href="https://pypi.org/project/prumo"><img alt="PyPI" src="https://img.shields.io/pypi/v/prumo?color=0ea5e9&labelColor=1e293b"></a>
    <a href="https://pypi.org/project/prumo"><img alt="Python" src="https://img.shields.io/pypi/pyversions/prumo?color=0ea5e9&labelColor=1e293b"></a>
    <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-0ea5e9?labelColor=1e293b"></a>
    <a href="https://github.com/Dione-b/prumo/actions"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/Dione-b/prumo/ci.yml?label=CI&color=0ea5e9&labelColor=1e293b"></a>
  </p>
</p>

---

## The Problem

AI models hallucinate APIs from new or obscure libraries because they were never trained on that documentation. When you ask a coding agent to use a recent SDK, it invents function names, parameters, and behaviors that do not exist.

Prumo solves this by turning live documentation into a compact, structured `llms.txt` file that you can drop into any agent's context window.

## How It Works

```
URL or GitHub repo
        │
        ▼
  ┌─────────────┐     ┌──────────────┐     ┌────────────┐
  │   Crawler    │────▶│   Exporter   │────▶│  llms.txt  │
  │ (httpx  or  │     │ (Gemini  or  │     │ (Markdown) │
  │  GitHub API)│     │   Claude)    │     │            │
  └─────────────┘     └──────────────┘     └────────────┘
```

**Crawler** operates in two modes:

- **Default** — navigates static HTML, follows internal links, strips navigation noise.
- **GitHub mode** (`--github`) — reads `.md`/`.mdx` files directly from a repository via the GitHub API. Bypasses JavaScript-rendered sites (Docusaurus, VitePress, Next.js).

**Exporter** sends the cleaned content to an LLM, which generates a `llms.txt` organized into logical sections with one-line descriptions per page.

## Installation

Prumo is a CLI tool. The recommended way to install it is with [pipx](https://pipx.pypa.io), which installs it in an isolated environment and makes it globally available in your terminal:

```bash
pipx install prumo
```

> **Don't have pipx?** Install it first:
>
> ```bash
> # macOS
> brew install pipx && pipx ensurepath
>
> # Ubuntu / Debian
> sudo apt install pipx && pipx ensurepath
>
> # Windows
> scoop install pipx
> ```

**Alternative — pip inside a virtual environment:**

```bash
pip install prumo
```

**Alternative — uv:**

```bash
uv tool install prumo
```

## Quick Start

### 1. Configure credentials

```bash
prumo init
```

The wizard will ask for your Gemini or Claude API key, and optionally a GitHub token for `--github` mode.

### 2. Fetch documentation

```bash
# Standard mode — static HTML
prumo fetch https://docs.example.com

# GitHub mode — reads .md/.mdx directly from the repository
prumo fetch https://github.com/some/repo --github

# Remap GitHub blob links to the published documentation URLs
prumo fetch https://github.com/stellar/stellar-docs \
  --github \
  --docs-base-url https://developers.stellar.org/docs
```

The result is written to `./output/llms.txt` by default.

## Output Format

Prumo generates a `llms.txt` following the [llmstxt.org](https://llmstxt.org) standard:

```markdown
# FastAPI

> Modern, fast web framework for building APIs with Python.

## Getting Started

- [Installation](https://fastapi.tiangolo.com/tutorial/): How to install and create the first endpoint.
- [First Steps](https://fastapi.tiangolo.com/tutorial/first-steps/): Basic structure of a FastAPI application.

## Request Handling

- [Path Parameters](https://fastapi.tiangolo.com/tutorial/path-params/): Dynamic URL parameters with automatic type validation.
```

## CLI Reference

### `prumo init`

Interactive wizard that creates a local `.env` file with your credentials.

```
Options:
  --force, -f    Overwrite an existing .env without prompting
```

### `prumo fetch <url>`

Crawls a documentation site and generates `llms.txt`.

| Option                  | Default    | Description                                            |
| ----------------------- | ---------- | ------------------------------------------------------ |
| `url`                   | required   | Root URL of the docs site or GitHub repository         |
| `--output`, `-o`        | `./output` | Output directory                                       |
| `--provider`, `-p`      | `gemini`   | LLM provider: `gemini` or `claude`                     |
| `--api-key`, `-k`       | env var    | LLM provider API key                                   |
| `--max-pages`, `-m`     | `50`       | Maximum pages or files to crawl                        |
| `--github`              | `false`    | Use the GitHub API to read `.md`/`.mdx` files directly |
| `--github-token`        | env var    | GitHub Personal Access Token                           |
| `--docs-base-url`, `-d` | —          | Remap GitHub blob links to the published docs URL      |

### Credential resolution order

For each secret, Prumo tries in this order and stops at the first match:

```
--api-key / --github-token flag  →  .env file  →  shell environment variable  →  error
```

## Limitations

|                            |                                                                                                                                                 |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **JS-rendered sites**      | Sites that require JavaScript to render will return empty content in standard mode. Use `--github` if the repository has Markdown source files. |
| **Large documentation**    | Crawling is capped at `--max-pages` to avoid bloated API calls. Increase it if the generated file feels incomplete.                             |
| **Output quality**         | Depends on the LLM provider and the structure of the source documentation. Gemini 2.5 Flash is the default and works well for most cases.       |
| **GitHub API rate limits** | Authenticated requests are limited to 5,000 per hour. A large repository with `--max-pages 200` can consume several hundred requests.           |

## Development

```bash
git clone https://github.com/Dione-b/prumo.git
cd prumo
uv sync
cp .env.example .env  # fill in your keys
```

```bash
uv run ruff check .
uv run mypy prumo/
uv run pytest tests/ -v
```

## Contributing

Contributions are welcome. Before opening a pull request:

1. Keep changes focused on a single concern.
2. Add or update tests for any behavior changes.
3. Make sure `ruff`, `mypy`, and `pytest` all pass locally.
4. Describe the motivation and user-facing impact in the PR description.

If you find a bug or want to propose a feature, [open an issue](https://github.com/Dione-b/prumo/issues) first.

## License

MIT — see [LICENSE](LICENSE) for details.
