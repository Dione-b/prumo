"""Base crawler contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from prumo.models import Page, ProgressCallback


class Crawler(ABC):
    @abstractmethod
    def crawl(
        self,
        url: str,
        max_pages: int = 50,
        on_progress: ProgressCallback | None = None,
    ) -> list[Page]:
        """Collect and return pages from a source URL."""
