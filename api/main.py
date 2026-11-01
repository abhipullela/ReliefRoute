"""ReliefRoute API: supplier, inventory, telemetry, plans, approval and dispatch."""

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import Field

from agent.citizen_reports import CitizenReportAgent
from services.approval_workflow import ApprovalDispatchWorkflow
from services.audit import PostgreSQLAuditService
from services.citizen_reports import PostgreSQLCitizenReportStore
from services.dispatch import PostgreSQLDispatchService
from services.genai import OpenAICompatibleTriageProvider
from services.plans import PostgreSQLPlanningStore
from services.suppliers import PostgreSQLSupplierService
from services.telemetry import PostgreSQLTelemetryService
from shared.enums import ErrorCode
from shared.errors import ReliefRouteError
from shared.models import (
    ApprovalRequest,
    CitizenReport,
    CitizenReportSubmission,
    ContractModel,
    DeliveryPlan,
    DispatchRequest,
    DispatchResult,
    DriverAcknowledgement,
    DriverLocation,
    InventoryItem,
    LatLon,
    ReportTriageStatus,
    Supplier,
    utc_now,
)

load_dotenv()


async def _unconfigured_notification_sender(_request: DispatchRequest) -> dict[str, Any]:
    """Fail honestly until a real notification provider is configured."""
    raise ReliefRouteError(
        ErrorCode.UPSTREAM_UNAVAILABLE,
        "Dispatch notification provider is not configured.",
        provider="notification",
        details={"required_configuration": "notification sender"},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create service objects once per application process."""
    database_url = os.getenv("DATABASE_URL")
    app.state.database_url = database_url
    app.state.suppliers = PostgreSQLSupplierService(database_url) if database_url else None
    app.state.telemetry = PostgreSQLTelemetryService(database_url) if database_url else None
    app.state.plans = PostgreSQLPlanningStore(database_url) if database_url else None
    app.state.dispatches = PostgreSQLDispatchService(database_url) if database_url else None
    app.state.audit = PostgreSQLAuditService(database_url) if database_url else None
    app.state.citizen_report_store = (
        PostgreSQLCitizenReportStore(database_url) if database_url else None
    )
    app.state.citizen_report_agent = (
        CitizenReportAgent(
            store=app.state.citizen_report_store,
            triage_provider=OpenAICompatibleTriageProvider(),
            audit=app.state.audit,
        )
        if database_url
        else None
    )
    app.state.approval_workflow = (
        ApprovalDispatchWorkflow(
            plans=app.state.plans,
            dispatches=app.state.dispatches,
            audit=app.state.audit,
        )
        if database_url
        else None
    )
    # Replace this callable with a real provider implementation when available.
    # Keeping it injectable also makes provider behavior testable.
    app.state.notification_sender = _unconfigured_notification_sender
    yield


app = FastAPI(title="ReliefRoute API", version="0.2.0", lifespan=lifespan)


class InventorySubmission(ContractModel):
    """Supplier-reported inventory; never inferred from mandi arrivals."""

    supplier_id: str = Field(min_length=1)
    commodity: str = Field(min_length=1)
    quantity: float = Field(gt=0)
    unit: str = Field(min_length=1)
    updated_at: datetime
    expires_at: datetime | None = None
    source: str = "supplier_reported"


class SupplierRegistration(ContractModel):
    supplier_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    location: LatLon
    contact_channel: str = "telegram"
    contact_handle: str = Field(min_length=1)
    verified_at: datetime | None = None
    active: bool = True


class ApprovalDecisionBody(ContractModel):
    approved: bool
    approver_id: str = Field(min_length=1)
    comment: str | None = None
    decided_at: datetime = Field(default_factory=utc_now)


class DispatchBody(ContractModel):
    driver_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class AcknowledgementBody(ContractModel):
    driver_id: str = Field(min_length=1)
    acknowledged: bool
    received_at: datetime = Field(default_factory=utc_now)
    message: str | None = None


def _service_or_503(service, name: str):
    if service is None:
        raise HTTPException(
            status_code=503,
            detail=f"{name} is unavailable: DATABASE_URL is not configured.",
        )
    return service


def _raise_http_error(exc: ReliefRouteError) -> None:
    """Translate typed domain errors to appropriate HTTP status codes."""
    status_map = {
        ErrorCode.VALIDATION_ERROR: 422,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.CONFLICT: 409,
        ErrorCode.APPROVAL_REQUIRED: 409,
        ErrorCode.UPSTREAM_TIMEOUT: 504,
        ErrorCode.UPSTREAM_UNAVAILABLE: 503,
        ErrorCode.UPSTREAM_RATE_LIMITED: 429,
        ErrorCode.UPSTREAM_AUTH_FAILED: 502,
        ErrorCode.INVALID_UPSTREAM_RESPONSE: 502,
        ErrorCode.DATA_STALE: 503,
    }
    raise HTTPException(
        status_code=status_map.get(exc.error.code, 500),
        detail=exc.error.model_dump(mode="json"),
    ) from exc


@app.get("/health")
async def health():
    database_url = getattr(app.state, "database_url", None)
    if not database_url:
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "database": "not_configured"},
        )
    try:
        async with await psycopg.AsyncConnection.connect(database_url, connect_timeout=10) as conn:
            await conn.execute("SELECT 1")
        return {"status": "ok", "service": "reliefroute-api", "database": "connected"}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "database": "unavailable",
                "reason": type(exc).__name__,
            },
        ) from exc


@app.post("/suppliers", response_model=Supplier)
async def register_supplier(body: SupplierRegistration):
    service = _service_or_503(app.state.suppliers, "Supplier service")
    try:
        return await service.register_supplier(Supplier.model_validate(body.model_dump()))
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.post("/inventory", response_model=InventoryItem)
async def upsert_inventory(body: InventorySubmission):
    service = _service_or_503(app.state.suppliers, "Supplier service")
    try:
        return await service.upsert_inventory(InventoryItem.model_validate(body.model_dump()))
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.get("/inventory/{commodity}")
async def list_inventory(commodity: str, min_quantity: float = Query(default=0, ge=0)):
    service = _service_or_503(app.state.suppliers, "Supplier service")
    try:
        rows = await service.list_available(commodity, min_quantity=min_quantity)
        return [{"supplier": supplier, "inventory": inventory} for supplier, inventory in rows]
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.post("/drivers/{driver_id}/location", response_model=DriverLocation)
async def record_driver_location(driver_id: str, body: DriverLocation):
    service = _service_or_503(app.state.telemetry, "Telemetry service")
    if driver_id != body.driver_id:
        raise HTTPException(status_code=422, detail="Path driver_id must match body driver_id.")
    try:
        return await service.record_location(body)
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.get("/drivers/{driver_id}/location", response_model=DriverLocation)
async def latest_driver_location(driver_id: str):
    service = _service_or_503(app.state.telemetry, "Telemetry service")
    try:
        location = await service.latest_location(driver_id)
        if location is None:
            raise HTTPException(status_code=404, detail="No location is available for this driver.")
        return location
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.get("/plans/{plan_id}", response_model=DeliveryPlan)
async def get_plan(plan_id: str):
    service = _service_or_503(app.state.plans, "Planning store")
    try:
        plan = await service.get_plan(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found.")
        return plan
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.post(
    "/citizen-reports",
    response_model=CitizenReport,
    status_code=201,
)
async def submit_citizen_report(body: CitizenReportSubmission):
    agent = _service_or_503(
        getattr(app.state, "citizen_report_agent", None),
        "Citizen report service",
    )
    try:
        return await agent.submit(body)
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.get("/citizen-reports", response_model=list[CitizenReport])
async def list_citizen_reports(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    triage_status: ReportTriageStatus | None = None,
):
    store = _service_or_503(
        getattr(app.state, "citizen_report_store", None),
        "Citizen report store",
    )
    try:
        return await store.list_reports(
            limit=limit,
            offset=offset,
            triage_status=triage_status,
        )
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.get("/citizen-reports/{report_id}", response_model=CitizenReport)
async def get_citizen_report(report_id: str):
    store = _service_or_503(
        getattr(app.state, "citizen_report_store", None),
        "Citizen report store",
    )
    try:
        report = await store.get_report(report_id)
        if report is None:
            raise ReliefRouteError(
                ErrorCode.NOT_FOUND,
                f"Citizen report '{report_id}' was not found.",
                provider="citizen_reports",
            )
        return report
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.post("/citizen-reports/{report_id}/triage", response_model=CitizenReport)
async def retriage_citizen_report(report_id: str):
    agent = _service_or_503(
        getattr(app.state, "citizen_report_agent", None),
        "Citizen report service",
    )
    try:
        return await agent.triage(report_id)
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.post("/plans/{plan_id}/approval", response_model=DeliveryPlan)
async def decide_plan(plan_id: str, body: ApprovalDecisionBody):
    workflow = _service_or_503(getattr(app.state, "approval_workflow", None), "Approval workflow")
    request = ApprovalRequest(plan_id=plan_id, **body.model_dump())
    try:
        return await workflow.decide(request)
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.post("/plans/{plan_id}/dispatch", response_model=DispatchResult)
async def dispatch_plan(plan_id: str, body: DispatchBody):
    workflow = _service_or_503(getattr(app.state, "approval_workflow", None), "Approval workflow")
    request = DispatchRequest(plan_id=plan_id, **body.model_dump())
    sender = getattr(app.state, "notification_sender", None)
    if not callable(sender):
        sender = _unconfigured_notification_sender
    try:
        return await workflow.dispatch(request, sender=sender)
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.post("/plans/{plan_id}/acknowledgement", response_model=DriverAcknowledgement)
async def acknowledge_dispatch(plan_id: str, body: AcknowledgementBody):
    workflow = _service_or_503(getattr(app.state, "approval_workflow", None), "Approval workflow")
    request = DriverAcknowledgement(plan_id=plan_id, **body.model_dump())
    try:
        return await workflow.acknowledge(request)
    except ReliefRouteError as exc:
        _raise_http_error(exc)
