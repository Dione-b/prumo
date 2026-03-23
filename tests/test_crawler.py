"""Unit tests for the crawler.

Mock HTTP via respx to isolate from real network.
"""

from __future__ import annotations

import httpx
import respx

from prumo.crawler import crawl

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


class TestCrawlLinkFiltering:
    """Tests that links outside the domain/prefix are ignored."""

    @respx.mock
    def test_external_links_are_ignored(self) -> None:
        # Arrange
        respx.get(ROOT_URL).mock(
            return_value=httpx.Response(200, text=INDEX_HTML)
        )
        respx.get("https://docs.example.com/guide/getting-started").mock(
            return_value=httpx.Response(200, text=GETTING_STARTED_HTML)
        )
        respx.get("https://docs.example.com/guide/advanced").mock(
            return_value=httpx.Response(200, text=ADVANCED_HTML)
        )

        # Act
        pages = crawl(ROOT_URL, max_pages=50)

        # Assert — no page from external.com should appear
        urls = [p.url for p in pages]
        assert all("external.com" not in u for u in urls)
        assert len(pages) == 3

    @respx.mock
    def test_links_outside_path_prefix_are_ignored(self) -> None:
        """Links from the same domain but outside the /guide/ prefix are ignored."""
        # Arrange
        html_with_about_link = """
        <html><head><title>Test</title></head>
        <body><main>
            <p>Content here.</p>
            <a href="/about">About us</a>
        </main></body></html>
        """
        respx.get(ROOT_URL).mock(
            return_value=httpx.Response(200, text=html_with_about_link)
        )

        # Act
        pages = crawl(ROOT_URL, max_pages=50)

        # Assert — /about is outside the /guide/ prefix
        assert len(pages) == 1
        assert pages[0].url == ROOT_URL


class TestCrawlNavRemoval:
    """Tests that navigation tags are removed from content."""

    @respx.mock
    def test_nav_footer_header_removed_from_content(self) -> None:
        # Arrange
        respx.get(ROOT_URL).mock(
            return_value=httpx.Response(200, text=INDEX_HTML)
        )
        respx.get("https://docs.example.com/guide/getting-started").mock(
            return_value=httpx.Response(200, text=GETTING_STARTED_HTML)
        )
        respx.get("https://docs.example.com/guide/advanced").mock(
            return_value=httpx.Response(200, text=ADVANCED_HTML)
        )

        # Act
        pages = crawl(ROOT_URL, max_pages=50)
        index_page = next(p for p in pages if p.url == ROOT_URL)

        # Assert — content from nav, footer, and header should not appear
        assert "About" not in index_page.content
        assert "Footer content" not in index_page.content
        assert "Header" not in index_page.content
        # Main content should exist
        assert "main documentation content" in index_page.content


class TestCrawlMaxPages:
    """Tests that max_pages limits the number of returned pages."""

    @respx.mock
    def test_max_pages_is_respected(self) -> None:
        # Arrange
        respx.get(ROOT_URL).mock(
            return_value=httpx.Response(200, text=INDEX_HTML)
        )
        respx.get("https://docs.example.com/guide/getting-started").mock(
            return_value=httpx.Response(200, text=GETTING_STARTED_HTML)
        )
        respx.get("https://docs.example.com/guide/advanced").mock(
            return_value=httpx.Response(200, text=ADVANCED_HTML)
        )

        # Act
        pages = crawl(ROOT_URL, max_pages=2)

        # Assert
        assert len(pages) == 2


class TestCrawlTitleExtraction:
    """Tests page title extraction."""

    @respx.mock
    def test_title_extracted_from_title_tag(self) -> None:
        # Arrange
        respx.get(ROOT_URL).mock(
            return_value=httpx.Response(200, text=INDEX_HTML)
        )
        respx.get("https://docs.example.com/guide/getting-started").mock(
            return_value=httpx.Response(200, text=GETTING_STARTED_HTML)
        )
        respx.get("https://docs.example.com/guide/advanced").mock(
            return_value=httpx.Response(200, text=ADVANCED_HTML)
        )

        # Act
        pages = crawl(ROOT_URL, max_pages=50)
        index_page = next(p for p in pages if p.url == ROOT_URL)

        # Assert
        assert index_page.title == "Example Docs"

    @respx.mock
    def test_title_fallback_to_h1(self) -> None:
        """If there is no <title>, uses the first <h1>."""
        # Arrange
        html_no_title = """
        <html><head></head>
        <body><main>
            <h1>Fallback Title</h1>
            <p>Some content.</p>
        </main></body></html>
        """
        respx.get(ROOT_URL).mock(
            return_value=httpx.Response(200, text=html_no_title)
        )

        # Act
        pages = crawl(ROOT_URL, max_pages=50)

        # Assert
        assert pages[0].title == "Fallback Title"

    @respx.mock
    def test_title_untitled_when_no_title_or_h1(self) -> None:
        """With no <title> and no <h1>, returns 'Untitled'."""
        # Arrange
        html_no_title = """
        <html><head></head>
        <body><main><p>Just content.</p></main></body></html>
        """
        respx.get(ROOT_URL).mock(
            return_value=httpx.Response(200, text=html_no_title)
        )

        # Act
        pages = crawl(ROOT_URL, max_pages=50)

        # Assert
        assert pages[0].title == "Untitled"


class TestCrawlContentExtraction:
    """Tests extraction of cleaned content."""

    @respx.mock
    def test_content_from_main_tag(self) -> None:
        # Arrange
        respx.get(ROOT_URL).mock(
            return_value=httpx.Response(200, text=GETTING_STARTED_HTML)
        )

        # Act
        pages = crawl(ROOT_URL, max_pages=1)

        # Assert
        assert "Install the package" in pages[0].content

    @respx.mock
    def test_empty_content_page_is_skipped(self) -> None:
        """Pages without textual content are ignored."""
        # Arrange
        empty_html = """
        <html><head><title>Empty</title></head>
        <body><main></main></body></html>
        """
        respx.get(ROOT_URL).mock(
            return_value=httpx.Response(200, text=empty_html)
        )

        # Act
        pages = crawl(ROOT_URL, max_pages=50)

        # Assert
        assert len(pages) == 0


class TestCrawlHttpErrors:
    """Tests behavior with HTTP failures."""

    @respx.mock
    def test_http_error_page_is_skipped(self) -> None:
        # Arrange
        respx.get(ROOT_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        # Act
        pages = crawl(ROOT_URL, max_pages=50)

        # Assert
        assert len(pages) == 0
