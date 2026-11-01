"""Unit tests for LangGraph state machine orchestration."""

import pytest

from agent.graph import build_agent_graph, create_agent_workflow
from agent.services import AgentServices
from agent.state import IncidentInfo, WorkflowStatus, create_initial_state
from shared.enums import ErrorCode, PlanStatus
from shared.errors import ReliefRouteError
from tests.conftest import MockSupplierService, MockWeatherService


def test_graph_build_and_compile(mock_services: AgentServices):
    """Verify that build_agent_graph and create_agent_workflow build and compile properly."""
    builder = build_agent_graph(mock_services)
    assert builder is not None
    workflow = create_agent_workflow(mock_services)
    assert workflow is not None


@pytest.mark.asyncio
async def test_graph_full_success_flow(
    sample_incident: IncidentInfo,
    mock_services: AgentServices,
):
    """Verify complete end-to-end workflow execution with valid mock services."""
    workflow = create_agent_workflow(mock_services)
    initial_state = create_initial_state(incident=sample_incident)

    result = await workflow.ainvoke(initial_state)

    # State transitions: START -> MONITOR -> ASSESS -> PLAN -> VALIDATE -> planning_success -> AWAIT_APPROVAL -> END
    assert result["workflow_status"] in (WorkflowStatus.VALIDATED, WorkflowStatus.AWAITING_APPROVAL)
    assert result["validation_results"] is not None
    assert result["validation_results"].is_valid is True
    assert len(result["validation_results"].errors) == 0

    # Verify weather observations were collected
    assert len(result["weather_observations"]) > 0

    # Verify hazard assessment was created
    assert result["hazard_assessment"] is not None

    # Verify supplier and inventory selection
    assert result["selected_supplier"] is not None
    assert result["selected_inventory"] is not None

    # Verify candidate route
    assert result["route"] is not None

    # Verify structured DeliveryPlan
    plan = result["delivery_plan"]
    assert plan is not None
    assert plan.status == PlanStatus.NEEDS_APPROVAL  # Ready for human approval gate
    assert plan.approval_required is True
    assert plan.commodity == sample_incident.commodity
    assert plan.quantity == sample_incident.required_quantity
    assert plan.origin == result["selected_supplier"].location
    assert plan.destination == sample_incident.destination
    assert plan.idempotency_key.startswith("plan_idem_")
    assert len(plan.rationale) >= 3
    assert len(plan.source_refs) >= 1


@pytest.mark.asyncio
async def test_graph_missing_incident_routes_to_needs_info(
    mock_services: AgentServices,
):
    """Verify workflow with missing incident information routes to needs_information."""
    workflow = create_agent_workflow(mock_services)
    initial_state = create_initial_state()  # No incident

    result = await workflow.ainvoke(initial_state)

    assert result["workflow_status"] == WorkflowStatus.NEEDS_INFO
    assert len(result["missing_info"]) > 0
    assert result["delivery_plan"] is None


@pytest.mark.asyncio
async def test_graph_no_eligible_supplier_routes_to_failure(
    sample_incident: IncidentInfo,
    mock_services: AgentServices,
):
    """Verify workflow routes to planning_failure when no supplier has sufficient stock."""
    # Replace supplier service with an empty one
    mock_services.supplier_service = MockSupplierService(suppliers_and_inventory=[])

    workflow = create_agent_workflow(mock_services)
    initial_state = create_initial_state(incident=sample_incident)

    result = await workflow.ainvoke(initial_state)

    assert result["workflow_status"] == WorkflowStatus.FAILED
    assert result["delivery_plan"] is None
    assert len(result["errors"]) > 0


@pytest.mark.asyncio
async def test_graph_weather_failure_handled_safely(
    sample_incident: IncidentInfo,
    mock_services: AgentServices,
):
    """Verify upstream weather failure degrades gracefully and does not crash the state machine."""
    mock_services.weather_service = MockWeatherService(
        error=ReliefRouteError(
            code=ErrorCode.UPSTREAM_TIMEOUT,
            message="Weather provider timeout",
            provider="open-meteo",
            retryable=True,
        )
    )

    workflow = create_agent_workflow(mock_services)
    initial_state = create_initial_state(incident=sample_incident)

    result = await workflow.ainvoke(initial_state)

    # Workflow degrades gracefully without unhandled exception
    assert any("Weather provider timeout" in err for err in result["errors"])
    assert result["workflow_status"] in (
        WorkflowStatus.FAILED,
        WorkflowStatus.DEGRADED,
        WorkflowStatus.NEEDS_INFO,
    )


@pytest.mark.asyncio
async def test_graph_idempotency_consistency(
    sample_incident: IncidentInfo,
    mock_services: AgentServices,
):
    """Verify that multiple workflow invocations with identical parameters yield identical idempotency keys."""
    workflow = create_agent_workflow(mock_services)

    state1 = create_initial_state(incident=sample_incident)
    res1 = await workflow.ainvoke(state1)

    state2 = create_initial_state(incident=sample_incident)
    res2 = await workflow.ainvoke(state2)

    assert res1["delivery_plan"] is not None
    assert res2["delivery_plan"] is not None
    assert res1["delivery_plan"].idempotency_key == res2["delivery_plan"].idempotency_key
