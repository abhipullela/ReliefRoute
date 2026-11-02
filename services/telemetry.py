"""PostgreSQL-backed driver GPS ingestion and retrieval."""

import os
from datetime import UTC

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from shared.enums import ErrorCode
from shared.errors import ReliefRouteError
from shared.models import DriverLocation

load_dotenv()


class PostgreSQLTelemetryService:
    """Persist consented driver locations and retrieve the latest location."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")

        if not self.database_url:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "DATABASE_URL is not configured.",
                provider="postgresql",
            )

    async def record_location(
        self, location: DriverLocation
    ) -> DriverLocation:
        """Persist a driver location only when consent and timestamp are valid."""

        if not location.consented:
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "Cannot record a driver location without consent.",
                provider="telemetry",
            )

        if not location.driver_id.strip():
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "driver_id cannot be empty.",
                provider="telemetry",
            )

        if location.observed_at.tzinfo is None or location.observed_at.utcoffset() is None:
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "observed_at must include a timezone.",
                provider="telemetry",
            )

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                await connection.execute(
                    """
                    INSERT INTO driver_locations (
                        driver_id,
                        latitude,
                        longitude,
                        observed_at,
                        source,
                        accuracy_m,
                        consented
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        location.driver_id,
                        location.location.latitude,
                        location.location.longitude,
                        location.observed_at.astimezone(UTC),
                        location.source,
                        location.accuracy_m,
                        location.consented,
                    ),
                )

            return location

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not persist the driver location.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def latest_location(
        self, driver_id: str
    ) -> DriverLocation | None:
        """Return the most recently observed location, or None if none exists."""

        if not driver_id.strip():
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "driver_id cannot be empty.",
                provider="telemetry",
            )

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                cursor = await connection.execute(
                    """
                    SELECT
                        driver_id,
                        latitude,
                        longitude,
                        observed_at,
                        source,
                        accuracy_m,
                        consented
                    FROM driver_locations
                    WHERE driver_id = %s
                    ORDER BY observed_at DESC, location_id DESC
                    LIMIT 1
                    """,
                    (driver_id,),
                )
                row = await cursor.fetchone()

            if row is None:
                return None

            return DriverLocation(
                driver_id=row["driver_id"],
                location={
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                },
                observed_at=row["observed_at"],
                source=row["source"],
                accuracy_m=row["accuracy_m"],
                consented=row["consented"],
            )

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not retrieve the latest driver location.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc