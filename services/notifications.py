"""Telegram Bot API notification provider."""

from collections.abc import Mapping
from typing import Any

import httpx

from shared.enums import ErrorCode
from shared.errors import ReliefRouteError
from shared.models import DispatchRequest


class TelegramNotificationProvider:
    """Send dispatch messages through Telegram and require provider confirmation."""

    def __init__(
        self,
        bot_token: str | None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.bot_token = bot_token.strip() if bot_token else None
        self.client = client

    def validate(self, request: DispatchRequest) -> None:
        if not self.bot_token:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Telegram notification provider is not configured.",
                provider="telegram",
                details={"required_configuration": "TELEGRAM_BOT_TOKEN"},
            )
        if not request.telegram_chat_id:
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "A Telegram chat ID is required for this driver.",
                provider="telegram",
                details={"required_field": "telegram_chat_id"},
            )

    async def __call__(self, request: DispatchRequest) -> Mapping[str, Any]:
        self.validate(request)
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": request.telegram_chat_id,
            "text": request.message,
        }

        try:
            if self.client is not None:
                response = await self.client.post(url, json=payload)
                return self._confirmed_result(response)

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                return self._confirmed_result(response)
        except httpx.TimeoutException as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_TIMEOUT,
                "Telegram did not confirm whether the message was delivered.",
                retryable=True,
                provider="telegram",
                delivery_uncertain=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Telegram did not confirm whether the message was delivered.",
                retryable=True,
                provider="telegram",
                delivery_uncertain=True,
            ) from exc

    @staticmethod
    def _confirmed_result(response: httpx.Response) -> Mapping[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "Telegram returned an invalid response.",
                provider="telegram",
                delivery_uncertain=True,
            ) from exc

        if not isinstance(body, dict):
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "Telegram returned an invalid response.",
                provider="telegram",
                delivery_uncertain=True,
            )
        if response.status_code == 401 or body.get("error_code") == 401:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_AUTH_FAILED,
                "Telegram rejected the configured bot credentials.",
                provider="telegram",
            )
        if response.status_code == 429 or body.get("error_code") == 429:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_RATE_LIMITED,
                "Telegram rate-limited the notification.",
                retryable=True,
                provider="telegram",
            )
        if not response.is_success or body.get("ok") is not True:
            if response.is_server_error:
                raise ReliefRouteError(
                    ErrorCode.UPSTREAM_UNAVAILABLE,
                    "Telegram could not confirm whether the message was delivered.",
                    retryable=True,
                    provider="telegram",
                    delivery_uncertain=True,
                )
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "Telegram rejected the dispatch message.",
                provider="telegram",
            )

        result = body.get("result")
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if (
            not isinstance(message_id, int)
            or isinstance(message_id, bool)
            or message_id <= 0
        ):
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "Telegram did not return a confirmed message ID.",
                provider="telegram",
                delivery_uncertain=True,
            )
        return {
            "status": "SENT",
            "provider_message_id": str(message_id),
        }
