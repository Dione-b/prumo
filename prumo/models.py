"""Shared data models for Prumo crawlers/exporter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

ProgressCallback = Callable[[int, str], None]


@dataclass
class Page:
    """A documentation page with cleaned content."""

    title: str
    url: str
    content: str
