"""Testes unitários para o crawler.

Mock HTTP via respx para isolar de rede real.
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
    """Testa que links fora do domínio/prefixo são ignorados."""

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

        # Assert — nenhuma página de external.com deve aparecer
        urls = [p.url for p in pages]
        assert all("external.com" not in u for u in urls)
        assert len(pages) == 3

    @respx.mock
    def test_links_outside_path_prefix_are_ignored(self) -> None:
        """Links do mesmo domínio mas fora do prefixo /guide/ são ignorados."""
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

        # Assert — /about está fora do prefixo /guide/
        assert len(pages) == 1
        assert pages[0].url == ROOT_URL


class TestCrawlNavRemoval:
    """Testa que tags de navegação são removidas do conteúdo."""

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

        # Assert — conteúdo de nav, footer e header não deve aparecer
        assert "About" not in index_page.content
        assert "Footer content" not in index_page.content
        assert "Header" not in index_page.content
        # Conteúdo principal deve existir
        assert "main documentation content" in index_page.content


class TestCrawlMaxPages:
    """Testa que max_pages limita o número de páginas retornadas."""

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
    """Testa extração de título da página."""

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
        """Se não houver <title>, usa o primeiro <h1>."""
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
        """Sem <title> e sem <h1>, retorna 'Untitled'."""
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
    """Testa extração do conteúdo limpo."""

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
        """Páginas sem conteúdo textual são ignoradas."""
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
    """Testa comportamento com falhas HTTP."""

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
