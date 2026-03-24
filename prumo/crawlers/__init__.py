"""Crawler implementations and factory selection."""

from __future__ import annotations

from prumo.crawlers.base import Crawler
from prumo.crawlers.github import GithubCrawler
from prumo.crawlers.static import StaticCrawler
from prumo.errors import CrawlerError


def resolve_crawler(
    *,
    github: bool,
    js: bool,
    github_token: str | None = None,
    docs_base_url: str | None = None,
) -> Crawler:
    if github and js:
        raise CrawlerError("--github and --js are mutually exclusive.")

    if js:
        from prumo.crawlers.playwright import PlaywrightCrawler

        return PlaywrightCrawler()

    if github:
        if not github_token:
            raise CrawlerError("GitHub token is required for --github mode.")
        return GithubCrawler(github_token=github_token, docs_base_url=docs_base_url)

    return StaticCrawler()


__all__ = ["Crawler", "GithubCrawler", "StaticCrawler", "resolve_crawler"]
