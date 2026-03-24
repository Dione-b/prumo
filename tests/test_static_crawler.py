"""Unit tests for StaticCrawler."""

from __future__ import annotations

import httpx
import respx

from prumo.crawlers.static import StaticCrawler

ROOT_URL = "https://docs.example.com/guide/"

INDEX_HTML = """
<html>
<head><title>Example Docs</title></head>
<body>
<nav><a href="/about">About</a></nav>
<header><h1>Header</h1></header>
<main>
    <h1>Welcome</h1>
    <p>This is the main documentation content.</p>
    <a href="/guide/getting-started">Getting Started</a>
    <a href="/guide/advanced">Advanced</a>
    <a href="https://external.com/unrelated">External</a>
</main>
<footer>Footer content</footer>
</body>
</html>
"""

GETTING_STARTED_HTML = """
<html>
<head><title>Getting Started</title></head>
<body>
<main>
    <h1>Getting Started</h1>
    <p>Install the package and run it.</p>
    <a href="/guide/">Back to index</a>
    <a href="/guide/advanced">Advanced</a>
</main>
</body>
</html>
"""

ADVANCED_HTML = """
<html>
<head><title>Advanced Usage</title></head>
<body>
<main>
    <h1>Advanced Usage</h1>
    <p>Advanced configuration and plugins.</p>
</main>
</body>
</html>
"""


class TestStaticCrawler:
    """Regression coverage for static HTML crawling behavior."""

    @respx.mock
    def test_should_ignore_external_links(self) -> None:
        crawler = StaticCrawler()
        respx.get(ROOT_URL).mock(return_value=httpx.Response(200, text=INDEX_HTML))
        respx.get("https://docs.example.com/guide/getting-started").mock(
            return_value=httpx.Response(200, text=GETTING_STARTED_HTML)
        )
        respx.get("https://docs.example.com/guide/advanced").mock(
            return_value=httpx.Response(200, text=ADVANCED_HTML)
        )

        pages = crawler.crawl(ROOT_URL, max_pages=50)

        urls = [page.url for page in pages]
        assert all("external.com" not in url for url in urls)
        assert len(pages) == 3

    @respx.mock
    def test_should_ignore_links_outside_prefix(self) -> None:
        crawler = StaticCrawler()
        html_with_outside_link = """
        <html><head><title>Test</title></head>
        <body><main>
            <p>Content here.</p>
            <a href="/about">About us</a>
        </main></body></html>
        """
        respx.get(ROOT_URL).mock(return_value=httpx.Response(200, text=html_with_outside_link))

        pages = crawler.crawl(ROOT_URL, max_pages=50)

        assert len(pages) == 1
        assert pages[0].url == ROOT_URL

    @respx.mock
    def test_should_remove_navigation_tags_from_content(self) -> None:
        crawler = StaticCrawler()
        respx.get(ROOT_URL).mock(return_value=httpx.Response(200, text=INDEX_HTML))
        respx.get("https://docs.example.com/guide/getting-started").mock(
            return_value=httpx.Response(200, text=GETTING_STARTED_HTML)
        )
        respx.get("https://docs.example.com/guide/advanced").mock(
            return_value=httpx.Response(200, text=ADVANCED_HTML)
        )

        pages = crawler.crawl(ROOT_URL, max_pages=50)
        index_page = next(page for page in pages if page.url == ROOT_URL)

        assert "About" not in index_page.content
        assert "Footer content" not in index_page.content
        assert "Header" not in index_page.content
        assert "# Welcome" in index_page.content
        assert "main documentation content" in index_page.content

    @respx.mock
    def test_should_respect_max_pages(self) -> None:
        crawler = StaticCrawler()
        respx.get(ROOT_URL).mock(return_value=httpx.Response(200, text=INDEX_HTML))
        respx.get("https://docs.example.com/guide/getting-started").mock(
            return_value=httpx.Response(200, text=GETTING_STARTED_HTML)
        )
        respx.get("https://docs.example.com/guide/advanced").mock(
            return_value=httpx.Response(200, text=ADVANCED_HTML)
        )

        pages = crawler.crawl(ROOT_URL, max_pages=2)
        assert len(pages) == 2

    @respx.mock
    def test_should_extract_title_from_title_tag(self) -> None:
        crawler = StaticCrawler()
        respx.get(ROOT_URL).mock(return_value=httpx.Response(200, text=INDEX_HTML))
        respx.get("https://docs.example.com/guide/getting-started").mock(
            return_value=httpx.Response(200, text=GETTING_STARTED_HTML)
        )
        respx.get("https://docs.example.com/guide/advanced").mock(
            return_value=httpx.Response(200, text=ADVANCED_HTML)
        )

        pages = crawler.crawl(ROOT_URL, max_pages=50)
        index_page = next(page for page in pages if page.url == ROOT_URL)
        assert index_page.title == "Example Docs"

    @respx.mock
    def test_should_fallback_title_to_h1(self) -> None:
        crawler = StaticCrawler()
        html_without_title = """
        <html><head></head>
        <body><main>
            <h1>Fallback Title</h1>
            <p>Some content.</p>
        </main></body></html>
        """
        respx.get(ROOT_URL).mock(return_value=httpx.Response(200, text=html_without_title))

        pages = crawler.crawl(ROOT_URL, max_pages=50)
        assert pages[0].title == "Fallback Title"

    @respx.mock
    def test_should_return_untitled_when_no_title_or_h1(self) -> None:
        crawler = StaticCrawler()
        html_without_title_or_h1 = """
        <html><head></head>
        <body><main><p>Just content.</p></main></body></html>
        """
        respx.get(ROOT_URL).mock(
            return_value=httpx.Response(200, text=html_without_title_or_h1)
        )

        pages = crawler.crawl(ROOT_URL, max_pages=50)
        assert pages[0].title == "Untitled"

    @respx.mock
    def test_should_skip_empty_content_page(self) -> None:
        crawler = StaticCrawler()
        empty_html = """
        <html><head><title>Empty</title></head>
        <body><main></main></body></html>
        """
        respx.get(ROOT_URL).mock(return_value=httpx.Response(200, text=empty_html))

        pages = crawler.crawl(ROOT_URL, max_pages=50)
        assert len(pages) == 0

    @respx.mock
    def test_should_skip_http_error_page(self) -> None:
        crawler = StaticCrawler()
        respx.get(ROOT_URL).mock(return_value=httpx.Response(500, text="Internal Server Error"))

        pages = crawler.crawl(ROOT_URL, max_pages=50)
        assert len(pages) == 0
