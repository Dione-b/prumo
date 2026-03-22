"""Crawler HTTP para sites de documentação.

Descobre links a partir de uma URL raiz, faz scraping do conteúdo
e retorna uma lista de páginas limpas (sem HTML de navegação).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
MAX_RETRIES = 2
REMOVABLE_TAGS = ("nav", "footer", "aside", "script", "style", "header")


@dataclass
class Page:
    """Página de documentação com conteúdo limpo."""

    title: str
    url: str
    content: str


def _is_same_docs_scope(candidate: str, root: str) -> bool:
    """Verifica se a URL candidata pertence ao mesmo domínio e prefixo de path."""
    parsed_candidate = urlparse(candidate)
    parsed_root = urlparse(root)

    if parsed_candidate.netloc != parsed_root.netloc:
        return False

    return parsed_candidate.path.startswith(parsed_root.path)


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extrai links absolutos de uma página HTML."""
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        absolute = urljoin(base_url, href)
        # Remove fragmentos e query strings para evitar duplicatas
        parsed = urlparse(absolute)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        # Apenas links HTTP(S)
        if parsed.scheme in ("http", "https"):
            links.append(clean_url)
    return links


def _clean_html(soup: BeautifulSoup) -> str:
    """Remove tags de navegação e retorna texto limpo."""
    for tag_name in REMOVABLE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Prefere <main>, fallback para <body>
    main = soup.find("main")
    container = main if main else soup.find("body")
    if container is None:
        return soup.get_text(separator="\n", strip=True)

    return container.get_text(separator="\n", strip=True)


def _extract_title(soup: BeautifulSoup) -> str:
    """Extrai título da página: <title> ou primeiro <h1>."""
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(strip=True)

    h1_tag = soup.find("h1")
    if h1_tag and h1_tag.get_text(strip=True):
        return h1_tag.get_text(strip=True)

    return "Untitled"


def _fetch_page(client: httpx.Client, url: str) -> str | None:
    """Faz GET com retries. Retorna HTML ou None em caso de falha."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.get(url, follow_redirects=True)
            response.raise_for_status()
            return response.text
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.debug(
                "Tentativa %d/%d falhou para %s: %s",
                attempt + 1,
                MAX_RETRIES + 1,
                url,
                exc,
            )
    logger.warning("Falha ao acessar %s após %d tentativas", url, MAX_RETRIES + 1)
    return None


def crawl(root_url: str, max_pages: int = 50) -> list[Page]:
    """Crawlea um site de documentação a partir da URL raiz.

    Args:
        root_url: URL raiz do site de documentação.
        max_pages: Número máximo de páginas a crawlear.

    Returns:
        Lista de páginas com título, URL e conteúdo limpo.
    """
    visited: set[str] = set()
    pages: list[Page] = []
    queue: list[str] = [root_url]

    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        while queue and len(pages) < max_pages:
            url = queue.pop(0)

            if url in visited:
                continue
            visited.add(url)

            html = _fetch_page(client, url)
            if html is None:
                continue

            soup = BeautifulSoup(html, "html.parser")

            # Descobrir novos links antes de limpar o HTML
            for link in _extract_links(soup, url):
                if link not in visited and _is_same_docs_scope(link, root_url):
                    queue.append(link)

            title = _extract_title(soup)
            content = _clean_html(soup)

            if not content.strip():
                logger.debug("Página sem conteúdo, ignorando: %s", url)
                continue

            pages.append(Page(title=title, url=url, content=content))
            logger.info(
                "Crawled %d/%d: %s", len(pages), max_pages, title
            )

    return pages
