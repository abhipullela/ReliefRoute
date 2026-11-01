"""Telegram provider contract tests; all HTTP interactions are mocked."""

import asyncio

import httpx
import pytest

from services.notifications import TelegramNotificationProvider
from shared.enums import ErrorCode
from shared.errors import ReliefRouteError
from shared.models import DispatchRequest


def dispatch_request(**overrides) -> DispatchRequest:
    values = {
        "plan_id": "plan-1",
        "driver_id": "driver-1",
        "telegram_chat_id": "chat-1",
        "message": "Deliver supplies",
        "idempotency_key": "dispatch-key-1",
    }
    return DispatchRequest(**(values | overrides))


def test_telegram_provider_returns_only_confirmed_message_ids():
    observed = {}

    def handler(request):
        observed["url"] = str(request.url)
        observed["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={"ok": True, "result": {"message_id": 872}},
        )

    async def send():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            provider = TelegramNotificationProvider("test-token", client=client)
            return await provider(dispatch_request())

    result = asyncio.run(send())

    assert result == {"status": "SENT", "provider_message_id": "872"}
    assert observed["url"].endswith("/bottest-token/sendMessage")
    assert '"chat_id":"chat-1"' in observed["body"]


@pytest.mark.parametrize(
    ("status_code", "body", "error_code"),
    [
        (401, {"ok": False, "error_code": 401}, ErrorCode.UPSTREAM_AUTH_FAILED),
        (429, {"ok": False, "error_code": 429}, ErrorCode.UPSTREAM_RATE_LIMITED),
        (400, {"ok": False, "error_code": 400}, ErrorCode.VALIDATION_ERROR),
    ],
)
def test_telegram_provider_surfaces_definitive_rejections(
    status_code, body, error_code
):
    async def send():
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(status_code, json=body)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            provider = TelegramNotificationProvider("test-token", client=client)
            return await provider(dispatch_request())

    with pytest.raises(ReliefRouteError) as error:
        asyncio.run(send())

    assert error.value.error.code == error_code
    assert not error.value.delivery_uncertain


def test_telegram_timeout_is_marked_unresolved():
    def handler(_request):
        raise httpx.ReadTimeout("simulated timeout")

    async def send():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = TelegramNotificationProvider("test-token", client=client)
            return await provider(dispatch_request())

    with pytest.raises(ReliefRouteError) as error:
        asyncio.run(send())

    assert error.value.error.code == ErrorCode.UPSTREAM_TIMEOUT
    assert error.value.delivery_uncertain


@pytest.mark.parametrize(
    "content",
    [
        b"not-json",
        b'{"ok": true, "result": {}}',
        b'{"ok": true, "result": {"message_id": 0}}',
        b'{"ok": true, "result": {"message_id": "872"}}',
        b"[]",
    ],
)
def test_malformed_telegram_response_is_not_reported_as_sent(content):
    async def send():
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, content=content)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            provider = TelegramNotificationProvider("test-token", client=client)
            return await provider(dispatch_request())

    with pytest.raises(ReliefRouteError) as error:
        asyncio.run(send())

    assert error.value.error.code == ErrorCode.INVALID_UPSTREAM_RESPONSE
    assert error.value.delivery_uncertain


@pytest.mark.parametrize(
    ("token", "dispatch", "error_code"),
    [
        (None, dispatch_request(), ErrorCode.UPSTREAM_UNAVAILABLE),
        ("test-token", dispatch_request(telegram_chat_id=None), ErrorCode.VALIDATION_ERROR),
    ],
)
def test_telegram_provider_validates_configuration_and_destination(
    token, dispatch, error_code
):
    with pytest.raises(ReliefRouteError) as error:
        TelegramNotificationProvider(token).validate(dispatch)
    assert error.value.error.code == error_code
