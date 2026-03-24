"""Shared HTML parsing helpers for crawlers."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify as md

REMOVABLE_TAGS = ("nav", "footer", "aside", "script", "style", "header")


def is_same_docs_scope(candidate: str, root: str) -> bool:
    parsed_candidate = urlparse(candidate)
    parsed_root = urlparse(root)
    if parsed_candidate.netloc != parsed_root.netloc:
        return False
    return parsed_candidate.path.startswith(parsed_root.path)


def extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.scheme in ("http", "https"):
            links.append(clean_url)
    return links


def clean_html(soup: BeautifulSoup) -> str:
    for tag_name in REMOVABLE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    main = soup.find("main")
    container = main if main else soup.find("body")
    if container is None:
        container = soup
    return md(str(container), heading_style="ATX", strip=["img"]).strip()


def extract_title(soup: BeautifulSoup) -> str:
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(strip=True)
    h1_tag = soup.find("h1")
    if h1_tag and h1_tag.get_text(strip=True):
        return h1_tag.get_text(strip=True)
    return "Untitled"
