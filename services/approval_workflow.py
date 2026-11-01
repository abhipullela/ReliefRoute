"""Approval, dispatch orchestration, and driver acknowledgement workflow."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any
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
    """Coordinate plan decisions, single-send dispatches, acknowledgements, and audit."""

    def __init__(self, *, plans, dispatches, audit) -> None:
        self.plans = plans
        self.dispatches = dispatches
        self.audit = audit

    async def decide(self, request: ApprovalRequest) -> DeliveryPlan:
        status = PlanStatus.APPROVED if request.approved else PlanStatus.REJECTED
        updated = await self.plans.transition_status(
            request.plan_id,
            status,
            expected_statuses=(PlanStatus.DRAFT, PlanStatus.NEEDS_APPROVAL),
        )
        if updated is None:
            current = await self._get_plan(request.plan_id)
            if current.status == status:
                return current
            raise ReliefRouteError(
                ErrorCode.CONFLICT,
                f"Plan cannot receive this approval decision while status is {current.status.value}.",
                provider="approval_workflow",
            )

        await self.audit.append(
            self._event(
                actor=request.approver_id,
                action="PLAN_APPROVED" if request.approved else "PLAN_REJECTED",
                plan=updated,
                outcome="SUCCESS",
                details={
                    "comment": request.comment,
                    "decided_at": request.decided_at.isoformat(),
                },
                occurred_at=request.decided_at,
            )
        )
        return updated

    async def dispatch(self, request: DispatchRequest, *, sender: Sender) -> DispatchResult:
        reservation = await self.dispatches.begin_attempt(request)
        if reservation is not None:
            return reservation

        validator = getattr(sender, "validate", None)
        try:
            if callable(validator):
                validation_result = validator(request)
                if inspect.isawaitable(validation_result):
                    await validation_result

            provider_result = await sender(request)
            if (
                not isinstance(provider_result, Mapping)
                or provider_result.get("status") != "SENT"
            ):
                raise ReliefRouteError(
                    ErrorCode.INVALID_UPSTREAM_RESPONSE,
                    "Notification provider did not confirm dispatch success.",
                    provider="notification",
                    delivery_uncertain=True,
                )
        except Exception as exc:
            if isinstance(exc, ReliefRouteError) and not exc.delivery_uncertain:
                await self.dispatches.fail_attempt(
                    request,
                    error={
                        "type": type(exc).__name__,
                        "message": exc.error.message,
                    },
                )
                await self.audit.append(
                    self._event(
                        actor="system",
                        action="PLAN_DISPATCH_FAILED",
                        plan=await self._get_plan(request.plan_id),
                        outcome="FAILURE",
                        details={
                            "driver_id": request.driver_id,
                            "error_type": type(exc).__name__,
                        },
                    )
                )
            else:
                await self.audit.append(
                    self._event(
                        actor="system",
                        action="PLAN_DISPATCH_UNRESOLVED",
                        plan=await self._get_plan(request.plan_id),
                        outcome="UNKNOWN",
                        details={
                            "driver_id": request.driver_id,
                            "error_type": type(exc).__name__,
                        },
                    )
                )
            raise

        result = await self.dispatches.complete_attempt(
            request,
            provider_message_id=provider_result.get("provider_message_id"),
        )
        plan = await self._get_plan(request.plan_id)
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
        first_acknowledgement = await self.dispatches.record_acknowledgement(ack)
        if first_acknowledgement:
            plan = await self._get_plan(ack.plan_id)
            await self.audit.append(
                self._event(
                    actor=ack.driver_id,
                    action=(
                        "DRIVER_ACKNOWLEDGED"
                        if ack.acknowledged
                        else "DRIVER_ACKNOWLEDGEMENT_NEGATIVE"
                    ),
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
            occurred_at=occurred_at or datetime.now(UTC),
            actor=actor,
            action=action,
            entity_type="delivery_plan",
            entity_id=plan.plan_id,
            outcome=outcome,
            details=details,
            source_refs=plan.source_refs,
        )
