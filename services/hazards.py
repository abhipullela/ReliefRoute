"""Rainfall-based hazard assessment using live weather forecasts.

Important:
- Rainfall risk is not proof of flooding or a road closure.
- This service does not fabricate hazard polygons.
- Missing or insufficient weather data results in UNKNOWN risk.
"""

from datetime import datetime, timezone
from uuid import uuid4

from shared.enums import ErrorCode, RiskLevel
from shared.errors import ReliefRouteError
from shared.models import HazardAssessment, WeatherObservation


PROVIDER_NAME = "Open-Meteo Forecast API"

# Initial rainfall screening thresholds, measured in mm/hour.
# These are configurable screening heuristics, not official flood warnings.
MODERATE_RAIN_MM_PER_HOUR = 2.5
HIGH_RAIN_MM_PER_HOUR = 7.5


class RainfallHazardService:
    """Assess forecast rainfall intensity without claiming confirmed flooding."""

    async def assess(
        self,
        observations: list[WeatherObservation],
    ) -> HazardAssessment:
        """Produce a transparent risk assessment from forecast observations."""

        if not observations:
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "At least one weather observation is required for hazard assessment.",
            )

        now = datetime.now(timezone.utc)

        # Forecast intervals must be timezone-aware and have positive duration.
        for observation in observations:
            start = observation.forecast_start
            end = observation.forecast_end

            if (
                start.tzinfo is None
                or start.utcoffset() is None
                or end.tzinfo is None
                or end.utcoffset() is None
            ):
                raise ReliefRouteError(
                    ErrorCode.VALIDATION_ERROR,
                    "Forecast timestamps must be timezone-aware.",
                )

            if end <= start:
                raise ReliefRouteError(
                    ErrorCode.INVALID_UPSTREAM_RESPONSE,
                    "A weather forecast interval has a non-positive duration.",
                )

            if observation.precipitation_mm < 0:
                raise ReliefRouteError(
                    ErrorCode.INVALID_UPSTREAM_RESPONSE,
                    "Precipitation cannot be negative.",
                )

        # Exclude forecasts that have entirely expired. Do not silently interpret
        # an old forecast as current evidence.
        current_or_future = [
            observation
            for observation in observations
            if observation.forecast_end.astimezone(timezone.utc) > now
        ]

        if not current_or_future:
            raise ReliefRouteError(
                ErrorCode.DATA_STALE,
                "All supplied weather forecast intervals have expired.",
            )

        # Convert interval totals into hourly rainfall rates. This avoids
        # treating, for example, 5 mm over 3 hours as 5 mm/hour.
        rainfall_rates: list[float] = []

        for observation in current_or_future:
            duration_hours = (
                observation.forecast_end - observation.forecast_start
            ).total_seconds() / 3600.0

            if duration_hours <= 0:
                raise ReliefRouteError(
                    ErrorCode.INVALID_UPSTREAM_RESPONSE,
                    "Cannot calculate rainfall rate for a non-positive interval.",
                )

            rainfall_rates.append(
                observation.precipitation_mm / duration_hours
            )

        peak_rate = max(rainfall_rates)

        if peak_rate >= HIGH_RAIN_MM_PER_HOUR:
            risk_level = RiskLevel.HIGH
            rationale = [
                f"Peak forecast rainfall intensity is {peak_rate:.2f} mm/hour.",
                (
                    f"This exceeds the configured high screening threshold of "
                    f"{HIGH_RAIN_MM_PER_HOUR:.2f} mm/hour."
                ),
            ]
        elif peak_rate >= MODERATE_RAIN_MM_PER_HOUR:
            risk_level = RiskLevel.MODERATE
            rationale = [
                f"Peak forecast rainfall intensity is {peak_rate:.2f} mm/hour.",
                (
                    f"This meets the configured moderate screening threshold of "
                    f"{MODERATE_RAIN_MM_PER_HOUR:.2f} mm/hour."
                ),
            ]
        else:
            risk_level = RiskLevel.LOW
            rationale = [
                f"Peak forecast rainfall intensity is {peak_rate:.2f} mm/hour.",
                (
                    "The forecast is below the configured rainfall screening "
                    "thresholds."
                ),
            ]

        rationale.append(
            f"Assessment uses {len(current_or_future)} forecast interval(s)."
        )

        # Preserve provenance from every contributing provider.
        sources = list(
            {
                (
                    observation.source.provider,
                    observation.source.url,
                    observation.source.retrieved_at,
                ): observation.source
                for observation in current_or_future
            }.values()
        )

        limitations = [
            "Risk level is a rainfall screening estimate, not an official flood warning.",
            "Rainfall forecasts do not confirm flooding, road closures, or road passability.",
            "No hazard polygons were generated because no authoritative hazard geometry was supplied.",
            "The configured rainfall thresholds are heuristics and require local validation.",
            "This assessment does not account for drainage, terrain, river levels, or historical flooding.",
        ]

        return HazardAssessment(
            assessment_id=str(uuid4()),
            generated_at=now,
            risk_level=risk_level,
            polygons=[],
            sources=sources,
            rationale=rationale,
            limitations=limitations,
        )