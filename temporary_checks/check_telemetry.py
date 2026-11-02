"""Integration check for PostgreSQL telemetry using temporary real DB records."""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
from dotenv import load_dotenv

from services.telemetry import PostgreSQLTelemetryService
from shared.enums import ErrorCode
from shared.errors import ReliefRouteError
from shared.models import DriverLocation, LatLon

load_dotenv()


async def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing from .env")

    service = PostgreSQLTelemetryService(database_url)
    driver_id = f"telemetry-test-{uuid.uuid4().hex}"

    now = datetime.now(UTC)

    older = DriverLocation(
        driver_id=driver_id,
        location=LatLon(latitude=12.9716, longitude=77.5946),
        observed_at=now - timedelta(minutes=2),
        source="integration_test",
        accuracy_m=10,
        consented=True,
    )

    newer = DriverLocation(
        driver_id=driver_id,
        location=LatLon(latitude=12.9352, longitude=77.6245),
        observed_at=now,
        source="integration_test",
        accuracy_m=5,
        consented=True,
    )

    try:
        await service.record_location(older)
        await service.record_location(newer)

        latest = await service.latest_location(driver_id)

        assert latest is not None
        assert latest.driver_id == driver_id
        assert latest.location.latitude == newer.location.latitude
        assert latest.location.longitude == newer.location.longitude
        assert latest.source == "integration_test"

        print("PASS: location reports persisted.")
        print("PASS: latest location returned correctly.")

        nonconsented = DriverLocation(
            driver_id=driver_id,
            location=LatLon(latitude=12.9716, longitude=77.5946),
            observed_at=now,
            source="integration_test",
            consented=False,
        )

        try:
            await service.record_location(nonconsented)
            raise AssertionError("Non-consented location was unexpectedly accepted.")
        except ReliefRouteError as exc:
            assert exc.error.code == ErrorCode.VALIDATION_ERROR
            print("PASS: non-consented location rejected.")

        missing = await service.latest_location(
            f"missing-{uuid.uuid4().hex}"
        )
        assert missing is None
        print("PASS: missing location returns None.")

    finally:
        # Delete only this test's uniquely identified records.
        async with await psycopg.AsyncConnection.connect(
            database_url,
            connect_timeout=5,
        ) as connection:
            await connection.execute(
                """
                DELETE FROM driver_locations
                WHERE driver_id = %s
                """,
                (driver_id,),
            )

        print("Test records cleaned up.")


if __name__ == "__main__":
    # SelectorEventLoop avoids Psycopg's unsupported Proactor loop on Windows.
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)