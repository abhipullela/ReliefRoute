"""Dependency injection container for backend services consumed by the agent.

Allows clean separation between Member A's orchestration and Member B's service
implementations (or mocks during isolated unit testing).
"""

from dataclasses import dataclass

from agent.planner import DefaultPlanningService
from shared.contracts import (
    HazardService,
    PlanningService,
    RoutingService,
    SupplierService,
    WeatherService,
)


@dataclass
class AgentServices:
    """Service interfaces consumed by the agent workflow."""

    weather_service: WeatherService | None = None
    hazard_service: HazardService | None = None
    supplier_service: SupplierService | None = None
    routing_service: RoutingService | None = None
    planning_service: PlanningService | None = None

    def get_planning_service(self) -> PlanningService:
        """Return injected planning service or default agent planning service."""
        if self.planning_service is not None:
            return self.planning_service
        return DefaultPlanningService()
