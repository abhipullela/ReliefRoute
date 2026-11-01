"""PostgreSQL-backed audit event persistence."""

import json
import os

import psycopg
from dotenv import load_dotenv

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