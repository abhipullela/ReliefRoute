import asyncio

from shared.models import LatLon
from services.weather import OpenMeteoWeatherService


async def main() -> None:
    service = OpenMeteoWeatherService()

    # Bengaluru coordinates for this live API connectivity check.
    location = LatLon(
        latitude=12.9716,
        longitude=77.5946,
    )

    observations = await service.get_forecast(
        location,
        horizon_hours=3,
    )

    print(f"Provider: {observations[0].source.provider}")
    print(f"Observations received: {len(observations)}")

    for observation in observations:
        print(
            f"Start: {observation.forecast_start.isoformat()} | "
            f"End: {observation.forecast_end.isoformat()} | "
            f"Precipitation: {observation.precipitation_mm} mm"
        )


if __name__ == "__main__":
    asyncio.run(main())