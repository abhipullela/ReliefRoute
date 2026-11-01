"""Planning service and DeliveryPlan generation for ReliefRoute.

Generates structured DeliveryPlan objects based on validated service outputs,
including deterministic idempotency keys, rationales, and complete source references.
"""

import hashlib
import uuid

from shared.enums import PlanStatus
from shared.models import (
    DeliveryPlan,
    HazardAssessment,
    InventoryItem,
    LatLon,
    RouteResult,
    SourceRef,
    Supplier,
    utc_now,
)


def compute_plan_idempotency_key(
    supplier_id: str,
    commodity: str,
    origin: LatLon,
    destination: LatLon,
    hazard_assessment_id: str,
) -> str:
    """Generate a deterministic idempotency key for a delivery plan."""
    payload = (
        f"{supplier_id}:{commodity.strip().lower()}:"
        f"{origin.latitude:.4f},{origin.longitude:.4f}:"
        f"{destination.latitude:.4f},{destination.longitude:.4f}:"
        f"{hazard_assessment_id}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"plan_idem_{digest}"


class DefaultPlanningService:
    """Default implementation of PlanningService Protocol for Member A's agent."""

    async def create_plan(
        self,
        *,
        supplier: Supplier,
        inventory: InventoryItem,
        origin: LatLon,
        destination: LatLon,
        hazard: HazardAssessment,
        route: RouteResult | None = None,
        requested_quantity: float | None = None,
        plan_id: str | None = None,
    ) -> DeliveryPlan:
        """Create a structured DeliveryPlan from validated supplier, inventory, route, and hazard data."""
        resolved_plan_id = plan_id or f"plan_{uuid.uuid4().hex[:12]}"

        # Delivery quantity cannot exceed available stock
        allocated_quantity = inventory.quantity
        if requested_quantity is not None and requested_quantity > 0:
            allocated_quantity = min(inventory.quantity, requested_quantity)

        idempotency_key = compute_plan_idempotency_key(
            supplier_id=supplier.supplier_id,
            commodity=inventory.commodity,
            origin=origin,
            destination=destination,
            hazard_assessment_id=hazard.assessment_id,
        )

        # Build clear, auditable rationale from service outputs
        rationale: list[str] = [
            f"Selected active supplier '{supplier.name}' ({supplier.supplier_id}) at ({origin.latitude}, {origin.longitude}).",
            f"Allocated {allocated_quantity} {inventory.unit} of '{inventory.commodity}' from available stock of {inventory.quantity} {inventory.unit}.",
            f"Evaluated hazard assessment '{hazard.assessment_id}' with risk level '{hazard.risk_level}'.",
        ]

        if hazard.limitations:
            rationale.append(f"Hazard limitations noted: {'; '.join(hazard.limitations)}")

        # Collect source references to ensure full audit provenance
        source_refs: list[SourceRef] = list(hazard.sources)

        if route is not None:
            rationale.append(
                f"Candidate route calculated via {route.provider}: "
                f"distance {route.distance_m:.0f}m, estimated duration {route.duration_s:.0f}s."
            )
            if hazard.polygons:
                status_str = "confirmed avoided" if route.avoids_requested_polygons else "NOT avoided"
                rationale.append(f"Hazard polygon avoidance: {status_str}.")
            if route.warnings:
                rationale.append(f"Route warnings: {'; '.join(route.warnings)}")

            if route.source not in source_refs:
                source_refs.append(route.source)

        return DeliveryPlan(
            plan_id=resolved_plan_id,
            created_at=utc_now(),
            supplier_id=supplier.supplier_id,
            commodity=inventory.commodity,
            quantity=allocated_quantity,
            unit=inventory.unit,
            origin=origin,
            destination=destination,
            route=route,
            hazard_assessment_id=hazard.assessment_id,
            status=PlanStatus.DRAFT,
            approval_required=True,
            idempotency_key=idempotency_key,
            rationale=rationale,
            source_refs=source_refs,
        )
