class AppError(Exception):
    """Base exception for all application-level errors."""


class SanitizationError(AppError):
    """Raised when LLM output fails JSON sanitization or decoding."""
