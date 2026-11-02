"""PostgreSQL-backed audit event persistence."""

import json
import os

import psycopg
from dotenv import load_dotenv

from psycopg.rows import dict_row
from shared.enums import ErrorCode
from shared.errors import ReliefRouteError
from shared.models import AuditEvent

load_dotenv()


class PostgreSQLAuditService:
    """Append immutable audit events to PostgreSQL."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "DATABASE_URL is not configured.",
                provider="postgresql",
            )

    async def append(self, event: AuditEvent) -> None:
        """Persist an audit event without overwriting previous events."""

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                connect_timeout=5,
            ) as connection:
                await connection.execute(
                    """
                    INSERT INTO audit_events (
                        event_id,
                        occurred_at,
                        actor,
                        action,
                        entity_type,
                        entity_id,
                        outcome,
                        details,
                        source_refs
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb
                    )
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    (
                        event.event_id,
                        event.occurred_at,
                        event.actor,
                        event.action,
                        event.entity_type,
                        event.entity_id,
                        event.outcome,
                        json.dumps(event.details),
                        json.dumps(
                            [
                                source.model_dump(mode="json")
                                for source in event.source_refs
                            ]
                        ),
                    ),
                )

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not persist the audit event.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def list_by_entity(self, entity_id: str, limit: int = 50) -> list[AuditEvent]:
        """Retrieve audit events for a specific entity."""

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                cursor = await connection.execute(
                    """
                    SELECT event_id, occurred_at, actor, action,
                           entity_type, entity_id, outcome, details, source_refs
                    FROM audit_events
                    WHERE entity_id = %s
                    ORDER BY occurred_at ASC
                    LIMIT %s
                    """,
                    (entity_id, limit),
                )
                rows = await cursor.fetchall()

            return [
                AuditEvent(
                    event_id=r["event_id"],
                    occurred_at=r["occurred_at"],
                    actor=r["actor"],
                    action=r["action"],
                    entity_type=r["entity_type"],
                    entity_id=r["entity_id"],
                    outcome=r["outcome"],
                    details=r["details"] if isinstance(r["details"], dict) else json.loads(r["details"] or "{}"),
                    source_refs=r["source_refs"] if isinstance(r["source_refs"], list) else json.loads(r["source_refs"] or "[]"),
                )
                for r in rows
            ]

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not retrieve audit events.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc