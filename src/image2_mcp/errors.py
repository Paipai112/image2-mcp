"""Custom exceptions for image2-mcp."""


class Image2Exception(Exception):
    """Base exception for image2-mcp."""

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


class AuthError(Image2Exception):
    """Authentication / API key error."""

    def __init__(self, message: str = "Authentication failed. Check MAGENE_API_KEY.") -> None:
        super().__init__(message)
        self.status = 401

    @property
    def retryable(self) -> bool:
        return False


class NetworkError(Image2Exception):
    """Network / connection error."""

    def __init__(self, message: str = "Network error", status: int = 0) -> None:
        super().__init__(message)
        self.status = status

    @property
    def retryable(self) -> bool:
        return True


class ValidationError(Image2Exception):
    """Parameter validation error."""

    @property
    def retryable(self) -> bool:
        return False


class APIError(Image2Exception):
    """Upstream API returned an error response."""

    def __init__(self, status: int, message: str, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body

    @property
    def retryable(self) -> bool:
        return self.status >= 500
