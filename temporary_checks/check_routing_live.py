import asyncio

from shared.models import LatLon, RouteRequest
from services.routing import OSRMRoutingService


async def main():
    service = OSRMRoutingService()

    request = RouteRequest(
        origin=LatLon(
            latitude=12.9716,
            longitude=77.5946,
        ),
        destination=LatLon(
            latitude=13.0827,
            longitude=80.2707,
        ),
    )

    result = await service.calculate_safe_route(request)

    print("Provider:", result.provider)
    print(f"Distance: {result.distance_m / 1000:.2f} km")
    print(f"Duration: {result.duration_s / 60:.1f} minutes")
    print("Avoids requested polygons:", result.avoids_requested_polygons)
    print("Risk level:", result.risk_level)
    print("Warnings:")
    for warning in result.warnings:
        print("-", warning)

    print("Geometry available:", result.geometry is not None)


if __name__ == "__main__":
    asyncio.run(main())