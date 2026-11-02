"""Agent node functions for ReliefRoute LangGraph state machine.

Implements the MONITOR -> ASSESS -> PLAN -> VALIDATE pipeline (Phase 1) and the
AWAIT_APPROVAL -> DISPATCH -> VERIFY -> COMPLETE / REPLAN pipeline (Phase 2),
consuming Member B's service contracts through dependency injection and applying
strict deterministic guardrails.
"""

import asyncio
import random
import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig

from agent.guardrails import validate_incident, validate_plan_guardrails
from agent.services import AgentServices
from agent.state import (
    _NON_RETRYABLE_CODES,
    MAX_DISPATCH_ATTEMPTS,
    MAX_REPLAN_ATTEMPTS,
    AgentState,
    ValidationResult,
    WorkflowStatus,
)
from shared.enums import ErrorCode, ExtractionStatus, PlanStatus
from shared.errors import ReliefRouteError
from shared.models import (
    AuditEvent,
    DispatchRequest,
    ReportExtractionMetadata,
    RouteRequest,
    utc_now,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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


def _make_audit_event(
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    outcome: str,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Construct a structured AuditEvent."""
    return AuditEvent(
        event_id=str(uuid.uuid4()),
        occurred_at=utc_now(),
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        outcome=outcome,
        details=details or {},
    )


async def _emit_audit(
    svc: AgentServices,
    event: AuditEvent,
    state: AgentState,
) -> list[dict[str, Any]]:
    """Persist an AuditEvent via AuditService and accumulate in state audit_events.

    Never raises — audit failures are logged to errors but do not abort workflow.
    """
    existing: list[dict[str, Any]] = list(state.get("audit_events", []))
    serialised = event.model_dump(mode="json")
    existing.append(serialised)

    if svc.audit_service is not None:
        try:
            await svc.audit_service.append(event)
        except Exception as exc:  # noqa: BLE001
            existing.append(
                _make_audit_event(
                    actor="agent",
                    action="audit_write_failed",
                    entity_type="audit_event",
                    entity_id=event.event_id,
                    outcome="ERROR",
                    details={"error": str(exc)},
                ).model_dump(mode="json")
            )
    return existing


def _is_non_retryable(exc: ReliefRouteError) -> bool:
    """Return True if the error code must not be retried."""
    return exc.error.code in _NON_RETRYABLE_CODES


async def _with_retry(
    coro_factory: Any,
    *,
    max_attempts: int = MAX_DISPATCH_ATTEMPTS,
    base_delay_s: float = 0.5,
) -> Any:
    """Execute an async callable with bounded exponential backoff + jitter.

    Args:
        coro_factory: Zero-argument async callable returning the desired value.
        max_attempts: Total attempts including the initial one.
        base_delay_s: Base delay in seconds for exponential back-off.

    Raises:
        The last exception if all attempts are exhausted.
        Immediately re-raises non-retryable ReliefRouteErrors.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_factory()
        except ReliefRouteError as exc:
            if _is_non_retryable(exc):
                raise
            last_exc = exc
            if attempt < max_attempts:
                delay = base_delay_s * (2 ** (attempt - 1)) + random.uniform(0, 0.1)
                await asyncio.sleep(delay)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < max_attempts:
                delay = base_delay_s * (2 ** (attempt - 1)) + random.uniform(0, 0.1)
                await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Phase 1 nodes
# ---------------------------------------------------------------------------

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

    # Emit plan creation audit event (best-effort)
    audit_events = list(state.get("audit_events", []))
    plan_event = _make_audit_event(
        actor="agent",
        action="plan_created",
        entity_type="delivery_plan",
        entity_id=plan.plan_id,
        outcome="SUCCESS",
        details={
            "supplier_id": plan.supplier_id,
            "commodity": plan.commodity,
            "quantity": plan.quantity,
            "idempotency_key": plan.idempotency_key,
        },
    )
    audit_events.append(plan_event.model_dump(mode="json"))

    return {
        "available_suppliers": available_pairs,
        "selected_supplier": selected_supplier,
        "selected_inventory": selected_inventory,
        "route": route_result,
        "delivery_plan": plan,
        "sources": collected_sources,
        "audit_events": audit_events,
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

        # Emit validation audit event
        audit_events = list(state.get("audit_events", []))
        val_event = _make_audit_event(
            actor="agent",
            action="plan_validated",
            entity_type="delivery_plan",
            entity_id=plan.plan_id,
            outcome="SUCCESS",
            details={"warnings": validation_result.warnings},
        )
        audit_events.append(val_event.model_dump(mode="json"))

        return {
            "delivery_plan": plan,
            "validation_results": validation_result,
            "audit_events": audit_events,
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
    """Terminal state for successful planning and validation — awaiting human approval."""
    return {
        "workflow_status": WorkflowStatus.VALIDATED,
        "updated_at": utc_now().isoformat(),
    }


def needs_info_node(state: AgentState) -> dict[str, Any]:
    """Terminal state when essential information is missing."""

    missing_info = list(state.get("missing_info", []))

    # Check whether the workflow has received any initial input.
    if state.get("incident") is None and state.get("citizen_report") is None:
        missing_info.append("incident or citizen_report")

    return {
        "workflow_status": WorkflowStatus.NEEDS_INFO,
        "missing_info": missing_info,
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


# ---------------------------------------------------------------------------
# Phase 2 nodes
# ---------------------------------------------------------------------------

async def await_approval_node(
    state: AgentState,
    config: RunnableConfig | None = None,
    *,
    services: AgentServices | None = None,
) -> dict[str, Any]:
    """AWAIT_APPROVAL node: Validate and record human approval decision.

    Requires an ``ApprovalRequest`` already present on the state (injected by the
    operator interface before invoking this node).  The node does NOT poll for a
    decision — it validates the decision that has been placed in the state.

    Approval is invalidated whenever a replan has occurred (approval_request will
    be None after replanning), forcing a fresh decision for each new plan.
    """
    svc = _resolve_services(config, services)
    plan = state.get("delivery_plan")
    approval_request = state.get("approval_request")
    audit_events = list(state.get("audit_events", []))

    # Guard: plan must exist and be in NEEDS_APPROVAL status
    if plan is None:
        err = "Approval cannot be processed: no delivery plan in state"
        return {
            "errors": state.get("errors", []) + [err],
            "workflow_status": WorkflowStatus.FAILED,
            "updated_at": utc_now().isoformat(),
        }

    if plan.status != PlanStatus.NEEDS_APPROVAL:
        err = f"Approval cannot be processed: plan status is '{plan.status}', expected NEEDS_APPROVAL"
        return {
            "errors": state.get("errors", []) + [err],
            "workflow_status": WorkflowStatus.FAILED,
            "updated_at": utc_now().isoformat(),
        }

    # Guard: an explicit human decision must be present
    if approval_request is None:
        # No decision yet — remain in awaiting state
        audit_event = _make_audit_event(
            actor="agent",
            action="approval_requested",
            entity_type="delivery_plan",
            entity_id=plan.plan_id,
            outcome="PENDING",
        )
        audit_events.append(audit_event.model_dump(mode="json"))
        # Persist event best-effort
        if svc.audit_service is not None:
            try:
                await svc.audit_service.append(audit_event)
            except Exception:  # noqa: BLE001
                pass
        return {
            "audit_events": audit_events,
            "workflow_status": WorkflowStatus.AWAITING_APPROVAL,
            "updated_at": utc_now().isoformat(),
        }

    # Validate the approval: approver_id must be non-empty (no self-approval by agent)
    if not approval_request.approver_id or approval_request.approver_id.strip() == "":
        err = "Approval rejected: approver_id is missing or empty"
        audit_event = _make_audit_event(
            actor="agent",
            action="approval_validation_failed",
            entity_type="delivery_plan",
            entity_id=plan.plan_id,
            outcome="ERROR",
            details={"reason": err},
        )
        audit_events.append(audit_event.model_dump(mode="json"))
        return {
            "errors": state.get("errors", []) + [err],
            "audit_events": audit_events,
            "workflow_status": WorkflowStatus.FAILED,
            "updated_at": utc_now().isoformat(),
        }

    # Validate plan_id matches the current plan
    if approval_request.plan_id != plan.plan_id:
        err = (
            f"Approval rejected: approval plan_id '{approval_request.plan_id}' "
            f"does not match current plan '{plan.plan_id}'"
        )
        audit_event = _make_audit_event(
            actor=approval_request.approver_id,
            action="approval_validation_failed",
            entity_type="delivery_plan",
            entity_id=plan.plan_id,
            outcome="ERROR",
            details={"reason": err},
        )
        audit_events.append(audit_event.model_dump(mode="json"))
        return {
            "errors": state.get("errors", []) + [err],
            "audit_events": audit_events,
            "workflow_status": WorkflowStatus.FAILED,
            "updated_at": utc_now().isoformat(),
        }

    if approval_request.approved:
        # Human approved
        approved_plan = plan.model_copy(update={"status": PlanStatus.APPROVED})
        audit_event = _make_audit_event(
            actor=approval_request.approver_id,
            action="plan_approved",
            entity_type="delivery_plan",
            entity_id=plan.plan_id,
            outcome="APPROVED",
            details={
                "comment": approval_request.comment,
                "decided_at": approval_request.decided_at.isoformat(),
            },
        )
        audit_events.append(audit_event.model_dump(mode="json"))
        if svc.audit_service is not None:
            try:
                await svc.audit_service.append(audit_event)
            except Exception:  # noqa: BLE001
                pass
        return {
            "delivery_plan": approved_plan,
            "audit_events": audit_events,
            "workflow_status": WorkflowStatus.APPROVED,
            "updated_at": utc_now().isoformat(),
        }
    else:
        # Human rejected
        rejected_plan = plan.model_copy(update={"status": PlanStatus.REJECTED})
        audit_event = _make_audit_event(
            actor=approval_request.approver_id,
            action="plan_rejected",
            entity_type="delivery_plan",
            entity_id=plan.plan_id,
            outcome="REJECTED",
            details={
                "comment": approval_request.comment,
                "decided_at": approval_request.decided_at.isoformat(),
            },
        )
        audit_events.append(audit_event.model_dump(mode="json"))
        if svc.audit_service is not None:
            try:
                await svc.audit_service.append(audit_event)
            except Exception:  # noqa: BLE001
                pass
        return {
            "delivery_plan": rejected_plan,
            "audit_events": audit_events,
            "workflow_status": WorkflowStatus.REJECTED,
            "updated_at": utc_now().isoformat(),
        }


def route_after_approval(state: AgentState) -> str:
    """Conditional router following the approval decision."""
    status = state.get("workflow_status")
    if status == WorkflowStatus.APPROVED:
        return "dispatch"
    elif status == WorkflowStatus.AWAITING_APPROVAL:
        return "approval_pending"
    elif status == WorkflowStatus.REJECTED:
        return "approval_rejected"
    else:
        # FAILED or any invalid/stale approval state
        return "approval_failed"


async def dispatch_node(
    state: AgentState,
    config: RunnableConfig | None = None,
    *,
    services: AgentServices | None = None,
) -> dict[str, Any]:
    """DISPATCH node: Send one idempotent dispatch for an approved plan.

    Implements:
    - Pre-dispatch safety checks (plan must be APPROVED, no prior dispatch for same key)
    - Bounded retries with exponential backoff + jitter (max 3 total attempts)
    - No retry on auth/validation errors
    - Idempotency: uses plan's idempotency_key; never re-sends after ambiguous timeout
    - Audit events for attempt, success, and failure
    """
    svc = _resolve_services(config, services)
    audit_events = list(state.get("audit_events", []))
    plan = state.get("delivery_plan")

    # Safety: plan must exist and be APPROVED
    if plan is None:
        err = "Dispatch blocked: no delivery plan in state"
        return {
            "errors": state.get("errors", []) + [err],
            "workflow_status": WorkflowStatus.DISPATCH_FAILED,
            "updated_at": utc_now().isoformat(),
        }

    if plan.status != PlanStatus.APPROVED:
        err = f"Dispatch blocked: plan status is '{plan.status}', must be APPROVED"
        audit_event = _make_audit_event(
            actor="agent",
            action="dispatch_blocked",
            entity_type="delivery_plan",
            entity_id=plan.plan_id,
            outcome="BLOCKED",
            details={"reason": err},
        )
        audit_events.append(audit_event.model_dump(mode="json"))
        return {
            "errors": state.get("errors", []) + [err],
            "audit_events": audit_events,
            "workflow_status": WorkflowStatus.DISPATCH_FAILED,
            "updated_at": utc_now().isoformat(),
        }

    if svc.dispatch_service is None:
        err = "DispatchService provider is not configured"
        return {
            "errors": state.get("errors", []) + [err],
            "audit_events": audit_events,
            "workflow_status": WorkflowStatus.DISPATCH_FAILED,
            "updated_at": utc_now().isoformat(),
        }

    # Validate required dispatch fields
    incident = state.get("incident")
    selected_supplier = state.get("selected_supplier")
    if incident is None or selected_supplier is None:
        err = "Dispatch blocked: incident or selected_supplier is missing from state"
        return {
            "errors": state.get("errors", []) + [err],
            "audit_events": audit_events,
            "workflow_status": WorkflowStatus.DISPATCH_FAILED,
            "updated_at": utc_now().isoformat(),
        }

    dispatch_request = DispatchRequest(
        plan_id=plan.plan_id,
        driver_id=selected_supplier.contact_handle,
        message=(
            f"RELIEF DISPATCH — Plan {plan.plan_id}: "
            f"deliver {plan.quantity} {plan.unit} of {plan.commodity} "
            f"to ({plan.destination.latitude:.4f}, {plan.destination.longitude:.4f}). "
            f"Follow safe route. Acknowledge receipt."
        ),
        idempotency_key=plan.idempotency_key,
    )

    attempts = state.get("dispatch_attempts", 0)

    # Emit attempt audit event
    attempt_num = attempts + 1
    attempt_event = _make_audit_event(
        actor="agent",
        action="dispatch_attempt",
        entity_type="delivery_plan",
        entity_id=plan.plan_id,
        outcome="IN_PROGRESS",
        details={
            "attempt": attempt_num,
            "idempotency_key": plan.idempotency_key,
            "driver_id": dispatch_request.driver_id,
        },
    )
    audit_events.append(attempt_event.model_dump(mode="json"))

    # Attempt dispatch with bounded retries
    remaining_attempts = MAX_DISPATCH_ATTEMPTS - attempts
    if remaining_attempts <= 0:
        err = f"Dispatch failed: max attempts ({MAX_DISPATCH_ATTEMPTS}) exhausted"
        fail_event = _make_audit_event(
            actor="agent",
            action="dispatch_failed",
            entity_type="delivery_plan",
            entity_id=plan.plan_id,
            outcome="FAILED",
            details={"reason": err},
        )
        audit_events.append(fail_event.model_dump(mode="json"))
        return {
            "errors": state.get("errors", []) + [err],
            "audit_events": audit_events,
            "dispatch_attempts": attempts,
            "workflow_status": WorkflowStatus.DISPATCH_FAILED,
            "updated_at": utc_now().isoformat(),
        }

    last_error: str | None = None
    result = None
    attempts_made = 0
    for attempt in range(1, remaining_attempts + 1):
        attempts_made = attempt
        try:
            result = await svc.dispatch_service.dispatch(dispatch_request)
            break
        except ReliefRouteError as exc:
            last_error = f"Dispatch error ({exc.error.code}): {exc.error.message}"
            if _is_non_retryable(exc):
                break
            if attempt < remaining_attempts:
                delay = 0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.1)
                await asyncio.sleep(delay)
            # Record retry audit event
            retry_event = _make_audit_event(
                actor="agent",
                action="dispatch_retry",
                entity_type="delivery_plan",
                entity_id=plan.plan_id,
                outcome="RETRYING",
                details={"attempt": attempts + attempt, "error": last_error},
            )
            audit_events.append(retry_event.model_dump(mode="json"))
        except Exception as exc:  # noqa: BLE001
            last_error = f"Unexpected dispatch error: {exc!s}"
            if attempt < remaining_attempts:
                delay = 0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.1)
                await asyncio.sleep(delay)
            retry_event = _make_audit_event(
                actor="agent",
                action="dispatch_retry",
                entity_type="delivery_plan",
                entity_id=plan.plan_id,
                outcome="RETRYING",
                details={"attempt": attempts + attempt, "error": last_error},
            )
            audit_events.append(retry_event.model_dump(mode="json"))

    total_attempts = attempts + attempts_made

    if result is not None and result.status == "SENT":
        dispatched_plan = plan.model_copy(update={"status": PlanStatus.DISPATCHED})
        success_event = _make_audit_event(
            actor="agent",
            action="dispatch_success",
            entity_type="delivery_plan",
            entity_id=plan.plan_id,
            outcome="SUCCESS",
            details={
                "dispatch_id": result.dispatch_id,
                "provider_message_id": result.provider_message_id,
                "attempt": total_attempts,
            },
        )
        audit_events.append(success_event.model_dump(mode="json"))
        if svc.audit_service is not None:
            try:
                await svc.audit_service.append(success_event)
            except Exception:  # noqa: BLE001
                pass
        return {
            "delivery_plan": dispatched_plan,
            "dispatch_result": result,
            "dispatch_attempts": total_attempts,
            "audit_events": audit_events,
            "workflow_status": WorkflowStatus.DISPATCHED,
            "updated_at": utc_now().isoformat(),
        }

    # All retries exhausted or non-retryable error
    err_msg = last_error or "Dispatch failed: unknown error"
    fail_event = _make_audit_event(
        actor="agent",
        action="dispatch_failed",
        entity_type="delivery_plan",
        entity_id=plan.plan_id,
        outcome="FAILED",
        details={"reason": err_msg, "total_attempts": total_attempts},
    )
    audit_events.append(fail_event.model_dump(mode="json"))
    if svc.audit_service is not None:
        try:
            await svc.audit_service.append(fail_event)
        except Exception:  # noqa: BLE001
            pass

    failed_plan = plan.model_copy(update={"status": PlanStatus.FAILED})
    return {
        "delivery_plan": failed_plan,
        "dispatch_attempts": total_attempts,
        "errors": state.get("errors", []) + [err_msg],
        "audit_events": audit_events,
        "workflow_status": WorkflowStatus.DISPATCH_FAILED,
        "updated_at": utc_now().isoformat(),
    }


def route_after_dispatch(state: AgentState) -> str:
    """Conditional router following dispatch execution."""
    status = state.get("workflow_status")
    if status == WorkflowStatus.DISPATCHED:
        return "verify"
    else:
        return "dispatch_failed"


async def verify_node(
    state: AgentState,
    config: RunnableConfig | None = None,
    *,
    services: AgentServices | None = None,
) -> dict[str, Any]:
    """VERIFY node: Check driver acknowledgement and decide next step.

    If no acknowledgement is present the plan is marked SENT_UNACKNOWLEDGED and
    the operator is notified via an audit event.  If route conditions have
    changed since planning, triggers a bounded replan.
    """
    svc = _resolve_services(config, services)
    audit_events = list(state.get("audit_events", []))
    plan = state.get("delivery_plan")
    dispatch_result = state.get("dispatch_result")

    if plan is None or dispatch_result is None:
        err = "Verify node: missing delivery plan or dispatch result"
        return {
            "errors": state.get("errors", []) + [err],
            "workflow_status": WorkflowStatus.FAILED,
            "updated_at": utc_now().isoformat(),
        }

    # Check if plan requires replanning (e.g. hazard conditions changed)
    # For the Phase 2 implementation, replan triggers are driven externally by
    # setting plan.status = PlanStatus.REPLAN_REQUIRED before invoking verify.
    if plan.status == PlanStatus.REPLAN_REQUIRED:
        replan_count = state.get("replan_count", 0) + 1
        if replan_count > MAX_REPLAN_ATTEMPTS:
            err = f"Replan limit ({MAX_REPLAN_ATTEMPTS}) exceeded; manual operator intervention required"
            fail_event = _make_audit_event(
                actor="agent",
                action="replan_limit_exceeded",
                entity_type="delivery_plan",
                entity_id=plan.plan_id,
                outcome="FAILED",
                details={"replan_count": replan_count},
            )
            audit_events.append(fail_event.model_dump(mode="json"))
            return {
                "errors": state.get("errors", []) + [err],
                "audit_events": audit_events,
                "replan_count": replan_count,
                "workflow_status": WorkflowStatus.FAILED,
                "updated_at": utc_now().isoformat(),
            }

        replan_event = _make_audit_event(
            actor="agent",
            action="replan_triggered",
            entity_type="delivery_plan",
            entity_id=plan.plan_id,
            outcome="REPLANNING",
            details={"replan_count": replan_count, "reason": "plan.status == REPLAN_REQUIRED"},
        )
        audit_events.append(replan_event.model_dump(mode="json"))
        if svc.audit_service is not None:
            try:
                await svc.audit_service.append(replan_event)
            except Exception:  # noqa: BLE001
                pass

        # Invalidate approval so a fresh decision is required for the new plan
        return {
            "delivery_plan": None,
            "approval_request": None,
            "dispatch_result": None,
            "dispatch_attempts": 0,
            "audit_events": audit_events,
            "replan_count": replan_count,
            "workflow_status": WorkflowStatus.REPLANNING,
            "updated_at": utc_now().isoformat(),
        }

    # No replan needed — mark delivery complete
    complete_plan = plan.model_copy(update={"status": PlanStatus.COMPLETED})
    complete_event = _make_audit_event(
        actor="agent",
        action="delivery_completed",
        entity_type="delivery_plan",
        entity_id=plan.plan_id,
        outcome="COMPLETED",
        details={"dispatch_id": dispatch_result.dispatch_id},
    )
    audit_events.append(complete_event.model_dump(mode="json"))
    if svc.audit_service is not None:
        try:
            await svc.audit_service.append(complete_event)
        except Exception:  # noqa: BLE001
            pass

    return {
        "delivery_plan": complete_plan,
        "audit_events": audit_events,
        "workflow_status": WorkflowStatus.COMPLETED,
        "updated_at": utc_now().isoformat(),
    }


def route_after_verify(state: AgentState) -> str:
    """Conditional router following verify node."""
    status = state.get("workflow_status")
    if status == WorkflowStatus.COMPLETED:
        return "completed"
    elif status == WorkflowStatus.REPLANNING:
        return "replan"
    else:
        return "verify_failed"


async def replan_node(
    state: AgentState,
    config: RunnableConfig | None = None,
    *,
    services: AgentServices | None = None,
) -> dict[str, Any]:
    """REPLAN node: Reset state for a new planning cycle preserving history.

    Clears plan-specific fields while preserving incident, location, audit
    history, and replan_count.  The new cycle must pass through MONITOR ->
    ASSESS -> PLAN -> VALIDATE -> AWAIT_APPROVAL before dispatching again.

    Approval is always invalidated on replan: the new plan requires fresh
    human sign-off.
    """
    audit_events = list(state.get("audit_events", []))
    replan_count = state.get("replan_count", 0)

    replan_event = _make_audit_event(
        actor="agent",
        action="replan_started",
        entity_type="workflow",
        entity_id=state.get("incident").incident_id if state.get("incident") else "unknown",
        outcome="REPLANNING",
        details={"replan_count": replan_count},
    )
    audit_events.append(replan_event.model_dump(mode="json"))

    # Preserve incident/location; reset all plan-lifecycle fields
    return {
        "weather_observations": [],
        "hazard_assessment": None,
        "available_suppliers": [],
        "selected_supplier": None,
        "selected_inventory": None,
        "route": None,
        "delivery_plan": None,
        "validation_results": None,
        "approval_request": None,      # Force fresh approval on new plan
        "dispatch_result": None,
        "dispatch_attempts": 0,
        "errors": [],
        "missing_info": [],
        "audit_events": audit_events,
        "workflow_status": WorkflowStatus.INITIALIZED,
        "updated_at": utc_now().isoformat(),
    }


async def execute_node(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Legacy EXECUTE stub — superseded by dispatch_node in Phase 2.

    Kept for backward compatibility with Phase 1 graph references.
    """
    raise ReliefRouteError(
        code=ErrorCode.APPROVAL_REQUIRED,
        message="dispatch_node must be used; execute_node is a legacy Phase 1 stub.",
        provider="agent_dispatch",
    )


def rejected_node(state: AgentState) -> dict[str, Any]:
    """Terminal state when a plan is rejected by a human approver."""
    return {
        "workflow_status": WorkflowStatus.REJECTED,
        "updated_at": utc_now().isoformat(),
    }


def approval_pending_node(state: AgentState) -> dict[str, Any]:
    """Terminal state when no human decision has been provided yet."""
    return {
        "workflow_status": WorkflowStatus.AWAITING_APPROVAL,
        "updated_at": utc_now().isoformat(),
    }


def dispatch_failed_node(state: AgentState) -> dict[str, Any]:
    """Terminal state when all dispatch attempts are exhausted."""
    return {
        "workflow_status": WorkflowStatus.DISPATCH_FAILED,
        "updated_at": utc_now().isoformat(),
    }


def completed_node(state: AgentState) -> dict[str, Any]:
    """Terminal state for a successfully completed delivery."""
    return {
        "workflow_status": WorkflowStatus.COMPLETED,
        "updated_at": utc_now().isoformat(),
    }
async def extract_report_node(state: AgentState) -> dict:
    """Extract structured emergency information from a citizen report."""

    report = state.get("citizen_report")

    if report is None:
        return {
            "workflow_status": WorkflowStatus.NEEDS_INFO,
            "errors": state.get("errors", []) + [
                "Citizen report is missing."
            ],
        }

    try:
        extracted = await extract_emergency_report(report)

        metadata = ReportExtractionMetadata(
            report_id=report.report_id,
            provider="Groq",
            model=settings.groq_model,
            status=ExtractionStatus.SUCCEEDED,
        )

        return {
            "extracted_report": extracted,
            "extraction_metadata": metadata,
            "updated_at": utc_now().isoformat(),
        }

    except Exception as error:
        metadata = ReportExtractionMetadata(
            report_id=report.report_id,
            provider="Groq",
            model=settings.groq_model,
            status=ExtractionStatus.FAILED,
            errors=[str(error)],
        )

        return {
            "extraction_metadata": metadata,
            "workflow_status": WorkflowStatus.FAILED,
            "errors": state.get("errors", []) + [
                "Emergency report extraction failed."
            ],
        }


def validate_report_node(state: AgentState) -> dict:
    """Validate extracted emergency information."""

    extracted = state.get("extracted_report")

    if extracted is None:
        return {
            "workflow_status": WorkflowStatus.NEEDS_INFO,
            "errors": state.get("errors", []) + [
                "No extracted emergency report is available."
            ],
        }

    validation = validate_emergency_report(extracted)

    return {
        "report_validation": validation,
        "missing_info": validation.clarification_fields,
        "workflow_status": (
            WorkflowStatus.NEEDS_INFO
            if not validation.structurally_valid
            else WorkflowStatus.MONITORED
        ),
        "updated_at": utc_now().isoformat(),
    }