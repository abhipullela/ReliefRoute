"""Integration test for the PostgreSQL-backed supplier service.

Creates uniquely identified test records and removes them afterward.
Do not use these records as demo or production inventory.
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
from dotenv import load_dotenv

from services.suppliers import PostgreSQLSupplierService
from shared.models import InventoryItem, LatLon, Supplier


async def main():
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing from .env")

    service = PostgreSQLSupplierService(database_url)

    # Unique IDs prevent collisions with existing supplier records.
    test_id = uuid.uuid4().hex[:12]
    active_id = f"test-active-{test_id}"
    inactive_id = f"test-inactive-{test_id}"
    expired_id = f"test-expired-{test_id}"

    now = datetime.now(UTC)

    active_supplier = Supplier(
        supplier_id=active_id,
        name=f"Integration Test Supplier {test_id}",
        location=LatLon(latitude=12.9716, longitude=77.5946),
        contact_channel="test",
        contact_handle=f"test-{test_id}",
        active=True,
    )

    inactive_supplier = Supplier(
        supplier_id=inactive_id,
        name=f"Inactive Test Supplier {test_id}",
        location=LatLon(latitude=12.9352, longitude=77.6245),
        contact_channel="test",
        contact_handle=f"test-inactive-{test_id}",
        active=False,
    )

    expired_supplier = Supplier(
        supplier_id=expired_id,
        name=f"Expired Stock Test Supplier {test_id}",
        location=LatLon(latitude=13.0827, longitude=77.5970),
        contact_channel="test",
        contact_handle=f"test-expired-{test_id}",
        active=True,
    )

    supplier_ids = [active_id, inactive_id, expired_id]

    try:
        # 1. Register suppliers.
        await service.register_supplier(active_supplier)
        await service.register_supplier(inactive_supplier)
        await service.register_supplier(expired_supplier)

        print("PASS: Supplier registration")

        # 2. Record two inventory updates for the same supplier.
        # The latest update should determine current available stock.
        await service.upsert_inventory(
            InventoryItem(
                supplier_id=active_id,
                commodity="integration-test-rice",
                quantity=100,
                unit="kg",
                updated_at=now - timedelta(minutes=2),
            )
        )

        await service.upsert_inventory(
            InventoryItem(
                supplier_id=active_id,
                commodity="integration-test-rice",
                quantity=5,
                unit="kg",
                updated_at=now - timedelta(minutes=1),
            )
        )

        print("PASS: Inventory updates recorded")

        # 3. Verify the latest inventory update is returned.
        available = await service.list_available(
            "integration-test-rice",
            min_quantity=1,
        )

        active_results = [
            (supplier, inventory)
            for supplier, inventory in available
            if supplier.supplier_id == active_id
        ]

        assert len(active_results) == 1, (
            "Expected exactly one result for the active supplier"
        )

        _, latest_inventory = active_results[0]

        assert latest_inventory.quantity == 5, (
            f"Expected latest quantity 5, got {latest_inventory.quantity}"
        )

        print("PASS: Latest inventory update selected")

        # 4. The older quantity was 100 kg, but the current quantity is
        # only 5 kg. A minimum of 10 kg must therefore exclude this supplier.
        sufficient_stock = await service.list_available(
            "integration-test-rice",
            min_quantity=10,
        )

        assert all(
            supplier.supplier_id != active_id
            for supplier, _ in sufficient_stock
        ), "Supplier with only 5 kg should not satisfy a 10 kg requirement"

        print("PASS: Minimum quantity filter")

        # 5. Verify expired stock is excluded.
        await service.upsert_inventory(
            InventoryItem(
                supplier_id=expired_id,
                commodity="integration-test-rice",
                quantity=50,
                unit="kg",
                updated_at=now - timedelta(minutes=1),
                expires_at=now - timedelta(seconds=1),
            )
        )

        # 6. Verify inactive supplier stock is excluded.
        await service.upsert_inventory(
            InventoryItem(
                supplier_id=inactive_id,
                commodity="integration-test-rice",
                quantity=50,
                unit="kg",
                updated_at=now - timedelta(minutes=1),
            )
        )

        available = await service.list_available(
            "integration-test-rice",
            min_quantity=1,
        )

        returned_ids = {supplier.supplier_id for supplier, _ in available}

        assert expired_id not in returned_ids, (
            "Expired inventory must not be returned"
        )
        assert inactive_id not in returned_ids, (
            "Inactive supplier must not be returned"
        )

        print("PASS: Expired inventory excluded")
        print("PASS: Inactive supplier excluded")
        print("\nALL SUPPLIER INTEGRATION TESTS PASSED")

    finally:
        # Delete only the records created by this test.
        # Inventory must be deleted before its referenced suppliers.
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM inventory WHERE supplier_id = ANY(%s)",
                (supplier_ids,),
            )
            cursor.execute(
                "DELETE FROM suppliers WHERE supplier_id = ANY(%s)",
                (supplier_ids,),
            )

        print("Test records cleaned up.")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)