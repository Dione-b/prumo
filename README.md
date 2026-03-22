<p align="center">
  <h1 align="center">🪸 Prumo</h1>
  <p align="center">
    <strong>Turn any documentation site into an <code>llms.txt</code> file — ready to feed your AI coding agents.</strong>
  </p>
</p>

<p align="center">
  <a href="#the-problem">The Problem</a> •
  <a href="#how-it-works">How It Works</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a> •
  <a href="#limitations">Limitations</a>
</p>

---

## The Problem

AI models **hallucinate APIs** from new or obscure libraries because they were never trained on that documentation. When you ask an agent to use a recent library, it invents function names, parameters, and behaviors that don't exist.

## The Solution

Prumo scrapes a documentation site, cleans the HTML, and uses an LLM (Gemini or Claude) to condense everything into a **structured index** (`llms.txt`). That file can then be used as context by any AI coding agent.

## How It Works

```
Documentation URL
        │
        ▼
  ┌───────────┐     ┌───────────┐     ┌───────────┐
  │  Crawler   │ ──▸ │  Exporter  │ ──▸ │  llms.txt  │
  │ (httpx +   │     │ (Gemini /  │     │ (structured│
  │  BS4)      │     │  Claude)   │     │  Markdown)  │
  └───────────┘     └───────────┘     └───────────┘
```

1. **Crawler** — navigates the site, follows internal links, and extracts the text from each page
2. **Exporter** — sends the content to an LLM, which generates a summary organized into sections
3. **CLI** — saves the result as `llms.txt` in the output directory

## Installation

```bash
pip install prumo
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add prumo
```

## Usage

```bash
prumo fetch https://docs.somelib.com --output ./somelib-docs/
# generates: ./somelib-docs/llms.txt
```

### Options

| Option | Default | Description |
|---|---|---|
| `url` | required | Root URL of the documentation site |
| `--output`, `-o` | `./output` | Output directory |
| `--provider`, `-p` | `gemini` | LLM provider: `gemini` or `claude` |
| `--api-key`, `-k` | env var | API key (see below) |
| `--max-pages`, `-m` | `50` | Maximum number of pages to crawl |

### Setting up your API Key

Prumo requires an API key from your chosen LLM provider. You can set it via **environment variable** (recommended) or via **flag**:

```bash
# Gemini (default)
export GEMINI_API_KEY=your-key-here
prumo fetch https://docs.example.com

# Claude
export ANTHROPIC_API_KEY=your-key-here
prumo fetch https://docs.example.com --provider claude

# Or pass it directly
prumo fetch https://docs.example.com --api-key your-key-here
```

### Example Output

The generated `llms.txt` follows this format:

```markdown
# FastAPI

> Modern, fast web framework for building APIs with Python.

## Getting Started
- [Installation](https://fastapi.tiangolo.com/tutorial/): How to install and create the first endpoint.
- [First Steps](https://fastapi.tiangolo.com/tutorial/first-steps/): Basic structure of a FastAPI application.

## Request Handling
- [Path Parameters](https://fastapi.tiangolo.com/tutorial/path-params/): Dynamic URL parameters with automatic type validation.
```

## Limitations

| Limitation | Detail |
|---|---|
| 🚫 JavaScript-rendered sites | Sites that require JS to render return partial or empty content |
| 📄 Large documentation | Capped at `--max-pages` pages |
| 🤖 Output quality | Depends on the LLM and the HTML structure of the source site |

## Development

```bash
git clone https://github.com/Dione-b/prumo.git
cd prumo
uv sync

# Lint + type check + tests
uv run ruff check .
uv run mypy prumo/
uv run pytest tests/ -v
```

## License

MIT
