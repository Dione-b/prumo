from __future__ import annotations

import asyncio
from typing import Literal, TypedDict
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import structlog
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)

DOCS_ROOT = "https://developers.stellar.org/docs"
ROBOTS_URL = "https://developers.stellar.org/robots.txt"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com"
REQUEST_TIMEOUT_SECONDS = 30.0
REQUEST_DELAY_SECONDS = 1.0
USER_AGENT = "prumo-stellar-crawler/0.1"
# Fontes GitHub oficiais (org stellar): core, docs em MD/MDX, exemplos x402.
# Ver https://github.com/stellar/stellar-core , x402-stellar , stellar-docs
GITHUB_REPOS: tuple[tuple[str, str], ...] = (
    ("stellar", "stellar-core"),
    ("stellar", "x402-stellar"),
    ("stellar", "stellar-docs"),
)
SKIP_GITHUB_TOKENS = (
    "changelog",
    "release-notes",
    "releases",
    "changes",
    "news",
)


class CrawledDocument(TypedDict):
    title: str
    content: str
    source_url: str
    source_type: Literal["docs", "github"]


def _normalize_docs_url(url: str) -> str:
    normalized, _ = urldefrag(url)
    return normalized.rstrip("/")


def _is_docs_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.netloc == "developers.stellar.org"
        and parsed.path.startswith("/docs")
    )


def _extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    container = soup.find("main") or soup.find("article") or soup.body
    if container is None:
        return ""

    for element in container.find_all(["script", "style", "noscript"]):
        element.decompose()

    text = container.get_text("\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _extract_title_from_html(html: str, fallback_url: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        return soup.title.string.strip()

    path = urlparse(fallback_url).path.rstrip("/")
    if not path:
        return fallback_url
    return path.split("/")[-1].replace("-", " ").title()


async def _load_robot_parser(client: httpx.AsyncClient) -> RobotFileParser:
    response = await client.get(ROBOTS_URL)
    response.raise_for_status()
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    reraise=True,
)
async def _fetch_text(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url)
    response.raise_for_status()
    return response.text


def _github_headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }


def _http_headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT}


def _should_skip_github_path(path: str) -> bool:
    normalized = path.lower()
    if not (normalized.endswith(".md") or normalized.endswith(".mdx")):
        return True
    return any(token in normalized for token in SKIP_GITHUB_TOKENS)


async def crawl_stellar_docs() -> list[CrawledDocument]:
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers=_http_headers(),
        follow_redirects=True,
    ) as client:
        robot_parser = await _load_robot_parser(client)
        landing_html = await _fetch_text(client, DOCS_ROOT)
        landing_soup = BeautifulSoup(landing_html, "lxml")

        urls: set[str] = set()
        for anchor in landing_soup.find_all("a", href=True):
            href = anchor.get("href")
            if not isinstance(href, str):
                continue
            absolute_url = urljoin(DOCS_ROOT, href)
            if _is_docs_url(absolute_url):
                urls.add(_normalize_docs_url(absolute_url))
        urls.add(_normalize_docs_url(DOCS_ROOT))

        documents: list[CrawledDocument] = []
        for url in sorted(urls):
            if not robot_parser.can_fetch(USER_AGENT, url):
                logger.info("stellar_docs_url_skipped_by_robots", url=url)
                continue

            await asyncio.sleep(REQUEST_DELAY_SECONDS)
            try:
                html = await _fetch_text(client, url)
                content = _extract_text_from_html(html)
                if not content:
                    logger.warning("stellar_docs_empty_content", url=url)
                    continue
                documents.append(
                    CrawledDocument(
                        title=_extract_title_from_html(html, url),
                        content=content,
                        source_url=url,
                        source_type="docs",
                    )
                )
            except Exception as exc:
                logger.warning(
                    "stellar_docs_crawl_failed",
                    url=url,
                    error=str(exc),
                )
                continue

        return documents


async def crawl_stellar_github_repos() -> list[CrawledDocument]:
    documents: list[CrawledDocument] = []
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers=_github_headers(),
        follow_redirects=True,
    ) as client:
        for owner, repo in GITHUB_REPOS:
            try:
                repo_response = await client.get(
                    f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
                )
                repo_response.raise_for_status()
                repo_data = repo_response.json()
                default_branch = repo_data["default_branch"]

                tree_response = await client.get(
                    f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{default_branch}",
                    params={"recursive": "1"},
                )
                tree_response.raise_for_status()
                tree_data = tree_response.json()
            except Exception as exc:
                logger.warning(
                    "stellar_github_repo_failed",
                    repo=f"{owner}/{repo}",
                    error=str(exc),
                )
                continue

            for item in tree_data.get("tree", []):
                path = item.get("path", "")
                if item.get("type") != "blob" or _should_skip_github_path(path):
                    continue

                raw_url = f"{GITHUB_RAW_BASE}/{owner}/{repo}/{default_branch}/{path}"
                await asyncio.sleep(REQUEST_DELAY_SECONDS)
                try:
                    content = await _fetch_text(client, raw_url)
                    if not content.strip():
                        continue
                    documents.append(
                        CrawledDocument(
                            title=f"{repo}/{path}",
                            content=content,
                            source_url=raw_url,
                            source_type="github",
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "stellar_github_file_failed",
                        repo=f"{owner}/{repo}",
                        path=path,
                        error=str(exc),
                    )
                    continue

    return documents
