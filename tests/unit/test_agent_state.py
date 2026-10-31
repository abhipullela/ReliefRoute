"""Unit tests for AgentState, IncidentInfo, and state initialization."""

import pytest
from pydantic import ValidationError

from agent.state import (
    IncidentInfo,
    ValidationResult,
    WorkflowStatus,
    create_initial_state,
)
from shared.models import LatLon


def test_incident_info_valid():
    """Verify valid IncidentInfo instantiates without error."""
    incident = IncidentInfo(
        incident_id="inc_123",
        commodity="rice",
        required_quantity=50.0,
        unit="kg",
        destination=LatLon(latitude=12.9, longitude=77.6),
    )
    assert incident.incident_id == "inc_123"
    assert incident.commodity == "rice"
    assert incident.required_quantity == 50.0
    assert incident.unit == "kg"
    assert incident.priority == "NORMAL"


def test_incident_info_rejects_non_positive_quantity():
    """Verify IncidentInfo rejects zero or negative quantities."""
    with pytest.raises(ValidationError):
        IncidentInfo(
            incident_id="inc_123",
            commodity="rice",
            required_quantity=0,
            unit="kg",
            destination=LatLon(latitude=12.9, longitude=77.6),
        )

    with pytest.raises(ValidationError):
        IncidentInfo(
            incident_id="inc_123",
            commodity="rice",
            required_quantity=-10.0,
            unit="kg",
            destination=LatLon(latitude=12.9, longitude=77.6),
        )


def test_create_initial_state_defaults():
    """Verify create_initial_state creates state with clean defaults."""
    state = create_initial_state()
    assert state["incident"] is None
    assert state["location"] is None
    assert state["weather_observations"] == []
    assert state["hazard_assessment"] is None
    assert state["available_suppliers"] == []
    assert state["selected_supplier"] is None
    assert state["selected_inventory"] is None
    assert state["route"] is None
    assert state["delivery_plan"] is None
    assert state["workflow_status"] == WorkflowStatus.INITIALIZED
    assert state["validation_results"] is None
    assert state["errors"] == []
    assert state["missing_info"] == []
    assert state["sources"] == []
    assert "created_at" in state
    assert "updated_at" in state


def test_create_initial_state_from_incident_dict():
    """Verify passing an incident dict initializes IncidentInfo and location."""
    raw_incident = {
        "incident_id": "inc_456",
        "commodity": "milk",
        "required_quantity": 25.0,
        "unit": "litre",
        "destination": {"latitude": 12.711, "longitude": 77.695},
    }
    state = create_initial_state(incident=raw_incident)
    assert state["incident"] is not None
    assert state["incident"].incident_id == "inc_456"
    assert state["location"] is not None
    assert state["location"].latitude == 12.711
    assert state["location"].longitude == 77.695


def test_create_initial_state_explicit_location_override():
    """Verify explicit location overrides incident destination for monitoring."""
    incident = IncidentInfo(
        incident_id="inc_789",
        commodity="blankets",
        required_quantity=100.0,
        unit="pieces",
        destination=LatLon(latitude=12.711, longitude=77.695),
    )
    custom_loc = LatLon(latitude=12.900, longitude=77.500)
    state = create_initial_state(incident=incident, location=custom_loc)
    assert state["incident"] == incident
    assert state["location"] == custom_loc


def test_validation_result_structure():
    """Verify ValidationResult model records errors and warnings."""
    res = ValidationResult(is_valid=False, errors=["Error A"], warnings=["Warning B"])
    assert not res.is_valid
    assert res.errors == ["Error A"]
    assert res.warnings == ["Warning B"]
    assert res.checked_at is not None
