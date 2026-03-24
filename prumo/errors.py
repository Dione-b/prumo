"""Domain exceptions for crawling and export flows."""

from __future__ import annotations


class CrawlerError(Exception):
    """Base error for crawler failures."""


class ExportError(Exception):
    """Raised when export generation fails."""
