"""ReliefRoute API: supplier, inventory, telemetry and plan endpoints."""

import os
from contextlib import asynccontextmanager

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from datetime import datetime

from services.plans import PostgreSQLPlanningStore
from services.suppliers import PostgreSQLSupplierService
from services.telemetry import PostgreSQLTelemetryService
from shared.errors import ReliefRouteError
from shared.models import (
    DeliveryPlan,
    DriverLocation,
    InventoryItem,
    LatLon,
    Supplier,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create service objects once per application process."""
    database_url = os.getenv("DATABASE_URL")

    app.state.database_url = database_url
    app.state.suppliers = (
        PostgreSQLSupplierService(database_url) if database_url else None
    )
    app.state.telemetry = (
        PostgreSQLTelemetryService(database_url) if database_url else None
    )
    app.state.plans = (
        PostgreSQLPlanningStore(database_url) if database_url else None
    )

    yield


app = FastAPI(
    title="ReliefRoute API",
    version="0.1.0",
    lifespan=lifespan,
)


class InventorySubmission(BaseModel):
    """Supplier-reported inventory; never inferred from mandi arrivals."""

    supplier_id: str = Field(min_length=1)
    commodity: str = Field(min_length=1)
    quantity: float = Field(gt=0)
    unit: str = Field(min_length=1)
    updated_at: datetime
    expires_at: datetime | None = None
    source: str = "supplier_reported"


class SupplierRegistration(BaseModel):
    supplier_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    location: LatLon
    contact_channel: str = "telegram"
    contact_handle: str = Field(min_length=1)
    verified_at: datetime | None = None
    active: bool = True


def _service_or_503(service, name: str):
    if service is None:
        raise HTTPException(
            status_code=503,
            detail=f"{name} is unavailable: DATABASE_URL is not configured.",
        )
    return service


def _raise_http_error(exc: ReliefRouteError) -> None:
    """Translate typed domain errors to appropriate HTTP status codes."""
    from shared.enums import ErrorCode

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
    code = exc.error.code
    status_code = status_map.get(code, 500)
    raise HTTPException(
        status_code=status_code,
        detail=exc.error.model_dump(mode="json"),
    ) from exc


# @app.get("/health")
# async def health() -> dict:
#     """Check API process and database readiness."""
#     database_url = app.state.database_url

#     if not database_url:
#         raise HTTPException(
#             status_code=503,
#             detail={
#                 "status": "unavailable",
#                 "service": "reliefroute-api",
#                 "database": "not_configured",
#             },
#         )

#     try:
#         async with await psycopg.AsyncConnection.connect(
#             database_url,
#             connect_timeout=3,
#         ) as connection:
#             await connection.execute("SELECT 1")
#     except psycopg.Error as exc:
#         raise HTTPException(
#             status_code=503,
#             detail={
#                 "status": "unavailable",
#                 "service": "reliefroute-api",
#                 "database": "unavailable",
#                 "error_type": type(exc).__name__,
#             },
#         ) from exc

#     return {
#         "status": "ok",
#         "service": "reliefroute-api",
#         "database": "connected",
#     }

@app.get("/health")
async def health():
    database_url = getattr(app.state, "database_url", None)

    if not database_url:
        return {
            "status": "error",
            "database": "not_configured",
        }

    try:
        async with await psycopg.AsyncConnection.connect(
            database_url,
            connect_timeout=10,
        ) as conn:
            await conn.execute("SELECT 1")

        return {
            "status": "ok",
            "service": "reliefroute-api",
            "database": "connected",
        }

    except Exception as exc:
        print(f"Health check failed: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "database": "unavailable",
                "reason": type(exc).__name__,
            },
        )

@app.post("/suppliers", response_model=Supplier)
async def register_supplier(body: SupplierRegistration):
    service = _service_or_503(app.state.suppliers, "Supplier service")
    try:
        supplier = Supplier.model_validate(body.model_dump())
        return await service.register_supplier(supplier)
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.post("/inventory", response_model=InventoryItem)
async def upsert_inventory(body: InventorySubmission):
    service = _service_or_503(app.state.suppliers, "Supplier service")
    try:
        item = InventoryItem.model_validate(body.model_dump())
        return await service.upsert_inventory(item)
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.get("/inventory/{commodity}")
async def list_inventory(
    commodity: str,
    min_quantity: float = Query(default=0, ge=0),
):
    service = _service_or_503(app.state.suppliers, "Supplier service")
    try:
        rows = await service.list_available(
            commodity,
            min_quantity=min_quantity,
        )
        return [
            {"supplier": supplier, "inventory": inventory}
            for supplier, inventory in rows
        ]
    except ReliefRouteError as exc:
        _raise_http_error(exc)


@app.post("/drivers/{driver_id}/location", response_model=DriverLocation)
async def record_driver_location(driver_id: str, body: DriverLocation):
    service = _service_or_503(app.state.telemetry, "Telemetry service")

    if driver_id != body.driver_id:
        raise HTTPException(
            status_code=422,
            detail="Path driver_id must match body driver_id.",
        )

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
            raise HTTPException(
                status_code=404,
                detail="No location is available for this driver.",
            )
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