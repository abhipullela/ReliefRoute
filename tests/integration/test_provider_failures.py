"""Mocked provider failure tests for Open-Meteo and OSRM.

These tests do not call live providers and do not require DATABASE_URL.
Run from the repository root:
    python -m pytest tests/integration/test_provider_failures.py -q
"""

import asyncio

import httpx
import pytest

import services.routing as routing_module
import services.weather as weather_module
from services.routing import OSRMRoutingService
from services.weather import OpenMeteoWeatherService
from shared.enums import ErrorCode
from shared.errors import ReliefRouteError
from shared.models import LatLon, RouteRequest


class FakeResponse:
    def __init__(self, status_code=200, payload=None, json_error=None):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error
        self.is_error = status_code >= 400

    def json(self):
        if self._json_error:
            raise ValueError("invalid JSON")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://provider.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=request, response=response
            )


class FakeAsyncClient:
    """Minimal AsyncClient replacement supporting async context management."""

    def __init__(self, *, response=None, exception=None, calls=None, **kwargs):
        self.response = response
        self.exception = exception
        self.calls = calls if calls is not None else []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.exception is not None:
            raise self.exception
        return self.response


def run(coro):
    return asyncio.run(coro)


async def no_sleep(_seconds):
    return None


def error_code(exc_info):
    """Read the typed code without assuming a particular wrapper attribute name."""
    error = exc_info.value
    for attribute in ("service_error", "error", "details"):
        candidate = getattr(error, attribute, None)
        if candidate is not None and hasattr(candidate, "code"):
            error = candidate
            break
    code = getattr(error, "code", None)
    return getattr(code, "value", code)


def test_weather_timeout_maps_to_typed_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(
        weather_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(
            exception=httpx.ReadTimeout("timed out"), calls=calls
        ),
    )
    monkeypatch.setattr(weather_module.asyncio, "sleep", no_sleep)
    service = OpenMeteoWeatherService(timeout_seconds=0.01, max_attempts=3)

    with pytest.raises(ReliefRouteError) as exc:
        run(service.get_forecast(LatLon(latitude=12.97, longitude=77.59)))

    assert error_code(exc) == ErrorCode.UPSTREAM_TIMEOUT.value
    assert len(calls) == 3


def test_weather_rate_limit_maps_to_rate_limited(monkeypatch):
    calls = []
    monkeypatch.setattr(
        weather_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(
            response=FakeResponse(status_code=429), calls=calls
        ),
    )
    monkeypatch.setattr(weather_module.asyncio, "sleep", no_sleep)
    service = OpenMeteoWeatherService(max_attempts=3)

    with pytest.raises(ReliefRouteError) as exc:
        run(service.get_forecast(LatLon(latitude=12.97, longitude=77.59)))

    assert error_code(exc) == ErrorCode.UPSTREAM_RATE_LIMITED.value
    assert len(calls) == 3


def test_weather_auth_failure_is_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(
        weather_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(
            response=FakeResponse(status_code=401), calls=calls
        ),
    )
    service = OpenMeteoWeatherService(max_attempts=3)

    with pytest.raises(ReliefRouteError) as exc:
        run(service.get_forecast(LatLon(latitude=12.97, longitude=77.59)))

    assert error_code(exc) == ErrorCode.UPSTREAM_AUTH_FAILED.value
    assert len(calls) == 1


def test_weather_invalid_json_maps_to_invalid_response(monkeypatch):
    monkeypatch.setattr(
        weather_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(
            response=FakeResponse(json_error=True)
        ),
    )
    service = OpenMeteoWeatherService(max_attempts=1)

    with pytest.raises(ReliefRouteError) as exc:
        run(service.get_forecast(LatLon(latitude=12.97, longitude=77.59)))

    assert error_code(exc) == ErrorCode.INVALID_UPSTREAM_RESPONSE.value


def test_weather_missing_hourly_fields_maps_to_invalid_response(monkeypatch):
    monkeypatch.setattr(
        weather_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(response=FakeResponse(payload={})),
    )
    service = OpenMeteoWeatherService(max_attempts=1)

    with pytest.raises(ReliefRouteError) as exc:
        run(service.get_forecast(LatLon(latitude=12.97, longitude=77.59)))

    assert error_code(exc) == ErrorCode.INVALID_UPSTREAM_RESPONSE.value


def make_route_request():
    return RouteRequest(
        origin=LatLon(latitude=12.97, longitude=77.59),
        destination=LatLon(latitude=13.08, longitude=77.64),
        profile="driving-car",
        avoid_polygons=[],
    )


def test_routing_timeout_maps_to_typed_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(
        routing_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(
            exception=httpx.ReadTimeout("timed out"), calls=calls
        ),
    )
    monkeypatch.setattr(routing_module.asyncio, "sleep", no_sleep)
    service = OSRMRoutingService(max_retries=2)

    with pytest.raises(ReliefRouteError) as exc:
        run(service.calculate_safe_route(make_route_request()))

    assert error_code(exc) == ErrorCode.UPSTREAM_TIMEOUT.value
    assert len(calls) == 3


def test_routing_rate_limit_is_reported_as_upstream_unavailable(monkeypatch):
    """Assert current implementation's behavior for OSRM HTTP 429."""
    calls = []
    monkeypatch.setattr(
        routing_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(
            response=FakeResponse(status_code=429), calls=calls
        ),
    )
    monkeypatch.setattr(routing_module.asyncio, "sleep", no_sleep)
    service = OSRMRoutingService(max_retries=2)

    with pytest.raises(ReliefRouteError) as exc:
        run(service.calculate_safe_route(make_route_request()))

    # Current routing.py groups 429 with 5xx and maps both to UNAVAILABLE.
    assert error_code(exc) == ErrorCode.UPSTREAM_UNAVAILABLE.value
    assert len(calls) == 3


def test_routing_auth_failure_is_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(
        routing_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(
            response=FakeResponse(status_code=403), calls=calls
        ),
    )
    service = OSRMRoutingService(max_retries=2)

    with pytest.raises(ReliefRouteError) as exc:
        run(service.calculate_safe_route(make_route_request()))

    assert error_code(exc) == ErrorCode.UPSTREAM_AUTH_FAILED.value
    assert len(calls) == 1


def test_routing_invalid_json_maps_to_invalid_response(monkeypatch):
    monkeypatch.setattr(
        routing_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(
            response=FakeResponse(json_error=True)
        ),
    )
    service = OSRMRoutingService(max_retries=0)

    with pytest.raises(ReliefRouteError) as exc:
        run(service.calculate_safe_route(make_route_request()))

    assert error_code(exc) == ErrorCode.INVALID_UPSTREAM_RESPONSE.value


def test_routing_no_routes_maps_to_invalid_response(monkeypatch):
    monkeypatch.setattr(
        routing_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(
            response=FakeResponse(payload={"code": "Ok", "routes": []})
        ),
    )
    service = OSRMRoutingService(max_retries=0)

    with pytest.raises(ReliefRouteError) as exc:
        run(service.calculate_safe_route(make_route_request()))

    assert error_code(exc) == ErrorCode.INVALID_UPSTREAM_RESPONSE.value
