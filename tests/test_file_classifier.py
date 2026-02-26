"""Tests for the deterministic file-type classifier."""

import pytest

from app.services.file_classifier import (
    ALLOWED_TEXT_TYPES,
    MAX_TEXT_MATERIALIZATION_BYTES,
    get_upload_mime,
    is_binary_file,
)


class TestIsBinaryFile:
    """Tests for the is_binary_file classifier."""

    # -- Binary by extension --

    @pytest.mark.parametrize(
        "filename",
        ["report.pdf", "doc.docx", "sheet.xlsx", "archive.zip", "image.png"],
    )
    def test_known_binary_extensions_always_binary(self, filename: str) -> None:
        # Arrange / Act
        result = is_binary_file("text/plain", filename)

        # Assert — extension overrides any MIME type.
        assert result is True

    def test_pdf_binary_regardless_of_content_type(self) -> None:
        # Arrange / Act
        result = is_binary_file("text/plain", "document.pdf")

        # Assert
        assert result is True

    # -- Text by MIME whitelist --

    @pytest.mark.parametrize(
        ("content_type", "filename"),
        [
            ("text/plain", "readme.txt"),
            ("text/markdown", "notes.md"),
            ("application/json", "config.json"),
            ("application/x-yaml", "rules.yaml"),
            ("text/yaml", "spec.yml"),
            ("text/csv", "data.csv"),
            ("text/html", "page.html"),
        ],
    )
    def test_allowed_text_types_not_binary(
        self, content_type: str, filename: str
    ) -> None:
        # Arrange / Act
        result = is_binary_file(content_type, filename)

        # Assert
        assert result is False

    # -- Binary by MIME not in whitelist --

    def test_unknown_mime_treated_as_binary(self) -> None:
        # Arrange / Act
        result = is_binary_file("application/octet-stream", "mystery.dat")

        # Assert
        assert result is True

    def test_mime_with_charset_param_still_matched(self) -> None:
        # Arrange — browsers often append charset.
        result = is_binary_file("text/plain; charset=utf-8", "notes.txt")

        # Assert — should strip params and match whitelist.
        assert result is False

    # -- Edge cases --

    def test_empty_content_type_treated_as_binary(self) -> None:
        # Arrange / Act
        result = is_binary_file("", "unknown.xyz")

        # Assert
        assert result is True

    def test_case_insensitive_extension(self) -> None:
        # Arrange / Act
        result = is_binary_file("application/pdf", "Report.PDF")

        # Assert
        assert result is True


class TestGetUploadMime:
    """Tests for the MIME type resolver."""

    def test_text_file_normalized_to_text_plain(self) -> None:
        # Arrange / Act
        result = get_upload_mime("text/markdown", "readme.md")

        # Assert
        assert result == "text/plain"

    def test_pdf_preserves_content_type(self) -> None:
        # Arrange / Act
        result = get_upload_mime("application/pdf", "report.pdf")

        # Assert
        assert result == "application/pdf"

    def test_octet_stream_pdf_uses_extension_fallback(self) -> None:
        # Arrange — browser sends generic MIME but file is .pdf.
        result = get_upload_mime("application/octet-stream", "report.pdf")

        # Assert — fallback to extension-based MIME.
        assert result == "application/pdf"

    def test_docx_with_octet_stream_fallback(self) -> None:
        # Arrange / Act
        result = get_upload_mime("application/octet-stream", "doc.docx")

        # Assert
        assert result == (
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        )

    def test_unknown_binary_returns_octet_stream(self) -> None:
        # Arrange / Act
        result = get_upload_mime("application/octet-stream", "data.bin")

        # Assert
        assert result == "application/octet-stream"

    def test_empty_mime_for_pdf_uses_fallback(self) -> None:
        # Arrange / Act
        result = get_upload_mime("", "report.pdf")

        # Assert
        assert result == "application/pdf"


class TestConstants:
    """Sanity checks for module-level constants."""

    def test_allowed_text_types_is_frozenset(self) -> None:
        assert isinstance(ALLOWED_TEXT_TYPES, frozenset)

    def test_max_materialization_is_10mb(self) -> None:
        assert MAX_TEXT_MATERIALIZATION_BYTES == 10 * 1024 * 1024

    def test_text_plain_in_whitelist(self) -> None:
        assert "text/plain" in ALLOWED_TEXT_TYPES

    def test_application_pdf_not_in_whitelist(self) -> None:
        assert "application/pdf" not in ALLOWED_TEXT_TYPES
