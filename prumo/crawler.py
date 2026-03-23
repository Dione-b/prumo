"""Crawler para sites de documentação.

Dois modos de operação:
- crawl()        → HTTP estático (httpx + BeautifulSoup), para sites que servem HTML puro.
- crawl_github() → GitHub Contents API, para repositórios com docs em .md / .mdx.
                   Contorna o JS-Wall de sites como Docusaurus, VitePress, etc.

Inteligência do modo GitHub:
- Ignora automaticamente diretórios de configuração/infraestrutura.
- Detecta o diretório de documentação quando o usuário passa apenas a raiz do repo.
- Prioriza arquivos com mais conteúdo textual real antes de passar ao exporter.
- Fallback automático para fetch individual quando o campo `content` vem vazio
  na listagem de diretório (comportamento normal da GitHub API em diretórios grandes).
- Transforma URLs do GitHub para a URL da docs publicada quando --docs-base-url
  é fornecido.

Ambos retornam List[Page] — interface idêntica para o exporter.
"""

from __future__ import annotations

import base64
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
MAX_RETRIES = 2
REMOVABLE_TAGS = ("nav", "footer", "aside", "script", "style", "header")

GITHUB_MD_EXTENSIONS = (".md", ".mdx")

GITHUB_IGNORED_FILENAMES = frozenset({
    "changelog", "changes", "release-notes", "releases",
    "license", "licence", "contributing", "code-of-conduct",
    "security", "crowdin", "readme",
})

GITHUB_IGNORED_DIRS = frozenset({
    ".github", ".husky", ".devcontainer", ".vscode",
    "node_modules", ".next", ".nuxt", "dist", "build", "out", ".cache",
    "src", "lib", "bin", "scripts", "patches",
    "nginx", "docker", "k8s", "helm", "terraform",
    "static", "public", "assets", "images", "img", "readme-imgs",
    "i18n", "locales",
    "openapi", "openrpc",
    "meeting-notes", "config",
})

DOCS_DIR_CANDIDATES = (
    "docs", "documentation", "doc", "content",
    "pages", "guide", "guides", "wiki",
    "knowledge", "manual", "handbook", "reference",
)


@dataclass
class Page:
    """Página de documentação com conteúdo limpo."""

    title: str
    url: str
    content: str


# ---------------------------------------------------------------------------
# Modo HTTP — crawling estático
# ---------------------------------------------------------------------------


def _is_same_docs_scope(candidate: str, root: str) -> bool:
    parsed_candidate = urlparse(candidate)
    parsed_root = urlparse(root)
    if parsed_candidate.netloc != parsed_root.netloc:
        return False
    return parsed_candidate.path.startswith(parsed_root.path)


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.scheme in ("http", "https"):
            links.append(clean_url)
    return links


def _clean_html(soup: BeautifulSoup) -> str:
    for tag_name in REMOVABLE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    main = soup.find("main")
    container = main if main else soup.find("body")
    if container is None:
        return soup.get_text(separator="\n", strip=True)
    return container.get_text(separator="\n", strip=True)


def _extract_title(soup: BeautifulSoup) -> str:
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(strip=True)
    h1_tag = soup.find("h1")
    if h1_tag and h1_tag.get_text(strip=True):
        return h1_tag.get_text(strip=True)
    return "Untitled"


def _fetch_page(client: httpx.Client, url: str) -> str | None:
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.get(url, follow_redirects=True)
            response.raise_for_status()
            return response.text
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.debug("Tentativa %d/%d falhou para %s: %s",
                         attempt + 1, MAX_RETRIES + 1, url, exc)
    logger.warning("Falha ao acessar %s após %d tentativas", url, MAX_RETRIES + 1)
    return None


def crawl(root_url: str, max_pages: int = 50) -> list[Page]:
    """Crawlea um site de documentação estático a partir da URL raiz."""
    visited: set[str] = set()
    pages: list[Page] = []
    queue: list[str] = [root_url]

    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        while queue and len(pages) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            logger.debug("Fetching: %s", url)
            html = _fetch_page(client, url)
            if html is None:
                continue

            soup = BeautifulSoup(html, "html.parser")
            for link in _extract_links(soup, url):
                if link not in visited and _is_same_docs_scope(link, root_url):
                    queue.append(link)

            title = _extract_title(soup)
            content = _clean_html(soup)

            if not content.strip():
                logger.debug("Página sem conteúdo, ignorando: %s", url)
                continue

            pages.append(Page(title=title, url=url, content=content))
            logger.info("Crawled %d/%d: %s", len(pages), max_pages, title)

    return pages


# ---------------------------------------------------------------------------
# Modo GitHub — leitura via Contents API
# ---------------------------------------------------------------------------


def _parse_github_url(url: str) -> tuple[str, str, str]:
    """Extrai owner, repo e subpath de uma URL do GitHub."""
    parsed = urlparse(url)
    if parsed.netloc not in ("github.com", "www.github.com"):
        raise ValueError(f"URL não é do GitHub: {url}")

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"URL GitHub inválida (esperado owner/repo): {url}")

    owner = parts[0]
    repo = parts[1]
    subpath = ""
    if len(parts) > 4 and parts[2] == "tree":
        subpath = "/".join(parts[4:])

    return owner, repo, subpath


def _is_ignored_dir(name: str) -> bool:
    return name.lower() in GITHUB_IGNORED_DIRS


def _is_ignored_file(filename: str) -> bool:
    stem = filename.lower().removesuffix(".md").removesuffix(".mdx")
    return stem in GITHUB_IGNORED_FILENAMES


def _decode_base64_content(encoded: str, name: str) -> str | None:
    try:
        return base64.b64decode(encoded.replace("\n", "")).decode("utf-8")
    except Exception as exc:
        logger.warning("Falha ao decodificar %s: %s", name, exc)
        return None


def _fetch_file_individually(
    client: httpx.Client,
    api_url: str,
    headers: dict[str, str],
    name: str,
) -> str | None:
    """Fetch individual de um arquivo quando o conteúdo não vem na listagem.

    A GitHub Contents API omite o campo `content` quando a resposta de um
    diretório ficaria muito grande. Nesse caso fazemos uma request direta
    ao endpoint do arquivo.
    """
    logger.debug("Fallback fetch individual: %s", api_url)
    try:
        response = client.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        encoded = data.get("content", "")
        if not encoded:
            logger.debug("Conteúdo ausente mesmo no fetch individual: %s", name)
            return None
        return _decode_base64_content(encoded, name)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("Falha no fetch individual de %s: %s", name, exc)
        return None


def _transform_to_docs_url(
    html_url: str,
    subpath: str,
    docs_base_url: str,
) -> str:
    """Transforma uma URL de blob do GitHub para a URL da documentação publicada.

    Extrai o path relativo do arquivo dentro do subdiretório de docs e
    o combina com a URL base da documentação publicada.

    Exemplo:
        html_url:      https://github.com/stellar/stellar-docs/blob/main/docs/build/setup.mdx
        subpath:       docs
        docs_base_url: https://developers.stellar.org/docs
        resultado:     https://developers.stellar.org/docs/build/setup

    Args:
        html_url: URL do arquivo no GitHub (formato blob/main/...).
        subpath: Subdiretório do repo que foi varrido (ex: "docs").
        docs_base_url: URL base da documentação publicada sem trailing slash.

    Returns:
        URL da página na documentação publicada, sem extensão de arquivo.
    """
    # Extrai o path após blob/main/ (ou blob/master/ etc.)
    # Ex: "docs/build/setup.mdx"
    match = re.search(r"/blob/[^/]+/(.+)$", html_url)
    if not match:
        return html_url

    file_path = match.group(1)  # "docs/build/setup.mdx"

    # Remove o prefixo do subpath varrido
    # Ex: subpath="docs" → remove "docs/" → "build/setup.mdx"
    if subpath:
        prefix = subpath.rstrip("/") + "/"
        if file_path.startswith(prefix):
            file_path = file_path[len(prefix):]

    # Remove extensão .md ou .mdx
    for ext in (".mdx", ".md"):
        if file_path.endswith(ext):
            file_path = file_path[: -len(ext)]
            break

    return f"{docs_base_url.rstrip('/')}/{file_path}"


def _detect_docs_subpath(
    client: httpx.Client,
    owner: str,
    repo: str,
    headers: dict[str, str],
) -> str:
    """Inspeciona o primeiro nível do repo e detecta o diretório de documentação."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/"
    logger.debug("Auto-detecção: inspecionando raiz do repo")

    try:
        response = client.get(api_url, headers=headers)
        response.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("Falha na auto-detecção: %s", exc)
        return ""

    items = response.json()
    if not isinstance(items, list):
        return ""

    dir_names = {item["name"].lower() for item in items if item.get("type") == "dir"}

    for candidate in DOCS_DIR_CANDIDATES:
        if candidate in dir_names:
            logger.info("Auto-detecção: diretório '%s' encontrado", candidate)
            return candidate

    logger.debug("Auto-detecção: nenhum candidato encontrado, varrendo raiz")
    return ""


def _score_markdown_content(raw: str) -> int:
    """Calcula o volume de texto narrativo real de um arquivo Markdown."""
    text = raw
    text = re.sub(r"^---[\s\S]*?---\s*", "", text, count=1)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"^(import|export)\s+.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"<[A-Z][^>]*/>", "", text)
    text = re.sub(r"<[A-Z][^>]*>[\s\S]*?</[A-Z][^>]*>", "", text)
    text = re.sub(r"!?\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"^[#\-=*_>|` ]+$", "", text, flags=re.MULTILINE)
    return len(text.strip())


def _extract_title_from_markdown(content: str, filename: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("# ").strip()
    return filename.removesuffix(".mdx").removesuffix(".md").replace("-", " ").title()


@dataclass
class _GitHubFile:
    name: str
    html_url: str
    content: str
    text_score: int = 0


def _list_github_files(
    client: httpx.Client,
    owner: str,
    repo: str,
    path: str,
    headers: dict[str, str],
    max_files: int,
    collected: list[_GitHubFile],
    on_progress: Callable[[int, str], None] | None = None,
) -> None:
    """Lista recursivamente arquivos .md/.mdx e coleta o conteúdo.

    Estratégia de coleta (em ordem de preferência):
    1. Decodifica o campo `content` base64 inline na listagem.
    2. Se `content` estiver vazio, faz fetch individual via `item["url"]`.
    """
    if len(collected) >= max_files:
        return

    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    logger.debug("GitHub API: listando %s", api_url)

    try:
        response = client.get(api_url, headers=headers)
        response.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("Falha ao listar %s: %s", api_url, exc)
        return

    items = response.json()
    if not isinstance(items, list):
        return

    for item in items:
        if len(collected) >= max_files:
            break

        item_type = item.get("type", "")
        name: str = item.get("name", "")

        if item_type == "dir":
            if _is_ignored_dir(name):
                logger.debug("Diretório ignorado: %s", name)
                continue
            _list_github_files(
                client, owner, repo, item["path"],
                headers, max_files, collected, on_progress,
            )

        elif item_type == "file":
            if not any(name.lower().endswith(ext) for ext in GITHUB_MD_EXTENSIONS):
                continue
            if _is_ignored_file(name):
                continue

            # Tentativa 1: conteúdo inline na listagem
            encoded: str = item.get("content", "")
            if encoded:
                decoded = _decode_base64_content(encoded, name)
            else:
                # Tentativa 2: fetch individual
                logger.debug("content vazio, fazendo fetch individual: %s", name)
                decoded = _fetch_file_individually(
                    client, item["url"], headers, name
                )

            if not decoded or not decoded.strip():
                logger.debug("Arquivo sem conteúdo: %s", name)
                continue

            score = _score_markdown_content(decoded)
            collected.append(_GitHubFile(
                name=name,
                html_url=item.get("html_url", ""),
                content=decoded,
                text_score=score,
            ))
            logger.debug("Coletado: %s (score=%d)", name, score)

            if on_progress is not None:
                on_progress(len(collected), name)


def crawl_github(
    repo_url: str,
    github_token: str,
    max_pages: int = 50,
    docs_base_url: str | None = None,
    on_progress: Callable[[int, str], None] | None = None,
) -> list[Page]:
    """Lê arquivos .md/.mdx de um repositório GitHub via Contents API.

    Args:
        repo_url: URL do repo ou subdiretório.
        github_token: Personal Access Token do GitHub.
        max_pages: Máximo de arquivos a processar.
        docs_base_url: URL base da documentação publicada (opcional).
                       Quando fornecida, os links no llms.txt apontarão para
                       a docs publicada em vez do código-fonte no GitHub.
                       Exemplo: "https://developers.stellar.org/docs"
        on_progress: Callback (total_coletado, nome_arquivo).

    Returns:
        Lista de páginas ordenadas por volume de conteúdo textual (decrescente).
    """
    try:
        owner, repo, subpath = _parse_github_url(repo_url)
    except ValueError as exc:
        logger.error("URL GitHub inválida: %s", exc)
        return []

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    collected: list[_GitHubFile] = []

    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        if not subpath:
            detected = _detect_docs_subpath(client, owner, repo, headers)
            if detected:
                subpath = detected

        logger.debug("Varrendo: %s/%s/%s", owner, repo, subpath or "(raiz)")
        _list_github_files(
            client, owner, repo, subpath,
            headers, max_pages, collected, on_progress,
        )

    if not collected:
        logger.warning(
            "Nenhum arquivo .md/.mdx encontrado em %s/%s/%s",
            owner, repo, subpath or "(raiz)",
        )
        return []

    collected.sort(key=lambda f: f.text_score, reverse=True)
    logger.info("%d arquivos coletados, ordenados por conteúdo textual", len(collected))

    pages: list[Page] = []
    for i, file in enumerate(collected, start=1):
        title = _extract_title_from_markdown(file.content, file.name)

        # Transforma a URL do GitHub para a docs publicada, se fornecida
        if docs_base_url:
            url = _transform_to_docs_url(file.html_url, subpath, docs_base_url)
        else:
            url = file.html_url

        pages.append(Page(title=title, url=url, content=file.content))
        logger.info("Processado %d/%d: %s (score=%d)", i, len(collected), title, file.text_score)

    return pages