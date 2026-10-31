from shared.enums import ErrorCode
from shared.models import ServiceError

class ReliefRouteError(Exception):
    def __init__(self, code: ErrorCode, message: str, *, retryable: bool = False,
                 provider: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.error = ServiceError(
            code=code, message=message, retryable=retryable,
            provider=provider, details=details or {}
        )
