"""PostgreSQL persistence for atomic dispatch and driver acknowledgement workflows."""

import json
import os
import uuid

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from shared.enums import ErrorCode, PlanStatus
from shared.errors import ReliefRouteError
from shared.models import (
    DispatchRequest,
    DispatchResult,
    DriverAcknowledgement,
)

load_dotenv()


class PostgreSQLDispatchService:
    """Reserve dispatches before sending and persist confirmed outcomes atomically."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "DATABASE_URL is not configured.",
                provider="postgresql",
            )

    async def begin_attempt(self, request: DispatchRequest) -> DispatchResult | None:
        """Claim an approved plan; return an existing result or reserve a new send.

        ``None`` means this caller owns the reservation and is the only caller
        allowed to invoke the external notification provider.
        """

        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self.database_url,
                    row_factory=dict_row,
                    connect_timeout=5,
                ) as connection,
                connection.transaction(),
            ):
                existing = await self._find_by_key(connection, request.idempotency_key)
                if existing is not None:
                    return self._existing_attempt(existing, request)

                cursor = await connection.execute(
                    """
                        UPDATE plans
                        SET status = %s,
                            payload = jsonb_set(
                                payload, '{status}', to_jsonb(%s::text)
                            ),
                            updated_at = NOW()
                        WHERE plan_id = %s AND status = %s
                        RETURNING plan_id
                        """,
                    (
                        PlanStatus.DISPATCHING.value,
                        PlanStatus.DISPATCHING.value,
                        request.plan_id,
                        PlanStatus.APPROVED.value,
                    ),
                )
                plan_row = await cursor.fetchone()
                if plan_row is None:
                    # A concurrent retry with this key may have committed while
                    # this statement waited on the plan row lock.
                    existing = await self._find_by_key(connection, request.idempotency_key)
                    if existing is not None:
                        return self._existing_attempt(existing, request)

                    cursor = await connection.execute(
                        "SELECT status FROM plans WHERE plan_id = %s",
                        (request.plan_id,),
                    )
                    current_plan = await cursor.fetchone()
                    if current_plan is None:
                        raise ReliefRouteError(
                            ErrorCode.NOT_FOUND,
                            f"Delivery plan '{request.plan_id}' was not found.",
                            provider="postgresql",
                        )
                    code = (
                        ErrorCode.APPROVAL_REQUIRED
                        if current_plan["status"] != PlanStatus.APPROVED.value
                        else ErrorCode.CONFLICT
                    )
                    raise ReliefRouteError(
                        code,
                        "Plan is not available for a new dispatch attempt.",
                        provider="approval_workflow",
                        details={
                            "plan_id": request.plan_id,
                            "status": current_plan["status"],
                        },
                    )

                dispatch_id = str(uuid.uuid4())
                payload = {"request": request.model_dump(mode="json")}
                cursor = await connection.execute(
                    """
                        INSERT INTO dispatches (
                            dispatch_id, plan_id, idempotency_key, status, payload
                        )
                        VALUES (%s, %s, %s, 'SENDING', %s::jsonb)
                        RETURNING dispatch_id, plan_id, status, attempted_at
                        """,
                    (
                        dispatch_id,
                        request.plan_id,
                        request.idempotency_key,
                        json.dumps(payload),
                    ),
                )
                await cursor.fetchone()
                return None

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not reserve the dispatch attempt.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def complete_attempt(
        self,
        request: DispatchRequest,
        *,
        provider_message_id: str | None,
    ) -> DispatchResult:
        """Record provider-confirmed acceptance and plan transition atomically."""

        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self.database_url,
                    row_factory=dict_row,
                    connect_timeout=5,
                ) as connection,
                connection.transaction(),
            ):
                cursor = await connection.execute(
                    """
                        UPDATE dispatches
                        SET status = 'SENT', provider_message_id = %s
                        WHERE idempotency_key = %s AND status = 'SENDING'
                        RETURNING dispatch_id, plan_id, status, provider_message_id,
                                  attempted_at
                        """,
                    (provider_message_id, request.idempotency_key),
                )
                row = await cursor.fetchone()

                if row is None:
                    existing = await self._find_by_key(connection, request.idempotency_key)
                    if existing and existing["status"] == "SENT":
                        self._assert_same_request(existing, request)
                        return self._dispatch_result(existing)
                    raise ReliefRouteError(
                        ErrorCode.CONFLICT,
                        "Dispatch reservation is no longer available.",
                        provider="postgresql",
                    )

                cursor = await connection.execute(
                    """
                        UPDATE plans
                        SET status = %s,
                            payload = jsonb_set(
                                payload, '{status}', to_jsonb(%s::text)
                            ),
                            updated_at = NOW()
                        WHERE plan_id = %s AND status = %s
                        RETURNING plan_id
                        """,
                    (
                        PlanStatus.DISPATCHED.value,
                        PlanStatus.DISPATCHED.value,
                        request.plan_id,
                        PlanStatus.DISPATCHING.value,
                    ),
                )
                if await cursor.fetchone() is None:
                    raise ReliefRouteError(
                        ErrorCode.CONFLICT,
                        "Plan state changed before dispatch completion.",
                        provider="approval_workflow",
                    )
                return self._dispatch_result(row)

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not persist the confirmed dispatch.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def fail_attempt(
        self,
        request: DispatchRequest,
        *,
        error: dict[str, str],
    ) -> DispatchResult:
        """Record a definitive provider rejection and release the plan for recovery."""

        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self.database_url,
                    row_factory=dict_row,
                    connect_timeout=5,
                ) as connection,
                connection.transaction(),
            ):
                cursor = await connection.execute(
                    """
                        UPDATE dispatches
                        SET status = 'FAILED',
                            payload = jsonb_set(payload, '{error}', %s::jsonb, true)
                        WHERE idempotency_key = %s AND status = 'SENDING'
                        RETURNING dispatch_id, plan_id, status, provider_message_id,
                                  attempted_at
                        """,
                    (json.dumps(error), request.idempotency_key),
                )
                row = await cursor.fetchone()

                if row is None:
                    existing = await self._find_by_key(connection, request.idempotency_key)
                    if existing and existing["status"] == "FAILED":
                        self._assert_same_request(existing, request)
                        return self._dispatch_result(existing)
                    raise ReliefRouteError(
                        ErrorCode.CONFLICT,
                        "Dispatch reservation is no longer available.",
                        provider="postgresql",
                    )

                cursor = await connection.execute(
                    """
                        UPDATE plans
                        SET status = %s,
                            payload = jsonb_set(
                                payload, '{status}', to_jsonb(%s::text)
                            ),
                            updated_at = NOW()
                        WHERE plan_id = %s AND status = %s
                        RETURNING plan_id
                        """,
                    (
                        PlanStatus.APPROVED.value,
                        PlanStatus.APPROVED.value,
                        request.plan_id,
                        PlanStatus.DISPATCHING.value,
                    ),
                )
                if await cursor.fetchone() is None:
                    raise ReliefRouteError(
                        ErrorCode.CONFLICT,
                        "Plan state changed before failed dispatch recovery.",
                        provider="approval_workflow",
                    )
                return self._dispatch_result(row)

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not persist the failed dispatch.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def record_acknowledgement(self, ack: DriverAcknowledgement) -> bool:
        """Atomically persist one acknowledgement and update the plan state.

        Returns True only for the first acknowledgement. Identical retries return
        False, while a conflicting second acknowledgement is rejected.
        """

        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self.database_url,
                    row_factory=dict_row,
                    connect_timeout=5,
                ) as connection,
                connection.transaction(),
            ):
                cursor = await connection.execute(
                    """
                        SELECT status
                        FROM plans
                        WHERE plan_id = %s
                        FOR UPDATE
                        """,
                    (ack.plan_id,),
                )
                plan = await cursor.fetchone()
                if plan is None:
                    raise ReliefRouteError(
                        ErrorCode.NOT_FOUND,
                        f"Delivery plan '{ack.plan_id}' was not found.",
                        provider="postgresql",
                    )
                if plan["status"] not in {
                    PlanStatus.DISPATCHED.value,
                    PlanStatus.ACKNOWLEDGED.value,
                    PlanStatus.IN_TRANSIT.value,
                }:
                    raise ReliefRouteError(
                        ErrorCode.CONFLICT,
                        "A driver acknowledgement requires a dispatched plan.",
                        provider="approval_workflow",
                        details={"plan_id": ack.plan_id, "status": plan["status"]},
                    )

                cursor = await connection.execute(
                    """
                        SELECT dispatch_id, payload
                        FROM dispatches
                        WHERE plan_id = %s
                          AND status = 'SENT'
                          AND payload->'request'->>'driver_id' = %s
                        ORDER BY attempted_at DESC
                        LIMIT 1
                        FOR UPDATE
                        """,
                    (ack.plan_id, ack.driver_id),
                )
                dispatch = await cursor.fetchone()
                if dispatch is None:
                    raise ReliefRouteError(
                        ErrorCode.NOT_FOUND,
                        "No confirmed dispatch found for this plan and driver.",
                        provider="postgresql",
                    )

                saved_ack = dispatch["payload"].get("acknowledgement")
                if saved_ack is not None:
                    same_decision = (
                        saved_ack.get("plan_id") == ack.plan_id
                        and saved_ack.get("driver_id") == ack.driver_id
                        and saved_ack.get("acknowledged") == ack.acknowledged
                        and saved_ack.get("message") == ack.message
                    )
                    if same_decision:
                        return False
                    raise ReliefRouteError(
                        ErrorCode.CONFLICT,
                        "A different acknowledgement is already recorded.",
                        provider="postgresql",
                    )

                cursor = await connection.execute(
                    """
                        UPDATE dispatches
                        SET payload = jsonb_set(
                            payload, '{acknowledgement}', %s::jsonb, true
                        )
                        WHERE dispatch_id = %s
                        """,
                    (
                        json.dumps(ack.model_dump(mode="json")),
                        dispatch["dispatch_id"],
                    ),
                )

                if ack.acknowledged and plan["status"] == PlanStatus.DISPATCHED.value:
                    await connection.execute(
                        """
                            UPDATE plans
                            SET status = %s,
                                payload = jsonb_set(
                                    payload, '{status}', to_jsonb(%s::text)
                                ),
                                updated_at = NOW()
                            WHERE plan_id = %s AND status = %s
                            """,
                        (
                            PlanStatus.ACKNOWLEDGED.value,
                            PlanStatus.ACKNOWLEDGED.value,
                            ack.plan_id,
                            PlanStatus.DISPATCHED.value,
                        ),
                    )
                return True

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not persist the driver acknowledgement.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def _find_by_key(self, connection, idempotency_key: str):
        cursor = await connection.execute(
            """
            SELECT dispatch_id, plan_id, idempotency_key, status,
                   provider_message_id, attempted_at, payload
            FROM dispatches
            WHERE idempotency_key = %s
            FOR UPDATE
            """,
            (idempotency_key,),
        )
        return await cursor.fetchone()

    def _existing_attempt(self, existing: dict, request: DispatchRequest) -> DispatchResult:
        self._assert_same_request(existing, request)
        if existing["status"] == "SENT":
            return self._dispatch_result(existing)
        if existing["status"] == "FAILED":
            raise ReliefRouteError(
                ErrorCode.CONFLICT,
                "This dispatch request already failed; use a new idempotency key to retry.",
                provider="approval_workflow",
                details={"dispatch_id": existing["dispatch_id"], "status": "FAILED"},
            )
        raise ReliefRouteError(
            ErrorCode.CONFLICT,
            "This dispatch request is unresolved and will not be sent again automatically.",
            retryable=True,
            provider="approval_workflow",
            details={"dispatch_id": existing["dispatch_id"], "status": existing["status"]},
        )

    @staticmethod
    def _assert_same_request(existing: dict, request: DispatchRequest) -> None:
        existing_request = dict(existing["payload"].get("request", {}))
        existing_request.setdefault("telegram_chat_id", None)
        if existing["plan_id"] != request.plan_id or existing_request != request.model_dump(
            mode="json"
        ):
            raise ReliefRouteError(
                ErrorCode.CONFLICT,
                "Dispatch idempotency key belongs to a different request.",
                provider="postgresql",
            )

    @staticmethod
    def _dispatch_result(row: dict) -> DispatchResult:
        return DispatchResult(
            dispatch_id=row["dispatch_id"],
            plan_id=row["plan_id"],
            provider_message_id=row.get("provider_message_id"),
            status=row["status"],
            attempted_at=row["attempted_at"],
        )
