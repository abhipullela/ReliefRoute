"""Mocked contract tests for the Agmarknet arrivals adapter."""

import asyncio

import httpx
import pytest

import services.mandi as mandi_module
from services.mandi import AgmarknetMandiService
from shared.enums import ErrorCode
from shared.errors import ReliefRouteError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, invalid_json=False):
        self.status_code = status_code
        self._payload = payload
        self.invalid_json = invalid_json

    def json(self):
        if self.invalid_json:
            raise ValueError("not JSON")
        return self._payload


class FakeAsyncClient:
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
        if self.exception:
            raise self.exception
        return self.response


def run(coro):
    return asyncio.run(coro)


async def no_sleep(_):
    return None


def code(exc): 
    err = exc.value 
    service_error = getattr(err, "error", None) 
    value = getattr(service_error, "code", None) 
    return getattr(value, "value", value)


def service():
    return AgmarknetMandiService(max_attempts=2)


def query():
    return dict(year=2026, month=10, state_id=19, commodity_id=10)


def test_normalizes_realistic_arrival_record_and_provenance(monkeypatch):
    payload = {
        "success": True,
        "data": [{
            "arrival_date": "28/10/2026",
            "state": "Karnataka",
            "district": "Kolar",
            "market": "Kolar",
            "commodity": "Tomato",
            "variety": "Local",
            "arrivals": "125.5",
            "arrival_unit": "Quintal",
        }],
    }
    monkeypatch.setattr(
        mandi_module.httpx, "AsyncClient",
        lambda **kw: FakeAsyncClient(response=FakeResponse(payload=payload)),
    )
    results = run(service().get_arrivals(**query()))
    assert len(results) == 1
    row = results[0]
    assert row.commodity == "Tomato"
    assert row.market == "Kolar"
    assert row.quantity == 125.5
    assert row.unit == "Quintal"
    assert row.source_provider == "Agmarknet 2.0"
    assert row.source_url.endswith("/prices-and-arrivals/date-wise/specific-commodity")
    assert row.retrieved_at.tzinfo is not None
    assert row.observed_at is not None and row.observed_at.tzinfo is not None


def test_explicit_no_data_response_returns_empty_list_not_fake_record(monkeypatch):
    monkeypatch.setattr(
        mandi_module.httpx, "AsyncClient",
        lambda **kw: FakeAsyncClient(
            response=FakeResponse(payload={"success": False, "message": "No data found."})
        ),
    )
    assert run(service().get_arrivals(**query())) == []


@pytest.mark.parametrize("month", [0, 13])
def test_invalid_month_rejected_before_http_call(monkeypatch, month):
    def should_not_be_called(**kwargs):
        pytest.fail("HTTP must not be called for invalid query")
    monkeypatch.setattr(mandi_module.httpx, "AsyncClient", should_not_be_called)
    params = query()
    params["month"] = month
    with pytest.raises(ReliefRouteError) as exc:
        run(service().get_arrivals(**params))
    assert code(exc) == ErrorCode.VALIDATION_ERROR.value


def test_missing_unit_is_not_silently_invented(monkeypatch):
    payload = {"data": [{
        "arrival_date": "28/10/2026", "market": "Kolar",
        "commodity": "Tomato", "arrivals": 125.5,
    }]}
    monkeypatch.setattr(
        mandi_module.httpx, "AsyncClient",
        lambda **kw: FakeAsyncClient(response=FakeResponse(payload=payload)),
    )
    with pytest.raises(ReliefRouteError) as exc:
        run(service().get_arrivals(**query()))
    assert code(exc) == ErrorCode.INVALID_UPSTREAM_RESPONSE.value


def test_timeout_maps_to_typed_error(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mandi_module.httpx, "AsyncClient",
        lambda **kw: FakeAsyncClient(
            exception=httpx.ReadTimeout("timeout"), calls=calls
        ),
    )
    monkeypatch.setattr(mandi_module.asyncio, "sleep", no_sleep)
    with pytest.raises(ReliefRouteError) as exc:
        run(service().get_arrivals(**query()))
    assert code(exc) == ErrorCode.UPSTREAM_TIMEOUT.value
    assert len(calls) == 2


def test_rate_limit_maps_to_typed_error(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mandi_module.httpx, "AsyncClient",
        lambda **kw: FakeAsyncClient(
            response=FakeResponse(status_code=429), calls=calls
        ),
    )
    monkeypatch.setattr(mandi_module.asyncio, "sleep", no_sleep)
    with pytest.raises(ReliefRouteError) as exc:
        run(service().get_arrivals(**query()))
    assert code(exc) == ErrorCode.UPSTREAM_RATE_LIMITED.value
    assert len(calls) == 2


def test_auth_failure_maps_to_typed_error_without_retry(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mandi_module.httpx, "AsyncClient",
        lambda **kw: FakeAsyncClient(
            response=FakeResponse(status_code=403), calls=calls
        ),
    )
    with pytest.raises(ReliefRouteError) as exc:
        run(service().get_arrivals(**query()))
    assert code(exc) == ErrorCode.UPSTREAM_AUTH_FAILED.value
    assert len(calls) == 1


def test_invalid_json_maps_to_typed_error(monkeypatch):
    monkeypatch.setattr(
        mandi_module.httpx, "AsyncClient",
        lambda **kw: FakeAsyncClient(response=FakeResponse(invalid_json=True)),
    )
    with pytest.raises(ReliefRouteError) as exc:
        run(service().get_arrivals(**query()))
    assert code(exc) == ErrorCode.INVALID_UPSTREAM_RESPONSE.value


def test_negative_quantity_is_rejected(monkeypatch):
    payload = {"data": [{
        "arrival_date": "28/10/2026", "market": "Kolar",
        "commodity": "Tomato", "arrivals": -3, "arrival_unit": "Quintal",
    }]}
    monkeypatch.setattr(
        mandi_module.httpx, "AsyncClient",
        lambda **kw: FakeAsyncClient(response=FakeResponse(payload=payload)),
    )
    with pytest.raises(ReliefRouteError) as exc:
        run(service().get_arrivals(**query()))
    assert code(exc) == ErrorCode.INVALID_UPSTREAM_RESPONSE.value
