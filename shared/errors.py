from shared.enums import ErrorCode
from shared.models import ServiceError


class ReliefRouteError(Exception):
    def __init__(self, code: ErrorCode, message: str, *, retryable: bool = False,
                 provider: str | None = None, details: dict | None = None,
                 delivery_uncertain: bool = False):
        super().__init__(message)
        self.delivery_uncertain = delivery_uncertain
        self.error = ServiceError(
            code=code, message=message, retryable=retryable,
            provider=provider, details=details or {}
        )
