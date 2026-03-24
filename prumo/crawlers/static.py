"""Static HTML crawler implementation."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from prumo.crawlers._html import clean_html, extract_links, extract_title, is_same_docs_scope
from prumo.crawlers.base import Crawler
from prumo.models import Page, ProgressCallback

TIMEOUT_SECONDS = 10
MAX_RETRIES = 2


class StaticCrawler(Crawler):
    """Crawler for documentation sites that return rendered HTML."""

    def _fetch_page(self, client: httpx.Client, url: str) -> str | None:
        for _ in range(MAX_RETRIES + 1):
            try:
                response = client.get(url, follow_redirects=True)
                response.raise_for_status()
                return response.text
            except (httpx.HTTPError, httpx.TimeoutException):
                pass
        return None

    def crawl(
        self,
        url: str,
        max_pages: int = 50,
        on_progress: ProgressCallback | None = None,
    ) -> list[Page]:
        visited: set[str] = set()
        pages: list[Page] = []
        queue: list[str] = [url]

        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            while queue and len(pages) < max_pages:
                current_url = queue.pop(0)
                if current_url in visited:
                    continue
                visited.add(current_url)

                html = self._fetch_page(client, current_url)
                if html is None:
                    continue

                soup = BeautifulSoup(html, "html.parser")
                for link in extract_links(soup, current_url):
                    if link not in visited and is_same_docs_scope(link, url):
                        queue.append(link)

                title = extract_title(soup)
                content = clean_html(soup)
                if not content.strip():
                    continue

                pages.append(Page(title=title, url=current_url, content=content))
                if on_progress:
                    on_progress(len(pages), title)

        return pages
