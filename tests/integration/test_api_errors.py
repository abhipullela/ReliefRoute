"""API error-handling tests for ReliefRoute."""

import pytest
from fastapi.testclient import TestClient

from api import main
from shared.enums import ErrorCode
from shared.errors import ReliefRouteError


class FailingSupplierService:
    """Supplier service test double that raises a selected typed error."""

    def __init__(self, error_code: ErrorCode):
        self.error_code = error_code

    async def register_supplier(self, supplier):
        raise ReliefRouteError(
            self.error_code,
            "Simulated service failure",
            retryable=self.error_code
            in {
                ErrorCode.UPSTREAM_TIMEOUT,
                ErrorCode.UPSTREAM_UNAVAILABLE,
                ErrorCode.UPSTREAM_RATE_LIMITED,
            },
            provider="test-provider",
        )


@pytest.mark.parametrize(
    ("error_code", "expected_status"),
    [
        (ErrorCode.VALIDATION_ERROR, 422),
        (ErrorCode.NOT_FOUND, 404),
        (ErrorCode.CONFLICT, 409),
        (ErrorCode.APPROVAL_REQUIRED, 409),
        (ErrorCode.UPSTREAM_TIMEOUT, 504),
        (ErrorCode.UPSTREAM_UNAVAILABLE, 503),
        (ErrorCode.UPSTREAM_RATE_LIMITED, 429),
        (ErrorCode.UPSTREAM_AUTH_FAILED, 502),
        (ErrorCode.INVALID_UPSTREAM_RESPONSE, 502),
        (ErrorCode.DATA_STALE, 503),
    ],
)
def test_typed_errors_map_to_http_status(monkeypatch, error_code, expected_status):
    """Typed domain errors should map to the expected HTTP status."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setattr(
        main,
        "PostgreSQLSupplierService",
        lambda database_url: FailingSupplierService(error_code),
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/suppliers",
            json={
                "supplier_id": "test-supplier",
                "name": "Test Supplier",
                "location": {"latitude": 12.9716, "longitude": 77.5946},
                "contact_channel": "test",
                "contact_handle": "test-handle",
                "active": True,
            },
        )

    assert response.status_code == expected_status
    detail = response.json()["detail"]
    assert detail["code"] == error_code.value
    assert detail["provider"] == "test-provider"


def test_invalid_coordinates_are_rejected_before_service_call(monkeypatch):
    """Out-of-range coordinates must fail request validation."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setattr(
        main,
        "PostgreSQLSupplierService",
        lambda database_url: FailingSupplierService(ErrorCode.UPSTREAM_UNAVAILABLE),
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/suppliers",
            json={
                "supplier_id": "invalid-coordinate-test",
                "name": "Invalid Supplier",
                "location": {"latitude": 120, "longitude": 77.5946},
                "contact_handle": "test-handle",
            },
        )

    assert response.status_code == 422


def test_health_endpoint_is_registered(monkeypatch):
    """Health endpoint is registered and returns a valid response."""
    monkeypatch.setenv("DATABASE_URL", "")

    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code in {200, 503}
    assert isinstance(response.json(), dict)
