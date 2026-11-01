"""Approval, dispatch idempotency, provider failure, and acknowledgement tests."""

import asyncio
from datetime import UTC, datetime
from functools import wraps

import pytest

from services.approval_workflow import ApprovalDispatchWorkflow
from shared.enums import ErrorCode, PlanStatus
from shared.errors import ReliefRouteError
from shared.models import (
    ApprovalRequest,
    DeliveryPlan,
    DispatchRequest,
    DispatchResult,
    DriverAcknowledgement,
    LatLon,
)


def async_test(test):
    @wraps(test)
    def run(*args, **kwargs):
        asyncio.run(test(*args, **kwargs))

    return run


def make_plan(status: PlanStatus = PlanStatus.NEEDS_APPROVAL) -> DeliveryPlan:
    return DeliveryPlan(
        plan_id="plan-1",
        supplier_id="supplier-1",
        commodity="rice",
        quantity=10,
        unit="kg",
        origin=LatLon(latitude=12.0, longitude=77.0),
        destination=LatLon(latitude=12.1, longitude=77.1),
        hazard_assessment_id="hazard-1",
        status=status,
        idempotency_key="plan-key-1",
        rationale=["test fixture"],
    )


def make_dispatch(key: str = "dispatch-key-1") -> DispatchRequest:
    return DispatchRequest(
        plan_id="plan-1",
        driver_id="driver-1",
        telegram_chat_id="chat-1",
        message="Deliver supplies",
        idempotency_key=key,
    )


class FakePlans:
    def __init__(self, status: PlanStatus) -> None:
        self.plan = make_plan(status)
        self.lock = asyncio.Lock()

    async def get_plan(self, plan_id: str):
        return self.plan if self.plan.plan_id == plan_id else None

    async def transition_status(self, plan_id, status, *, expected_statuses):
        async with self.lock:
            if (
                self.plan.plan_id != plan_id
                or self.plan.status not in expected_statuses
            ):
                return None
            self.plan = self.plan.model_copy(update={"status": status})
            return self.plan


class FakeDispatches:
    def __init__(self, plans: FakePlans) -> None:
        self.plans = plans
        self.attempts: dict[str, dict] = {}
        self.acknowledgements: dict[str, DriverAcknowledgement] = {}
        self.lock = asyncio.Lock()

    async def begin_attempt(self, request):
        async with self.lock:
            existing = self.attempts.get(request.idempotency_key)
            if existing is not None:
                if existing["request"] != request:
                    raise ReliefRouteError(
                        ErrorCode.CONFLICT, "Idempotency key conflict."
                    )
                if existing["status"] == "SENT":
                    return existing["result"]
                raise ReliefRouteError(
                    ErrorCode.CONFLICT,
                    "Dispatch request already exists.",
                    retryable=existing["status"] == "SENDING",
                )
            if self.plans.plan.status != PlanStatus.APPROVED:
                raise ReliefRouteError(
                    ErrorCode.APPROVAL_REQUIRED, "Plan must be approved."
                )
            self.plans.plan = self.plans.plan.model_copy(
                update={"status": PlanStatus.DISPATCHING}
            )
            self.attempts[request.idempotency_key] = {
                "request": request,
                "status": "SENDING",
            }
            return None

    async def complete_attempt(self, request, *, provider_message_id):
        async with self.lock:
            attempt = self.attempts[request.idempotency_key]
            result = DispatchResult(
                dispatch_id="dispatch-1",
                plan_id=request.plan_id,
                provider_message_id=provider_message_id,
                status="SENT",
                attempted_at=datetime.now(UTC),
            )
            attempt.update(status="SENT", result=result)
            self.plans.plan = self.plans.plan.model_copy(
                update={"status": PlanStatus.DISPATCHED}
            )
            return result

    async def fail_attempt(self, request, *, error):
        async with self.lock:
            self.attempts[request.idempotency_key]["status"] = "FAILED"
            self.plans.plan = self.plans.plan.model_copy(
                update={"status": PlanStatus.APPROVED}
            )

    async def record_acknowledgement(self, ack):
        async with self.lock:
            if (
                self.plans.plan.status
                not in {
                    PlanStatus.DISPATCHED,
                    PlanStatus.ACKNOWLEDGED,
                    PlanStatus.IN_TRANSIT,
                }
                or not any(
                    attempt["status"] == "SENT"
                    and attempt["request"].plan_id == ack.plan_id
                    and attempt["request"].driver_id == ack.driver_id
                    for attempt in self.attempts.values()
                )
            ):
                raise ReliefRouteError(
                    ErrorCode.NOT_FOUND, "No confirmed matching dispatch."
                )
            previous = self.acknowledgements.get(ack.plan_id)
            if previous is not None:
                if (
                    previous.acknowledged == ack.acknowledged
                    and previous.message == ack.message
                ):
                    return False
                raise ReliefRouteError(
                    ErrorCode.CONFLICT, "Conflicting acknowledgement."
                )
            self.acknowledgements[ack.plan_id] = ack
            if (
                ack.acknowledged
                and self.plans.plan.status == PlanStatus.DISPATCHED
            ):
                self.plans.plan = self.plans.plan.model_copy(
                    update={"status": PlanStatus.ACKNOWLEDGED}
                )
            return True


class FakeAudit:
    def __init__(self) -> None:
        self.events = []

    async def append(self, event):
        self.events.append(event)


@pytest.fixture
def workflow_factory():
    def create(status=PlanStatus.NEEDS_APPROVAL):
        plans = FakePlans(status)
        dispatches = FakeDispatches(plans)
        audit = FakeAudit()
        return ApprovalDispatchWorkflow(
            plans=plans, dispatches=dispatches, audit=audit
        ), plans, dispatches, audit

    return create


@async_test
async def test_concurrent_same_approval_is_idempotent(workflow_factory):
    workflow, plans, _, audit = workflow_factory()
    request = ApprovalRequest(
        plan_id="plan-1", approved=True, approver_id="reviewer-1"
    )

    results = await asyncio.gather(workflow.decide(request), workflow.decide(request))

    assert all(result.status == PlanStatus.APPROVED for result in results)
    assert plans.plan.status == PlanStatus.APPROVED
    assert [event.action for event in audit.events] == ["PLAN_APPROVED"]


@async_test
async def test_conflicting_approval_decisions_do_not_overwrite(workflow_factory):
    workflow, plans, _, _ = workflow_factory()
    first = ApprovalRequest(
        plan_id="plan-1", approved=True, approver_id="reviewer-1"
    )
    opposing = first.model_copy(update={"approved": False})

    await workflow.decide(first)
    with pytest.raises(ReliefRouteError) as error:
        await workflow.decide(opposing)

    assert error.value.error.code == ErrorCode.CONFLICT
    assert plans.plan.status == PlanStatus.APPROVED


@async_test
async def test_concurrent_opposing_approvals_have_one_winner(workflow_factory):
    workflow, plans, _, _ = workflow_factory()
    approved = ApprovalRequest(
        plan_id="plan-1", approved=True, approver_id="reviewer-1"
    )
    rejected = approved.model_copy(update={"approved": False})

    results = await asyncio.gather(
        workflow.decide(approved),
        workflow.decide(rejected),
        return_exceptions=True,
    )

    assert sum(isinstance(result, DeliveryPlan) for result in results) == 1
    assert sum(isinstance(result, ReliefRouteError) for result in results) == 1
    assert plans.plan.status in {PlanStatus.APPROVED, PlanStatus.REJECTED}


@async_test
async def test_dispatch_requires_approval_before_sender_is_called(workflow_factory):
    workflow, _, dispatches, _ = workflow_factory(PlanStatus.DRAFT)
    calls = 0

    async def sender(_request):
        nonlocal calls
        calls += 1
        return {"status": "SENT", "provider_message_id": "message-1"}

    with pytest.raises(ReliefRouteError) as error:
        await workflow.dispatch(make_dispatch(), sender=sender)

    assert error.value.error.code == ErrorCode.APPROVAL_REQUIRED
    assert calls == 0
    assert dispatches.attempts == {}


@async_test
async def test_dispatch_idempotency_key_cannot_be_reused_for_another_request(
    workflow_factory,
):
    workflow, _, _, _ = workflow_factory(PlanStatus.APPROVED)
    calls = 0

    async def sender(_request):
        nonlocal calls
        calls += 1
        return {"status": "SENT", "provider_message_id": "message-1"}

    await workflow.dispatch(make_dispatch(), sender=sender)
    different_message = make_dispatch().model_copy(
        update={"message": "A different instruction"}
    )
    with pytest.raises(ReliefRouteError) as error:
        await workflow.dispatch(different_message, sender=sender)

    assert error.value.error.code == ErrorCode.CONFLICT
    assert calls == 1


@async_test
async def test_concurrent_dispatch_and_retry_send_once(workflow_factory):
    workflow, plans, _, _ = workflow_factory(PlanStatus.APPROVED)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def sender(_request):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"status": "SENT", "provider_message_id": "message-1"}

    first = asyncio.create_task(workflow.dispatch(make_dispatch(), sender=sender))
    await started.wait()
    with pytest.raises(ReliefRouteError):
        await workflow.dispatch(make_dispatch(), sender=sender)
    release.set()

    result = await first
    retry = await workflow.dispatch(make_dispatch(), sender=sender)

    assert calls == 1
    assert result.status == retry.status == "SENT"
    assert plans.plan.status == PlanStatus.DISPATCHED


@async_test
async def test_definitive_provider_failure_releases_plan_for_new_key(workflow_factory):
    workflow, plans, dispatches, _ = workflow_factory(PlanStatus.APPROVED)

    async def rejected(_request):
        raise ReliefRouteError(
            ErrorCode.UPSTREAM_AUTH_FAILED,
            "Telegram rejected credentials.",
            provider="telegram",
        )

    with pytest.raises(ReliefRouteError):
        await workflow.dispatch(make_dispatch(), sender=rejected)
    assert plans.plan.status == PlanStatus.APPROVED
    assert dispatches.attempts["dispatch-key-1"]["status"] == "FAILED"

    async def accepted(_request):
        return {"status": "SENT", "provider_message_id": "message-2"}

    result = await workflow.dispatch(
        make_dispatch("dispatch-key-2"), sender=accepted
    )
    assert result.status == "SENT"
    assert plans.plan.status == PlanStatus.DISPATCHED


@async_test
async def test_ambiguous_provider_failure_is_not_retried_or_reported_sent(
    workflow_factory,
):
    workflow, plans, dispatches, _ = workflow_factory(PlanStatus.APPROVED)
    calls = 0

    async def uncertain(_request):
        nonlocal calls
        calls += 1
        raise ReliefRouteError(
            ErrorCode.UPSTREAM_TIMEOUT,
            "Telegram delivery outcome is unknown.",
            retryable=True,
            provider="telegram",
            delivery_uncertain=True,
        )

    with pytest.raises(ReliefRouteError):
        await workflow.dispatch(make_dispatch(), sender=uncertain)
    assert plans.plan.status == PlanStatus.DISPATCHING
    assert dispatches.attempts["dispatch-key-1"]["status"] == "SENDING"

    with pytest.raises(ReliefRouteError):
        await workflow.dispatch(make_dispatch(), sender=uncertain)
    assert calls == 1
    assert plans.plan.status != PlanStatus.DISPATCHED


@async_test
async def test_acknowledgement_is_driver_bound_idempotent_and_preserves_transit(
    workflow_factory,
):
    workflow, plans, dispatches, audit = workflow_factory(PlanStatus.APPROVED)
    request = make_dispatch()
    await dispatches.begin_attempt(request)
    await dispatches.complete_attempt(request, provider_message_id="message-1")
    ack = DriverAcknowledgement(
        plan_id="plan-1",
        driver_id="driver-1",
        acknowledged=True,
        message="Received",
    )

    await workflow.acknowledge(ack)
    await workflow.acknowledge(ack.model_copy(update={"received_at": datetime.now(UTC)}))
    assert plans.plan.status == PlanStatus.ACKNOWLEDGED
    assert [event.action for event in audit.events].count("DRIVER_ACKNOWLEDGED") == 1

    plans.plan = plans.plan.model_copy(update={"status": PlanStatus.IN_TRANSIT})
    dispatches.acknowledgements.clear()
    await workflow.acknowledge(ack)
    assert plans.plan.status == PlanStatus.IN_TRANSIT

    wrong_driver = ack.model_copy(update={"driver_id": "driver-2"})
    with pytest.raises(ReliefRouteError):
        await workflow.acknowledge(wrong_driver)
