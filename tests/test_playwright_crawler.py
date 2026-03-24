"""Unit tests for PlaywrightCrawler."""

from __future__ import annotations

import builtins
import sys
from types import SimpleNamespace

import pytest

from prumo.crawlers.playwright import PlaywrightCrawler
from prumo.cli import JS_SECURITY_WARNING
from prumo.errors import CrawlerError


class FakePlaywrightError(Exception):
    """Fake Playwright Error for tests."""


class FakePage:
    def __init__(
        self,
        html_by_url: dict[str, str],
        links_by_url: dict[str, list[str]],
        failing_urls: set[str] | None = None,
    ) -> None:
        self._html_by_url = html_by_url
        self._links_by_url = links_by_url
        self._failing_urls = failing_urls or set()
        self._current_url = ""

    def goto(self, url: str, wait_until: str, timeout: int) -> None:
        del wait_until, timeout
        if url in self._failing_urls:
            raise FakePlaywrightError("timeout")
        self._current_url = url

    def content(self) -> str:
        return self._html_by_url[self._current_url]

    def eval_on_selector_all(self, selector: str, script: str) -> list[str]:
        del selector, script
        return self._links_by_url.get(self._current_url, [])


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self._page = page

    def new_page(self) -> FakePage:
        return self._page


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self._page = page

    def new_context(self, accept_downloads: bool) -> FakeContext:
        assert accept_downloads is False
        return FakeContext(self._page)

    def close(self) -> None:
        return None


class FakeChromium:
    def __init__(self, browser: FakeBrowser) -> None:
        self._browser = browser

    def launch(self, headless: bool) -> FakeBrowser:
        assert headless is True
        return self._browser


class FakeSyncPlaywright:
    def __init__(self, browser: FakeBrowser) -> None:
        self._playwright = SimpleNamespace(chromium=FakeChromium(browser))

    def __call__(self) -> "FakeSyncPlaywright":
        return self

    def __enter__(self) -> SimpleNamespace:
        return self._playwright

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        return None


def _install_fake_playwright(
    monkeypatch: pytest.MonkeyPatch,
    html_by_url: dict[str, str],
    links_by_url: dict[str, list[str]],
    failing_urls: set[str] | None = None,
) -> None:
    fake_page = FakePage(html_by_url, links_by_url, failing_urls=failing_urls)
    fake_browser = FakeBrowser(fake_page)
    fake_sync = FakeSyncPlaywright(fake_browser)
    fake_module = SimpleNamespace(sync_playwright=fake_sync, Error=FakePlaywrightError)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_module)


class TestPlaywrightCrawler:
    def test_should_extract_pages_from_rendered_html(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = "https://docs.example.com/guide"
        page_two = "https://docs.example.com/guide/getting-started"

        _install_fake_playwright(
            monkeypatch,
            html_by_url={
                root: "<html><title>Guide</title><body><main><p>Root content</p></main></body></html>",
                page_two: "<html><title>Getting Started</title><body><main><p>Step by step</p></main></body></html>",
            },
            links_by_url={root: [page_two], page_two: []},
        )

        crawler = PlaywrightCrawler()
        pages = crawler.crawl(root, max_pages=10)

        assert len(pages) == 2
        assert pages[0].title == "Guide"
        assert pages[1].title == "Getting Started"

    def test_should_respect_max_pages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        root = "https://docs.example.com/guide"
        page_two = "https://docs.example.com/guide/getting-started"

        _install_fake_playwright(
            monkeypatch,
            html_by_url={
                root: "<html><title>Guide</title><body><main><p>Root content</p></main></body></html>",
                page_two: "<html><title>Getting Started</title><body><main><p>Step by step</p></main></body></html>",
            },
            links_by_url={root: [page_two], page_two: []},
        )

        crawler = PlaywrightCrawler()
        pages = crawler.crawl(root, max_pages=1)

        assert len(pages) == 1
        assert pages[0].title == "Guide"

    def test_should_raise_when_playwright_not_installed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original_import = builtins.__import__

        def fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "playwright.sync_api":
                raise ImportError("not installed")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        crawler = PlaywrightCrawler()
        with pytest.raises(CrawlerError, match="Playwright nao instalado"):
            crawler.crawl("https://docs.example.com/guide", max_pages=10)

    def test_should_skip_page_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        root = "https://docs.example.com/guide"
        bad = "https://docs.example.com/guide/failing-page"
        good = "https://docs.example.com/guide/good-page"

        _install_fake_playwright(
            monkeypatch,
            html_by_url={
                root: "<html><title>Guide</title><body><main><p>Root content</p></main></body></html>",
                good: "<html><title>Good Page</title><body><main><p>Good content</p></main></body></html>",
            },
            links_by_url={root: [bad, good], good: []},
            failing_urls={bad},
        )

        crawler = PlaywrightCrawler()
        pages = crawler.crawl(root, max_pages=10)

        titles = [page.title for page in pages]
        assert "Guide" in titles
        assert "Good Page" in titles

    def test_should_define_security_warning_message(self) -> None:
        assert "JavaScript rendering mode enabled" in JS_SECURITY_WARNING
