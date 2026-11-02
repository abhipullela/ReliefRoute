"""PostgreSQL-backed supplier registration and inventory services."""

from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row

from shared.enums import ErrorCode
from shared.errors import ReliefRouteError
from shared.models import InventoryItem, LatLon, Supplier


class PostgreSQLSupplierService:
    """Persist suppliers and supplier-reported inventory in PostgreSQL.

    Inventory updates are stored as separate records. Queries select the
    latest valid record for each supplier/commodity pair.
    """

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")

        if not self.database_url:
            raise ValueError(
                "DATABASE_URL is not configured. Set it to your PostgreSQL connection URL."
            )

    async def register_supplier(self, supplier: Supplier) -> Supplier:
        """Create or update a supplier registration."""

        query = """
            INSERT INTO suppliers (
                supplier_id,
                name,
                latitude,
                longitude,
                contact_channel,
                contact_handle,
                active,
                verified_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (supplier_id)
            DO UPDATE SET
                name = EXCLUDED.name,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                contact_channel = EXCLUDED.contact_channel,
                contact_handle = EXCLUDED.contact_handle,
                active = EXCLUDED.active,
                verified_at = EXCLUDED.verified_at
            RETURNING
                supplier_id,
                name,
                latitude,
                longitude,
                contact_channel,
                contact_handle,
                active,
                verified_at;
        """

        values = (
            supplier.supplier_id,
            supplier.name,
            supplier.location.latitude,
            supplier.location.longitude,
            supplier.contact_channel,
            supplier.contact_handle,
            supplier.active,
            supplier.verified_at,
        )

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
            ) as connection, connection.cursor() as cursor:
                await cursor.execute(query, values)
                row = await cursor.fetchone()

            return self._supplier_from_row(row)

        except psycopg.Error as exc:
            raise self._database_error(
                "Failed to register supplier.",
                exc,
            ) from exc

    async def upsert_inventory(self, item: InventoryItem) -> InventoryItem:
        """Record a new supplier inventory update.

        Each update is retained as a record instead of overwriting history.
        The latest record determines currently available stock.
        """

        if item.source != "supplier_reported":
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "Inventory must be explicitly supplier-reported. "
                "Mandi arrivals and prices are not supplier inventory.",
                provider="PostgreSQL",
            )

        query = """
            INSERT INTO inventory (
                supplier_id,
                commodity,
                quantity,
                unit,
                updated_at,
                expires_at,
                source
            )
            SELECT
                s.supplier_id,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            FROM suppliers AS s
            WHERE s.supplier_id = %s
            RETURNING
                supplier_id,
                commodity,
                quantity,
                unit,
                updated_at,
                expires_at,
                source;
        """

        values = (
            item.commodity,
            item.quantity,
            item.unit,
            item.updated_at,
            item.expires_at,
            item.source,
            item.supplier_id,
        )

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
            ) as connection, connection.cursor() as cursor:
                await cursor.execute(query, values)
                row = await cursor.fetchone()

            if row is None:
                raise ReliefRouteError(
                    ErrorCode.NOT_FOUND,
                    f"Supplier '{item.supplier_id}' does not exist.",
                    provider="PostgreSQL",
                )

            return self._inventory_from_row(row)

        except ReliefRouteError:
            raise
        except psycopg.Error as exc:
            raise self._database_error(
                "Failed to record supplier inventory.",
                exc,
            ) from exc

    async def list_available(
        self,
        commodity: str,
        *,
        min_quantity: float = 0,
    ) -> list[tuple[Supplier, InventoryItem]]:
        """Return active suppliers with their latest non-expired stock.

        Commodity matching is case-insensitive. Inventory records with
        future update timestamps are excluded.
        """

        if not commodity.strip():
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "Commodity cannot be empty.",
            )

        if min_quantity < 0:
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "Minimum quantity cannot be negative.",
            )

        query = """
            WITH latest_inventory AS (
                SELECT DISTINCT ON (i.supplier_id, LOWER(i.commodity))
                    i.supplier_id,
                    i.commodity,
                    i.quantity,
                    i.unit,
                    i.updated_at,
                    i.expires_at,
                    i.source
                FROM inventory AS i
                WHERE LOWER(i.commodity) = LOWER(%s)
                  AND i.updated_at <= NOW()
                ORDER BY
                    i.supplier_id,
                    LOWER(i.commodity),
                    i.updated_at DESC,
                    i.inventory_id DESC
            )
            SELECT
                s.supplier_id,
                s.name,
                s.latitude,
                s.longitude,
                s.contact_channel,
                s.contact_handle,
                s.active,
                s.verified_at,
                i.commodity,
                i.quantity,
                i.unit,
                i.updated_at,
                i.expires_at,
                i.source
            FROM suppliers AS s
            JOIN latest_inventory AS i
              ON i.supplier_id = s.supplier_id
            WHERE s.active = TRUE
              AND i.quantity >= %s
              AND (i.expires_at IS NULL OR i.expires_at > NOW())
            ORDER BY i.quantity DESC, s.supplier_id;
        """

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
            ) as connection, connection.cursor() as cursor:
                await cursor.execute(query, (commodity.strip(), min_quantity))
                rows = await cursor.fetchall()

            results: list[tuple[Supplier, InventoryItem]] = []

            for row in rows:
                supplier = self._supplier_from_row(row)
                inventory = self._inventory_from_row(row)
                results.append((supplier, inventory))

            return results

        except psycopg.Error as exc:
            raise self._database_error(
                "Failed to retrieve available supplier inventory.",
                exc,
            ) from exc

    @staticmethod
    def _supplier_from_row(row: dict) -> Supplier:
        return Supplier(
            supplier_id=row["supplier_id"],
            name=row["name"],
            location=LatLon(
                latitude=row["latitude"],
                longitude=row["longitude"],
            ),
            contact_channel=row["contact_channel"],
            contact_handle=row["contact_handle"],
            active=row["active"],
            verified_at=row["verified_at"],
        )

    @staticmethod
    def _inventory_from_row(row: dict) -> InventoryItem:
        return InventoryItem(
            supplier_id=row["supplier_id"],
            commodity=row["commodity"],
            quantity=row["quantity"],
            unit=row["unit"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
            source=row["source"],
        )

    @staticmethod
    def _database_error(
        message: str,
        exc: psycopg.Error,
    ) -> ReliefRouteError:
        return ReliefRouteError(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            message,
            retryable=True,
            provider="PostgreSQL",
            details={"error_type": type(exc).__name__},
        )
