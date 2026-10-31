"""Unit tests for individual agent node functions."""

import pytest

from agent.nodes import (
    assess_node,
    execute_node,
    monitor_node,
    plan_node,
    route_after_validation,
    validate_node,
    verify_node,
)
from agent.services import AgentServices
from agent.state import IncidentInfo, WorkflowStatus, create_initial_state
from shared.enums import ErrorCode, PlanStatus
from shared.errors import ReliefRouteError
from shared.models import (
    DeliveryPlan,
    HazardAssessment,
    InventoryItem,
    RouteResult,
    SourceRef,
    Supplier,
    WeatherObservation,
)
from tests.conftest import (
    MockHazardService,
    MockRoutingService,
    MockSupplierService,
    MockWeatherService,
)


@pytest.mark.asyncio
async def test_monitor_node_success(
    sample_incident: IncidentInfo,
    sample_weather_observations: list[WeatherObservation],
):
    """Verify monitor_node retrieves observations and advances status to MONITORED."""
    state = create_initial_state(incident=sample_incident)
    services = AgentServices(
        weather_service=MockWeatherService(sample_weather_observations)
    )

    update = await monitor_node(state, services=services)
    assert update["workflow_status"] == WorkflowStatus.MONITORED
    assert len(update["weather_observations"]) == len(sample_weather_observations)
    assert len(update["sources"]) >= 1


@pytest.mark.asyncio
async def test_monitor_node_missing_location():
    """Verify monitor_node returns NEEDS_INFO when neither location nor incident is present."""
    state = create_initial_state()  # No location, no incident
    services = AgentServices(weather_service=MockWeatherService([]))

    update = await monitor_node(state, services=services)
    assert update["workflow_status"] == WorkflowStatus.NEEDS_INFO
    assert "location" in update["missing_info"]


@pytest.mark.asyncio
async def test_monitor_node_weather_failure(sample_incident: IncidentInfo):
    """Verify monitor_node safely catches ReliefRouteError and marks DEGRADED."""
    error = ReliefRouteError(
        code=ErrorCode.UPSTREAM_TIMEOUT,
        message="Open-Meteo connection timed out",
        provider="open-meteo",
        retryable=True,
    )
    services = AgentServices(weather_service=MockWeatherService(error=error))
    state = create_initial_state(incident=sample_incident)

    update = await monitor_node(state, services=services)
    assert update["workflow_status"] == WorkflowStatus.DEGRADED
    assert any("Open-Meteo connection timed out" in err for err in update["errors"])


@pytest.mark.asyncio
async def test_assess_node_success(
    sample_hazard_assessment: HazardAssessment,
    sample_weather_observations: list[WeatherObservation],
):
    """Verify assess_node produces hazard assessment and advances status to ASSESSED."""
    state = create_initial_state()
    state["weather_observations"] = sample_weather_observations
    services = AgentServices(hazard_service=MockHazardService(sample_hazard_assessment))

    update = await assess_node(state, services=services)
    assert update["workflow_status"] == WorkflowStatus.ASSESSED
    assert update["hazard_assessment"] == sample_hazard_assessment
    assert len(update["sources"]) >= 1


@pytest.mark.asyncio
async def test_assess_node_service_unconfigured():
    """Verify assess_node marks DEGRADED when hazard service is not configured."""
    state = create_initial_state()
    services = AgentServices()  # No hazard_service

    update = await assess_node(state, services=services)
    assert update["workflow_status"] == WorkflowStatus.DEGRADED
    assert any("HazardService provider is not configured" in err for err in update["errors"])


@pytest.mark.asyncio
async def test_plan_node_success(
    sample_incident: IncidentInfo,
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
    sample_hazard_assessment: HazardAssessment,
    sample_route_result: RouteResult,
):
    """Verify plan_node selects supplier, computes route, and creates DeliveryPlan."""
    state = create_initial_state(incident=sample_incident)
    state["hazard_assessment"] = sample_hazard_assessment

    services = AgentServices(
        supplier_service=MockSupplierService([(sample_supplier, sample_inventory)]),
        routing_service=MockRoutingService(sample_route_result),
    )

    update = await plan_node(state, services=services)
    assert update["workflow_status"] == WorkflowStatus.PLANNED
    assert update["selected_supplier"] == sample_supplier
    assert update["selected_inventory"] == sample_inventory
    assert update["route"] == sample_route_result
    assert update["delivery_plan"] is not None
    assert update["delivery_plan"].status == PlanStatus.DRAFT


@pytest.mark.asyncio
async def test_plan_node_no_eligible_supplier(
    sample_incident: IncidentInfo,
    sample_hazard_assessment: HazardAssessment,
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
):
    """Verify plan_node returns NO_FEASIBLE_PLAN when inventory is insufficient."""
    low_inventory = sample_inventory.model_copy(update={"quantity": 5.0})  # Needed 100.0
    state = create_initial_state(incident=sample_incident)
    state["hazard_assessment"] = sample_hazard_assessment

    services = AgentServices(
        supplier_service=MockSupplierService([(sample_supplier, low_inventory)]),
        routing_service=MockRoutingService(),
    )

    update = await plan_node(state, services=services)
    assert update["workflow_status"] == WorkflowStatus.NO_FEASIBLE_PLAN
    assert any("No eligible active suppliers" in err for err in update["errors"])


@pytest.mark.asyncio
async def test_plan_node_routing_error(
    sample_incident: IncidentInfo,
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
    sample_hazard_assessment: HazardAssessment,
):
    """Verify plan_node safely handles routing provider failures."""
    error = ReliefRouteError(
        code=ErrorCode.UPSTREAM_UNAVAILABLE,
        message="Routing engine unreachable",
        provider="openrouteservice",
    )
    services = AgentServices(
        supplier_service=MockSupplierService([(sample_supplier, sample_inventory)]),
        routing_service=MockRoutingService(error=error),
    )

    state = create_initial_state(incident=sample_incident)
    state["hazard_assessment"] = sample_hazard_assessment

    update = await plan_node(state, services=services)
    assert update["workflow_status"] == WorkflowStatus.NO_FEASIBLE_PLAN
    assert any("Routing engine unreachable" in err for err in update["errors"])


def test_validate_node_valid_plan(
    sample_incident: IncidentInfo,
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
    sample_hazard_assessment: HazardAssessment,
    sample_route_result: RouteResult,
    sample_source_ref: SourceRef,
):
    """Verify validate_node transitions DRAFT plan to NEEDS_APPROVAL upon valid guardrails check."""
    plan = DeliveryPlan(
        plan_id="plan_123",
        supplier_id=sample_supplier.supplier_id,
        commodity=sample_incident.commodity,
        quantity=sample_incident.required_quantity,
        unit=sample_incident.unit,
        origin=sample_supplier.location,
        destination=sample_incident.destination,
        route=sample_route_result,
        hazard_assessment_id=sample_hazard_assessment.assessment_id,
        status=PlanStatus.DRAFT,
        approval_required=True,
        idempotency_key="plan_idem_123",
        rationale=["Valid plan"],
        source_refs=[sample_source_ref],
    )

    state = create_initial_state(incident=sample_incident)
    state["hazard_assessment"] = sample_hazard_assessment
    state["selected_supplier"] = sample_supplier
    state["selected_inventory"] = sample_inventory
    state["route"] = sample_route_result
    state["delivery_plan"] = plan

    update = validate_node(state)
    assert update["workflow_status"] == WorkflowStatus.VALIDATED
    assert update["delivery_plan"].status == PlanStatus.NEEDS_APPROVAL


def test_validate_node_invalid_missing_info():
    """Verify validate_node marks NEEDS_INFO when essential input is missing."""
    state = create_initial_state()  # Blank state

    update = validate_node(state)
    assert update["workflow_status"] == WorkflowStatus.NEEDS_INFO
    assert len(update["errors"]) > 0


def test_route_after_validation():
    """Verify route_after_validation returns appropriate branch keys."""
    assert route_after_validation({"workflow_status": WorkflowStatus.VALIDATED}) == "planning_success"
    assert route_after_validation({"workflow_status": WorkflowStatus.NEEDS_INFO}) == "needs_information"
    assert route_after_validation({"workflow_status": WorkflowStatus.FAILED}) == "planning_failure"
    assert route_after_validation({"workflow_status": WorkflowStatus.BLOCKED}) == "planning_failure"


@pytest.mark.asyncio
async def test_execute_node_blocks_unauthorized():
    """Verify execute_node blocks autonomous dispatch with APPROVAL_REQUIRED error."""
    state = create_initial_state()
    with pytest.raises(ReliefRouteError) as exc_info:
        await execute_node(state)
    assert exc_info.value.error.code == ErrorCode.APPROVAL_REQUIRED


@pytest.mark.asyncio
async def test_verify_node_placeholder():
    """Verify verify_node handles uninitialized state safely."""
    state = create_initial_state()
    result = await verify_node(state)
    assert result["workflow_status"] == WorkflowStatus.FAILED
    assert any("missing" in err.lower() for err in result.get("errors", []))
