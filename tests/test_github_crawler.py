"""Unit tests for GithubCrawler."""

from __future__ import annotations

import base64

import httpx
import respx

from prumo.crawlers.github import GithubCrawler


def _encode(markdown: str) -> str:
    return base64.b64encode(markdown.encode("utf-8")).decode("utf-8")


class TestGithubCrawler:
    def test_should_parse_github_url_when_valid(self) -> None:
        crawler = GithubCrawler(github_token="token")
        owner, repo, subpath = crawler._parse_github_url(
            "https://github.com/stellar/stellar-docs/tree/main/docs"
        )

        assert owner == "stellar"
        assert repo == "stellar-docs"
        assert subpath == "docs"

    def test_should_return_empty_when_url_is_not_github(self) -> None:
        crawler = GithubCrawler(github_token="token")
        pages = crawler.crawl("https://docs.example.com", max_pages=10)
        assert pages == []

    @respx.mock
    def test_should_detect_docs_subpath_when_root_url(self) -> None:
        crawler = GithubCrawler(github_token="token")

        respx.get("https://api.github.com/repos/acme/repo/contents/").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"type": "dir", "name": "docs", "path": "docs"},
                    {"type": "dir", "name": "src", "path": "src"},
                ],
            )
        )
        respx.get("https://api.github.com/repos/acme/repo/contents/docs").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "type": "file",
                        "name": "intro.md",
                        "path": "docs/intro.md",
                        "url": "https://api.github.com/repos/acme/repo/contents/docs/intro.md",
                        "html_url": "https://github.com/acme/repo/blob/main/docs/intro.md",
                        "content": _encode("# Intro\n\nWelcome"),
                    }
                ],
            )
        )

        pages = crawler.crawl("https://github.com/acme/repo", max_pages=10)

        assert len(pages) == 1
        assert pages[0].title == "Intro"

    @respx.mock
    def test_should_ignore_non_markdown_and_ignored_filenames(self) -> None:
        crawler = GithubCrawler(github_token="token")

        respx.get("https://api.github.com/repos/acme/repo/contents/docs").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "type": "file",
                        "name": "intro.md",
                        "path": "docs/intro.md",
                        "url": "https://api.github.com/repos/acme/repo/contents/docs/intro.md",
                        "html_url": "https://github.com/acme/repo/blob/main/docs/intro.md",
                        "content": _encode("# Intro\n\nWelcome"),
                    },
                    {
                        "type": "file",
                        "name": "CHANGELOG.md",
                        "path": "docs/CHANGELOG.md",
                        "url": "https://api.github.com/repos/acme/repo/contents/docs/CHANGELOG.md",
                        "html_url": "https://github.com/acme/repo/blob/main/docs/CHANGELOG.md",
                        "content": _encode("# Changelog"),
                    },
                    {
                        "type": "file",
                        "name": "logo.png",
                        "path": "docs/logo.png",
                        "url": "https://api.github.com/repos/acme/repo/contents/docs/logo.png",
                        "html_url": "https://github.com/acme/repo/blob/main/docs/logo.png",
                        "content": "",
                    },
                ],
            )
        )

        pages = crawler.crawl("https://github.com/acme/repo/tree/main/docs", max_pages=10)
        assert len(pages) == 1
        assert pages[0].title == "Intro"

    @respx.mock
    def test_should_transform_to_docs_url_when_base_provided(self) -> None:
        crawler = GithubCrawler(
            github_token="token",
            docs_base_url="https://developers.example.com/docs",
        )

        respx.get("https://api.github.com/repos/acme/repo/contents/docs").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "type": "file",
                        "name": "setup.mdx",
                        "path": "docs/setup.mdx",
                        "url": "https://api.github.com/repos/acme/repo/contents/docs/setup.mdx",
                        "html_url": "https://github.com/acme/repo/blob/main/docs/setup.mdx",
                        "content": _encode("# Setup\n\nInstall"),
                    }
                ],
            )
        )

        pages = crawler.crawl("https://github.com/acme/repo/tree/main/docs", max_pages=10)
        assert pages[0].url == "https://developers.example.com/docs/setup"

    @respx.mock
    def test_should_fetch_individually_when_content_is_missing(self) -> None:
        crawler = GithubCrawler(github_token="token")

        respx.get("https://api.github.com/repos/acme/repo/contents/docs").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "type": "file",
                        "name": "install.md",
                        "path": "docs/install.md",
                        "url": "https://api.github.com/repos/acme/repo/contents/docs/install.md",
                        "html_url": "https://github.com/acme/repo/blob/main/docs/install.md",
                        "content": "",
                    }
                ],
            )
        )
        respx.get("https://api.github.com/repos/acme/repo/contents/docs/install.md").mock(
            return_value=httpx.Response(
                200,
                json={"content": _encode("# Install\n\nRun command")},
            )
        )

        pages = crawler.crawl("https://github.com/acme/repo/tree/main/docs", max_pages=10)
        assert len(pages) == 1
        assert pages[0].title == "Install"
