"""Live hourly precipitation forecasts from the Open-Meteo Forecast API."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from shared.enums import ErrorCode
from shared.errors import ReliefRouteError
from shared.models import LatLon, SourceRef, WeatherObservation


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
PROVIDER_NAME = "Open-Meteo Forecast API"


class OpenMeteoWeatherService:
    """Retrieve and validate real precipitation forecasts."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        if max_attempts < 1 or max_attempts > 3:
            raise ValueError("max_attempts must be between 1 and 3")

        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts

    async def get_forecast(
        self,
        location: LatLon,
        *,
        horizon_hours: int = 3,
    ) -> list[WeatherObservation]:
        """
        Return hourly precipitation forecasts for a location.

        Each observation represents one hourly forecast interval.
        Provider failures raise ReliefRouteError.
        """
        if not 1 <= horizon_hours <= 72:
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "horizon_hours must be between 1 and 72",
                provider=PROVIDER_NAME,
            )

        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": "precipitation",
            "forecast_hours": horizon_hours,
            "timezone": "UTC",
        }

        payload = await self._fetch(params)

        return self._parse_response(
            payload,
            location=location,
            horizon_hours=horizon_hours,
        )

    async def _fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch real data, retrying transient failures a bounded number of times."""

        for attempt in range(self.max_attempts):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds
                ) as client:
                    response = await client.get(
                        OPEN_METEO_URL,
                        params=params,
                    )

                if response.status_code == 429:
                    if attempt + 1 < self.max_attempts:
                        await asyncio.sleep(self._retry_delay(attempt))
                        continue

                    raise ReliefRouteError(
                        ErrorCode.UPSTREAM_RATE_LIMITED,
                        "Open-Meteo rate limit exceeded",
                        retryable=True,
                        provider=PROVIDER_NAME,
                    )

                if response.status_code in (401, 403):
                    raise ReliefRouteError(
                        ErrorCode.UPSTREAM_AUTH_FAILED,
                        "Open-Meteo rejected the request",
                        provider=PROVIDER_NAME,
                    )

                if response.status_code >= 500:
                    if attempt + 1 < self.max_attempts:
                        await asyncio.sleep(self._retry_delay(attempt))
                        continue

                    raise ReliefRouteError(
                        ErrorCode.UPSTREAM_UNAVAILABLE,
                        "Open-Meteo is temporarily unavailable",
                        retryable=True,
                        provider=PROVIDER_NAME,
                        details={"status_code": response.status_code},
                    )

                if response.is_error:
                    raise ReliefRouteError(
                        ErrorCode.INVALID_UPSTREAM_RESPONSE,
                        "Open-Meteo rejected the forecast request",
                        provider=PROVIDER_NAME,
                        details={"status_code": response.status_code},
                    )

                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ReliefRouteError(
                        ErrorCode.INVALID_UPSTREAM_RESPONSE,
                        "Open-Meteo returned invalid JSON",
                        provider=PROVIDER_NAME,
                    ) from exc

                if not isinstance(payload, dict):
                    raise ReliefRouteError(
                        ErrorCode.INVALID_UPSTREAM_RESPONSE,
                        "Expected a JSON object from Open-Meteo",
                        provider=PROVIDER_NAME,
                    )

                return payload

            except httpx.TimeoutException as exc:
                if attempt + 1 < self.max_attempts:
                    await asyncio.sleep(self._retry_delay(attempt))
                    continue

                raise ReliefRouteError(
                    ErrorCode.UPSTREAM_TIMEOUT,
                    "Timed out while requesting the weather forecast",
                    retryable=True,
                    provider=PROVIDER_NAME,
                ) from exc

            except httpx.RequestError as exc:
                if attempt + 1 < self.max_attempts:
                    await asyncio.sleep(self._retry_delay(attempt))
                    continue

                raise ReliefRouteError(
                    ErrorCode.UPSTREAM_UNAVAILABLE,
                    "Could not connect to the weather provider",
                    retryable=True,
                    provider=PROVIDER_NAME,
                ) from exc

        # Defensive guard: the loop should always return or raise.
        raise ReliefRouteError(
            ErrorCode.INTERNAL_ERROR,
            "Weather request ended unexpectedly",
            provider=PROVIDER_NAME,
        )

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        """Short bounded backoff for transient upstream failures."""
        return min(0.5 * (2**attempt), 2.0)

    @staticmethod
    def _parse_response(
        payload: dict[str, Any],
        *,
        location: LatLon,
        horizon_hours: int,
    ) -> list[WeatherObservation]:
        """Validate the provider response and convert it to shared models."""

        hourly = payload.get("hourly")

        if not isinstance(hourly, dict):
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "Forecast response is missing the hourly object",
                provider=PROVIDER_NAME,
            )

        times = hourly.get("time")
        precipitation = hourly.get("precipitation")

        if not isinstance(times, list) or not isinstance(
            precipitation, list
        ):
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "Forecast response is missing time or precipitation arrays",
                provider=PROVIDER_NAME,
            )

        if len(times) != len(precipitation):
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "Forecast time and precipitation arrays have different lengths",
                provider=PROVIDER_NAME,
            )

        if not times:
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "Forecast response contains no hourly observations",
                provider=PROVIDER_NAME,
            )

        retrieved_at = datetime.now(timezone.utc)
        observations: list[WeatherObservation] = []

        for index, (raw_time, raw_precipitation) in enumerate(
            zip(times, precipitation)
        ):
            if not isinstance(raw_time, str):
                raise ReliefRouteError(
                    ErrorCode.INVALID_UPSTREAM_RESPONSE,
                    "Forecast contains an invalid timestamp",
                    provider=PROVIDER_NAME,
                )

            try:
                forecast_start = datetime.fromisoformat(
                    raw_time.replace("Z", "+00:00")
                )

                # Open-Meteo may return naive timestamps when timezone=UTC.
                if forecast_start.tzinfo is None:
                    forecast_start = forecast_start.replace(
                        tzinfo=timezone.utc
                    )
                else:
                    forecast_start = forecast_start.astimezone(
                        timezone.utc
                    )

            except ValueError as exc:
                raise ReliefRouteError(
                    ErrorCode.INVALID_UPSTREAM_RESPONSE,
                    "Forecast contains an unparseable timestamp",
                    provider=PROVIDER_NAME,
                ) from exc

            # Missing measurements remain missing; never turn them into zero.
            if raw_precipitation is None:
                continue

            if (
                isinstance(raw_precipitation, bool)
                or not isinstance(raw_precipitation, (int, float))
                or raw_precipitation < 0
            ):
                raise ReliefRouteError(
                    ErrorCode.INVALID_UPSTREAM_RESPONSE,
                    "Forecast contains an invalid precipitation value",
                    provider=PROVIDER_NAME,
                )

            observations.append(
                WeatherObservation(
                    location=location,
                    forecast_start=forecast_start,
                    forecast_end=forecast_start + timedelta(hours=1),
                    precipitation_mm=float(raw_precipitation),
                    source=SourceRef(
                        provider=PROVIDER_NAME,
                        url=OPEN_METEO_URL,
                        retrieved_at=retrieved_at,
                        observed_at=None,
                        stale=False,
                        notes=(
                            "Hourly precipitation forecast; "
                            "not evidence of flooding or road closure."
                        ),
                    ),
                )
            )

        if not observations:
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "No usable precipitation measurements were returned",
                provider=PROVIDER_NAME,
            )

        return observations