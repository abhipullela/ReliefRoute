"""Agent node functions for ReliefRoute LangGraph state machine.

Implements the MONITOR -> ASSESS -> PLAN -> VALIDATE pipeline, consuming
Member B's service contracts through dependency injection and applying
strict deterministic guardrails.
"""

from typing import Any

from langchain_core.runnables import RunnableConfig

from agent.guardrails import validate_incident, validate_plan_guardrails
from agent.services import AgentServices
from agent.state import AgentState, ValidationResult, WorkflowStatus
from shared.enums import ErrorCode, PlanStatus
from shared.errors import ReliefRouteError
from shared.models import (
    RouteRequest,
    utc_now,
)


def _resolve_services(
    config: RunnableConfig | None = None,
    services: AgentServices | None = None,
) -> AgentServices:
    """Resolve services from direct parameter or LangGraph RunnableConfig."""
    if services is not None:
        return services
    if config and isinstance(config, dict):
        configurable = config.get("configurable", {})
        if isinstance(configurable, dict) and "services" in configurable:
            svc = configurable["services"]
            if isinstance(svc, AgentServices):
                return svc
    return AgentServices()


async def monitor_node(
    state: AgentState,
    config: RunnableConfig | None = None,
    *,
    services: AgentServices | None = None,
) -> dict[str, Any]:
    """MONITOR node: Fetch weather observations for the target location."""
    svc = _resolve_services(config, services)

    # Resolve location: state.location or incident destination
    location = state.get("location")
    incident = state.get("incident")
    if location is None and incident is not None:
        location = incident.destination

    if location is None:
        return {
            "errors": state.get("errors", []) + ["Location is required for weather monitoring"],
            "missing_info": state.get("missing_info", []) + ["location"],
            "workflow_status": WorkflowStatus.NEEDS_INFO,
            "updated_at": utc_now().isoformat(),
        }

    if svc.weather_service is None:
        return {
            "errors": state.get("errors", []) + ["WeatherService provider is not configured"],
            "workflow_status": WorkflowStatus.DEGRADED,
            "updated_at": utc_now().isoformat(),
        }

    try:
        observations = await svc.weather_service.get_forecast(location=location, horizon_hours=3)
    except ReliefRouteError as exc:
        return {
            "errors": state.get("errors", [])
            + [f"Weather service failure ({exc.error.code}): {exc.error.message}"],
            "workflow_status": WorkflowStatus.DEGRADED,
            "updated_at": utc_now().isoformat(),
        }
    except Exception as exc:  # noqa: BLE001 - Safely capture unexpected provider failures to prevent crashing
        return {
            "errors": state.get("errors", []) + [f"Unexpected weather service error: {exc!s}"],
            "workflow_status": WorkflowStatus.DEGRADED,
            "updated_at": utc_now().isoformat(),
        }

    # Collect source references to ensure audit provenance
    collected_sources = list(state.get("sources", []))
    for obs in observations:
        if obs.source not in collected_sources:
            collected_sources.append(obs.source)

    return {
        "location": location,
        "weather_observations": observations,
        "sources": collected_sources,
        "workflow_status": WorkflowStatus.MONITORED,
        "updated_at": utc_now().isoformat(),
    }


async def assess_node(
    state: AgentState,
    config: RunnableConfig | None = None,
    *,
    services: AgentServices | None = None,
) -> dict[str, Any]:
    """ASSESS node: Evaluate weather observations and generate structured hazard assessment."""
    svc = _resolve_services(config, services)

    # Do not overwrite upstream degraded or failure status
    current_status = state.get("workflow_status")
    if current_status in (WorkflowStatus.DEGRADED, WorkflowStatus.NEEDS_INFO, WorkflowStatus.FAILED):
        return {
            "errors": state.get("errors", []) + ["Hazard assessment skipped due to upstream monitoring failure"],
            "workflow_status": current_status,
            "updated_at": utc_now().isoformat(),
        }

    if svc.hazard_service is None:
        return {
            "errors": state.get("errors", []) + ["HazardService provider is not configured"],
            "workflow_status": WorkflowStatus.DEGRADED,
            "updated_at": utc_now().isoformat(),
        }

    observations = state.get("weather_observations", [])

    try:
        assessment = await svc.hazard_service.assess(observations=observations)
    except ReliefRouteError as exc:
        return {
            "errors": state.get("errors", [])
            + [f"Hazard assessment failure ({exc.error.code}): {exc.error.message}"],
            "workflow_status": WorkflowStatus.DEGRADED,
            "updated_at": utc_now().isoformat(),
        }
    except Exception as exc:  # noqa: BLE001 - Safely capture unexpected provider failures to prevent crashing
        return {
            "errors": state.get("errors", []) + [f"Unexpected hazard service error: {exc!s}"],
            "workflow_status": WorkflowStatus.DEGRADED,
            "updated_at": utc_now().isoformat(),
        }

    # Collect assessment sources
    collected_sources = list(state.get("sources", []))
    for src in assessment.sources:
        if src not in collected_sources:
            collected_sources.append(src)

    return {
        "hazard_assessment": assessment,
        "sources": collected_sources,
        "workflow_status": WorkflowStatus.ASSESSED,
        "updated_at": utc_now().isoformat(),
    }


async def plan_node(
    state: AgentState,
    config: RunnableConfig | None = None,
    *,
    services: AgentServices | None = None,
) -> dict[str, Any]:
    """PLAN node: Discover eligible suppliers, check inventory, compute route, and build DeliveryPlan."""
    svc = _resolve_services(config, services)

    # Do not attempt planning if upstream monitoring or assessment is degraded or failed
    current_status = state.get("workflow_status")
    if current_status in (WorkflowStatus.DEGRADED, WorkflowStatus.NEEDS_INFO, WorkflowStatus.FAILED):
        return {
            "errors": state.get("errors", []) + ["Planning aborted: upstream workflow is in a degraded or failed state"],
            "workflow_status": current_status,
            "updated_at": utc_now().isoformat(),
        }

    incident = state.get("incident")
    if incident is None:
        return {
            "errors": state.get("errors", [])
            + ["Planning cannot proceed: incident information is missing"],
            "missing_info": state.get("missing_info", []) + ["incident"],
            "workflow_status": WorkflowStatus.NEEDS_INFO,
            "updated_at": utc_now().isoformat(),
        }

    # 1. Discover suppliers
    if svc.supplier_service is None:
        return {
            "errors": state.get("errors", []) + ["SupplierService provider is not configured"],
            "workflow_status": WorkflowStatus.NO_FEASIBLE_PLAN,
            "updated_at": utc_now().isoformat(),
        }

    try:
        available_pairs = await svc.supplier_service.list_available(
            commodity=incident.commodity,
            min_quantity=incident.required_quantity,
        )
    except ReliefRouteError as exc:
        return {
            "errors": state.get("errors", [])
            + [f"Supplier service failure ({exc.error.code}): {exc.error.message}"],
            "workflow_status": WorkflowStatus.NO_FEASIBLE_PLAN,
            "updated_at": utc_now().isoformat(),
        }
    except Exception as exc:  # noqa: BLE001 - Safely capture unexpected provider failures to prevent crashing
        return {
            "errors": state.get("errors", []) + [f"Unexpected supplier service error: {exc!s}"],
            "workflow_status": WorkflowStatus.NO_FEASIBLE_PLAN,
            "updated_at": utc_now().isoformat(),
        }

    # Filter for active suppliers, supplier_reported source, fresh stock, and sufficient quantity
    now = utc_now()
    eligible_pairs = [
        (s, inv)
        for s, inv in available_pairs
        if s.active
        and inv.source == "supplier_reported"
        and inv.commodity.strip().lower() == incident.commodity.strip().lower()
        and inv.quantity >= incident.required_quantity
        and (inv.expires_at is None or inv.expires_at > now)
    ]

    if not eligible_pairs:
        return {
            "available_suppliers": available_pairs,
            "errors": state.get("errors", [])
            + [
                (
                    f"No eligible active suppliers with fresh stock for '{incident.commodity}' "
                    f"(required: {incident.required_quantity} {incident.unit})"
                )
            ],
            "workflow_status": WorkflowStatus.NO_FEASIBLE_PLAN,
            "updated_at": utc_now().isoformat(),
        }

    selected_supplier, selected_inventory = eligible_pairs[0]

    # 2. Compute route
    if svc.routing_service is None:
        return {
            "available_suppliers": available_pairs,
            "selected_supplier": selected_supplier,
            "selected_inventory": selected_inventory,
            "errors": state.get("errors", []) + ["RoutingService provider is not configured"],
            "workflow_status": WorkflowStatus.NO_FEASIBLE_PLAN,
            "updated_at": utc_now().isoformat(),
        }

    hazard = state.get("hazard_assessment")
    avoid_polygons = hazard.polygons if hazard else []

    route_request = RouteRequest(
        origin=selected_supplier.location,
        destination=incident.destination,
        avoid_polygons=avoid_polygons,
    )

    try:
        route_result = await svc.routing_service.calculate_safe_route(route_request)
    except ReliefRouteError as exc:
        return {
            "available_suppliers": available_pairs,
            "selected_supplier": selected_supplier,
            "selected_inventory": selected_inventory,
            "errors": state.get("errors", [])
            + [f"Routing service failure ({exc.error.code}): {exc.error.message}"],
            "workflow_status": WorkflowStatus.NO_FEASIBLE_PLAN,
            "updated_at": utc_now().isoformat(),
        }
    except Exception as exc:  # noqa: BLE001 - Safely capture unexpected provider failures to prevent crashing
        return {
            "available_suppliers": available_pairs,
            "selected_supplier": selected_supplier,
            "selected_inventory": selected_inventory,
            "errors": state.get("errors", []) + [f"Unexpected routing service error: {exc!s}"],
            "workflow_status": WorkflowStatus.NO_FEASIBLE_PLAN,
            "updated_at": utc_now().isoformat(),
        }

    # 3. Create DeliveryPlan
    if hazard is None:
        return {
            "available_suppliers": available_pairs,
            "selected_supplier": selected_supplier,
            "selected_inventory": selected_inventory,
            "route": route_result,
            "errors": state.get("errors", [])
            + ["Cannot generate DeliveryPlan without hazard assessment"],
            "workflow_status": WorkflowStatus.NO_FEASIBLE_PLAN,
            "updated_at": utc_now().isoformat(),
        }

    planner = svc.get_planning_service()
    try:
        plan = await planner.create_plan(
            supplier=selected_supplier,
            inventory=selected_inventory,
            origin=selected_supplier.location,
            destination=incident.destination,
            hazard=hazard,
        )
    except ReliefRouteError as exc:
        return {
            "available_suppliers": available_pairs,
            "selected_supplier": selected_supplier,
            "selected_inventory": selected_inventory,
            "route": route_result,
            "errors": state.get("errors", [])
            + [f"Planning failure ({exc.error.code}): {exc.error.message}"],
            "workflow_status": WorkflowStatus.NO_FEASIBLE_PLAN,
            "updated_at": utc_now().isoformat(),
        }

    # Enrich plan with calculated route, allocated quantity, rationale, and sources
    enriched_rationale = list(plan.rationale)
    enriched_sources = list(plan.source_refs)

    if route_result is not None:
        enriched_rationale.append(
            f"Candidate route calculated via {route_result.provider}: "
            f"distance {route_result.distance_m:.0f}m, estimated duration {route_result.duration_s:.0f}s."
        )
        if hazard.polygons:
            status_str = "confirmed avoided" if route_result.avoids_requested_polygons else "NOT avoided"
            enriched_rationale.append(f"Hazard polygon avoidance: {status_str}.")
        if route_result.warnings:
            enriched_rationale.append(f"Route warnings: {'; '.join(route_result.warnings)}")
        if route_result.source not in enriched_sources:
            enriched_sources.append(route_result.source)

    allocated_quantity = min(selected_inventory.quantity, incident.required_quantity)
    plan = plan.model_copy(
        update={
            "route": route_result,
            "quantity": allocated_quantity,
            "rationale": enriched_rationale,
            "source_refs": enriched_sources,
        }
    )

    # Merge sources
    collected_sources = list(state.get("sources", []))
    for src in plan.source_refs:
        if src not in collected_sources:
            collected_sources.append(src)

    return {
        "available_suppliers": available_pairs,
        "selected_supplier": selected_supplier,
        "selected_inventory": selected_inventory,
        "route": route_result,
        "delivery_plan": plan,
        "sources": collected_sources,
        "workflow_status": WorkflowStatus.PLANNED,
        "updated_at": utc_now().isoformat(),
    }


def validate_node(
    state: AgentState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """VALIDATE node: Run deterministic guardrails on state and DeliveryPlan."""
    current_status = state.get("workflow_status")

    # 1. If already degraded from upstream provider failure, preserve degraded status
    if current_status == WorkflowStatus.DEGRADED:
        degraded_errors = list(state.get("errors", []))
        if not any("degraded" in e.lower() for e in degraded_errors):
            degraded_errors.append("Validation blocked: upstream weather data is degraded")
        val_res = ValidationResult(
            is_valid=False,
            errors=degraded_errors,
            warnings=[],
            checked_at=utc_now(),
        )
        return {
            "validation_results": val_res,
            "workflow_status": WorkflowStatus.DEGRADED,
            "updated_at": utc_now().isoformat(),
        }

    # 2. If already marked NO_FEASIBLE_PLAN, this is a planning failure
    if current_status == WorkflowStatus.NO_FEASIBLE_PLAN:
        val_res = ValidationResult(
            is_valid=False,
            errors=state.get("errors", []) + ["No feasible delivery plan could be constructed"],
            warnings=[],
            checked_at=utc_now(),
        )
        return {
            "validation_results": val_res,
            "workflow_status": WorkflowStatus.FAILED,
            "updated_at": utc_now().isoformat(),
        }

    # 3. Check for genuinely missing essential inputs (incident, destination, commodity)
    incident = state.get("incident")
    missing_items = state.get("missing_info", [])
    incident_errors = validate_incident(incident)

    if bool(missing_items) or bool(incident_errors):
        all_missing_errors = list(state.get("errors", [])) + incident_errors
        val_res = ValidationResult(
            is_valid=False,
            errors=all_missing_errors,
            warnings=[],
            checked_at=utc_now(),
        )
        return {
            "validation_results": val_res,
            "errors": all_missing_errors,
            "workflow_status": WorkflowStatus.NEEDS_INFO,
            "updated_at": utc_now().isoformat(),
        }

    # 4. Run full deterministic guardrails
    validation_result = validate_plan_guardrails(state)

    plan = state.get("delivery_plan")
    if validation_result.is_valid and plan is not None:
        if plan.status == PlanStatus.DRAFT:
            plan = plan.model_copy(update={"status": PlanStatus.NEEDS_APPROVAL})

        return {
            "delivery_plan": plan,
            "validation_results": validation_result,
            "workflow_status": WorkflowStatus.VALIDATED,
            "updated_at": utc_now().isoformat(),
        }

    # Guardrail check failed (route, stock, plan integrity, or missing plan) -> FAILED
    return {
        "validation_results": validation_result,
        "errors": state.get("errors", []) + validation_result.errors,
        "workflow_status": WorkflowStatus.FAILED,
        "updated_at": utc_now().isoformat(),
    }


def route_after_validation(state: AgentState) -> str:
    """Conditional router selecting the next state following guardrail validation."""
    status = state.get("workflow_status")
    if status == WorkflowStatus.VALIDATED:
        return "planning_success"
    elif status == WorkflowStatus.NEEDS_INFO:
        return "needs_information"
    else:
        return "planning_failure"


def planning_success_node(state: AgentState) -> dict[str, Any]:
    """Terminal state for successful planning and validation."""
    return {
        "workflow_status": WorkflowStatus.VALIDATED,
        "updated_at": utc_now().isoformat(),
    }


def needs_info_node(state: AgentState) -> dict[str, Any]:
    """Terminal state when essential information is missing."""
    return {
        "workflow_status": WorkflowStatus.NEEDS_INFO,
        "updated_at": utc_now().isoformat(),
    }


def planning_failure_node(state: AgentState) -> dict[str, Any]:
    """Terminal state when planning fails or is blocked by guardrails."""
    current_status = state.get("workflow_status")
    final_status = (
        current_status
        if current_status in (WorkflowStatus.DEGRADED, WorkflowStatus.FAILED)
        else WorkflowStatus.FAILED
    )
    return {
        "workflow_status": final_status,
        "updated_at": utc_now().isoformat(),
    }


async def execute_node(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """EXECUTE node placeholder: Architectural stub for Phase 2.

    Explicitly blocks unauthorized autonomous dispatch per docs/09.
    """
    raise ReliefRouteError(
        code=ErrorCode.APPROVAL_REQUIRED,
        message="Phase 1 safety policy: dispatch execution requires explicit human approval and is not authorized in this phase.",
        provider="agent_dispatch",
    )


async def verify_node(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """VERIFY node placeholder: Architectural stub for Phase 2 driver verification."""
    raise ReliefRouteError(
        code=ErrorCode.INTERNAL_ERROR,
        message="Verify node is reserved for Phase 2 delivery telemetry and driver acknowledgement verification.",
        provider="agent_verify",
    )
