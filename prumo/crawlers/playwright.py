"""Playwright-based crawler for JavaScript-rendered documentation."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from prumo.crawlers._html import clean_html, extract_links, extract_title, is_same_docs_scope
from prumo.crawlers.base import Crawler
from prumo.errors import CrawlerError
from prumo.models import Page, ProgressCallback

logger = logging.getLogger(__name__)

PAGE_TIMEOUT_MS = 15_000
NAVIGATION_WAIT = "networkidle"


class PlaywrightCrawler(Crawler):
    """Crawler that executes page JavaScript in a headless browser."""

    def crawl(
        self,
        url: str,
        max_pages: int = 50,
        on_progress: ProgressCallback | None = None,
    ) -> list[Page]:
        try:
            from playwright.sync_api import Error as PlaywrightError  # type: ignore[import-not-found]
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise CrawlerError(
                "Playwright nao instalado. Rode:\n"
                "  pip install prumo[js]\n"
                "  playwright install chromium"
            ) from exc

        visited: set[str] = set()
        queue: list[str] = [url]
        pages: list[Page] = []

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(accept_downloads=False)
                page = context.new_page()

                try:
                    while queue and len(pages) < max_pages:
                        current_url = queue.pop(0)
                        if current_url in visited:
                            continue
                        visited.add(current_url)

                        try:
                            page.goto(
                                current_url,
                                wait_until=NAVIGATION_WAIT,
                                timeout=PAGE_TIMEOUT_MS,
                            )
                            rendered_html = page.content()
                        except PlaywrightError as exc:
                            logger.warning("Skipping URL due to JS navigation error: %s (%s)", current_url, exc)
                            continue

                        soup = BeautifulSoup(rendered_html, "html.parser")

                        # Collect links from rendered DOM first, fallback to soup extraction.
                        rendered_links = page.eval_on_selector_all(
                            "a[href]",
                            "elements => elements.map(a => a.href)",
                        )
                        candidate_links = [link for link in rendered_links if isinstance(link, str)]
                        candidate_links.extend(extract_links(soup, current_url))

                        for link in candidate_links:
                            parsed = urlparse(link)
                            cleaned = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                            if cleaned in visited:
                                continue
                            if is_same_docs_scope(cleaned, url):
                                queue.append(cleaned)

                        title = extract_title(soup)
                        content = clean_html(soup)
                        if not content.strip():
                            continue

                        pages.append(Page(title=title, url=current_url, content=content))
                        if on_progress:
                            on_progress(len(pages), title)
                finally:
                    browser.close()
        except PlaywrightError as exc:
            raise CrawlerError(
                "Falha ao iniciar navegador Playwright. Rode:\n"
                "  playwright install chromium"
            ) from exc

        return pages
