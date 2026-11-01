"""Approval, dispatch orchestration, and driver acknowledgement workflow.

This module orchestrates existing persistence services. It does not implement a
notification provider; callers must inject a sender that returns a mapping with
status="SENT" after the provider confirms acceptance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping
from uuid import uuid4

from shared.enums import ErrorCode, PlanStatus
from shared.errors import ReliefRouteError
from shared.models import (
    ApprovalRequest,
    AuditEvent,
    DeliveryPlan,
    DispatchRequest,
    DispatchResult,
    DriverAcknowledgement,
)

Sender = Callable[[DispatchRequest], Awaitable[Mapping[str, Any]]]


class ApprovalDispatchWorkflow:
    """Coordinate plan decisions, dispatch attempts, acknowledgements, and audit."""

    def __init__(self, *, plans, dispatches, audit) -> None:
        self.plans = plans
        self.dispatches = dispatches
        self.audit = audit

    async def decide(self, request: ApprovalRequest) -> DeliveryPlan:
        plan = await self._get_plan(request.plan_id)
        if plan.status not in (PlanStatus.DRAFT, PlanStatus.NEEDS_APPROVAL):
            raise ReliefRouteError(
                ErrorCode.CONFLICT,
                f"Plan cannot receive an approval decision while status is {plan.status.value}.",
                provider="approval_workflow",
            )

        status = PlanStatus.APPROVED if request.approved else PlanStatus.REJECTED
        updated = await self.plans.update_status(request.plan_id, status)
        await self.audit.append(
            self._event(
                actor=request.approver_id,
                action="PLAN_APPROVED" if request.approved else "PLAN_REJECTED",
                plan=updated,
                outcome="SUCCESS",
                details={"comment": request.comment, "decided_at": request.decided_at.isoformat()},
                occurred_at=request.decided_at,
            )
        )
        return updated

    async def dispatch(self, request: DispatchRequest, *, sender: Sender) -> DispatchResult:
        plan = await self._get_plan(request.plan_id)
        if plan.status != PlanStatus.APPROVED:
            raise ReliefRouteError(
                ErrorCode.APPROVAL_REQUIRED,
                "Plan must be approved before dispatch.",
                provider="approval_workflow",
                details={"plan_id": request.plan_id, "status": plan.status.value},
            )

        try:
            provider_result = await sender(request)
            if not isinstance(provider_result, Mapping) or provider_result.get("status") != "SENT":
                raise ReliefRouteError(
                    ErrorCode.INVALID_UPSTREAM_RESPONSE,
                    "Notification provider did not confirm dispatch success.",
                    provider="notification",
                )
        except Exception as exc:
            # Preserve the original provider exception for callers, but record the
            # failed attempt first. A persistence error here may supersede it.
            await self.dispatches.record_attempt(
                request,
                status="FAILED",
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            await self.audit.append(
                self._event(
                    actor="system",
                    action="PLAN_DISPATCH_FAILED",
                    plan=plan,
                    outcome="FAILURE",
                    details={"driver_id": request.driver_id, "error_type": type(exc).__name__},
                )
            )
            raise

        result = await self.dispatches.record_attempt(
            request,
            status="SENT",
            provider_message_id=provider_result.get("provider_message_id"),
        )
        await self.plans.update_status(request.plan_id, PlanStatus.DISPATCHED)
        await self.audit.append(
            self._event(
                actor="system",
                action="PLAN_DISPATCHED",
                plan=plan,
                outcome="SUCCESS",
                details={
                    "dispatch_id": result.dispatch_id,
                    "driver_id": request.driver_id,
                    "provider_message_id": result.provider_message_id,
                },
            )
        )
        return result

    async def acknowledge(self, ack: DriverAcknowledgement) -> DriverAcknowledgement:
        plan = await self._get_plan(ack.plan_id)
        if plan.status not in (PlanStatus.DISPATCHED, PlanStatus.ACKNOWLEDGED, PlanStatus.IN_TRANSIT):
            raise ReliefRouteError(
                ErrorCode.CONFLICT,
                "A driver acknowledgement requires a dispatched plan.",
                provider="approval_workflow",
                details={"plan_id": ack.plan_id, "status": plan.status.value},
            )

        # The concrete PostgreSQL service currently returns None; do not rely on
        # the conflicting return annotation in the shared Protocol.
        await self.dispatches.record_acknowledgement(ack)
        if ack.acknowledged and plan.status != PlanStatus.ACKNOWLEDGED:
            plan = await self.plans.update_status(ack.plan_id, PlanStatus.ACKNOWLEDGED)

        await self.audit.append(
            self._event(
                actor=ack.driver_id,
                action="DRIVER_ACKNOWLEDGED" if ack.acknowledged else "DRIVER_ACKNOWLEDGEMENT_NEGATIVE",
                plan=plan,
                outcome="SUCCESS",
                details={
                    "driver_id": ack.driver_id,
                    "acknowledged": ack.acknowledged,
                    "message": ack.message,
                    "received_at": ack.received_at.isoformat(),
                },
                occurred_at=ack.received_at,
            )
        )
        return ack

    async def _get_plan(self, plan_id: str) -> DeliveryPlan:
        plan = await self.plans.get_plan(plan_id)
        if plan is None:
            raise ReliefRouteError(
                ErrorCode.NOT_FOUND,
                f"Delivery plan '{plan_id}' was not found.",
                provider="approval_workflow",
            )
        return plan

    @staticmethod
    def _event(
        *,
        actor: str,
        action: str,
        plan: DeliveryPlan,
        outcome: str,
        details: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> AuditEvent:
        return AuditEvent(
            event_id=str(uuid4()),
            occurred_at=occurred_at or datetime.now(timezone.utc),
            actor=actor,
            action=action,
            entity_type="delivery_plan",
            entity_id=plan.plan_id,
            outcome=outcome,
            details=details,
            source_refs=plan.source_refs,
        )
