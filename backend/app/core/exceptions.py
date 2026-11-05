"""Custom application exceptions."""

from typing import Any


class VeritasError(Exception):
    def __init__(self, message: str, code: str = "veritas_error", status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(VeritasError):
    def __init__(self, message: str = "Resource not found", code: str = "not_found"):
        super().__init__(message=message, code=code, status_code=404)


class UnauthorizedError(VeritasError):
    def __init__(self, message: str = "Unauthorized", code: str = "unauthorized"):
        super().__init__(message=message, code=code, status_code=401)


class ForbiddenError(VeritasError):
    def __init__(self, message: str = "Forbidden", code: str = "forbidden"):
        super().__init__(message=message, code=code, status_code=403)


class RateLimitError(VeritasError):
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        code: str = "rate_limit",
        retry_after: int | None = None,
    ):
        super().__init__(message=message, code=code, status_code=429)
        self.retry_after = retry_after


class QuotaExceededError(VeritasError):
    def __init__(self, message: str = "Quota exceeded", code: str = "quota_exceeded"):
        super().__init__(message=message, code=code, status_code=402)


class ConflictError(VeritasError):
    def __init__(self, message: str = "Conflict", code: str = "conflict"):
        super().__init__(message=message, code=code, status_code=409)


def error_payload(exc: VeritasError) -> dict[str, Any]:
    return {"error": {"code": exc.code, "message": exc.message}}
