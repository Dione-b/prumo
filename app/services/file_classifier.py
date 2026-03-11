# Copyright (C) 2026 Dione Bastos
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


"""Deterministic file-type classifier for the ingestion pipeline.

Centralizes the binary/text decision into a single, testable module.
The whitelist approach ensures that only explicitly allowed text formats
bypass the binary streaming path.
"""

from __future__ import annotations

from pathlib import PurePosixPath

# Whitelist of MIME types safe to materialize as UTF-8 strings.
# Any type NOT in this set is treated as binary (streaming-only).
ALLOWED_TEXT_TYPES: frozenset[str] = frozenset(
    {
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "text/csv",
        "application/x-yaml",
        "application/yaml",
        "text/yaml",
        "application/json",
        "text/html",
        "text/xml",
        "application/xml",
    }
)

# Extensions that are ALWAYS binary, regardless of reported content_type.
_BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".docx",
        ".doc",
        ".xlsx",
        ".xls",
        ".pptx",
        ".ppt",
        ".zip",
        ".tar",
        ".gz",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".webp",
        ".mp3",
        ".mp4",
        ".wav",
        ".ogg",
    }
)

# Maximum text content size to materialize in memory (10 MB).
MAX_TEXT_MATERIALIZATION_BYTES: int = 10 * 1024 * 1024

# Fallback MIME types for known binary extensions without a valid content_type.
_EXTENSION_MIME_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ".doc": "application/msword",
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}


def is_binary_file(content_type: str, filename: str) -> bool:
    """Determine whether a file should be treated as binary (streaming-only).

    The decision is deterministic, based on two criteria:
    1. The file extension is in the known binary extensions set.
    2. The MIME type is NOT in the allowed text types whitelist.

    Args:
        content_type: MIME type reported by the upload (e.g. "application/pdf").
        filename: Filename with extension (e.g. "report.pdf").

    Returns:
        True if the file is binary and must not be materialized as a string.
    """
    suffix = PurePosixPath(filename).suffix.lower()

    # Known binary extension — immediate decision.
    if suffix in _BINARY_EXTENSIONS:
        return True

    # MIME type outside whitelist — treated as binary as a safety measure.
    normalized_type = content_type.strip().lower().split(";")[0]
    return normalized_type not in ALLOWED_TEXT_TYPES


def get_upload_mime(content_type: str, filename: str) -> str:
    """Return the appropriate MIME type for the Gemini File API upload.

    For binary files, preserves the original content_type.
    For text files, normalizes to text/plain.

    Args:
        content_type: MIME type reported by the client.
        filename: Filename with extension.

    Returns:
        MIME type to use for the upload.
    """
    if is_binary_file(content_type, filename):
        normalized = content_type.strip().lower().split(";")[0]
        # Fallback for known extensions without a valid content_type.
        if not normalized or normalized == "application/octet-stream":
            suffix = PurePosixPath(filename).suffix.lower()
            return _EXTENSION_MIME_MAP.get(suffix, "application/octet-stream")
        return normalized
    return "text/plain"
