from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from shared.models import LatLon, InventoryItem

def test_latlon_accepts_valid_coordinates():
    assert LatLon(latitude=12.9, longitude=77.6).latitude == 12.9

def test_latlon_rejects_invalid_latitude():
    with pytest.raises(ValidationError):
        LatLon(latitude=100, longitude=77.6)

def test_inventory_requires_positive_quantity():
    with pytest.raises(ValidationError):
        InventoryItem(supplier_id="s1", commodity="milk", quantity=0, unit="litre",
                      updated_at=datetime.now(timezone.utc))
