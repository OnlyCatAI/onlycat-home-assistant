"""Tests for the OnlyCat event sensor."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.onlycat.binary_sensor_event import OnlyCatEventSensor
from custom_components.onlycat.data.event import (
    Event,
    EventClassification,
    EventTriggerSource,
)
from custom_components.onlycat.data.event_store import EventStore
from custom_components.onlycat.data.event_summary import EventSummary, SubEvent


@pytest.mark.asyncio
async def test_event_summary_adds_exact_subevent_attributes() -> None:
    """Summary RFID, action, and direction are published without access tokens."""
    device_id = "OC-00000000001"
    store = EventStore(MagicMock())
    sensor = OnlyCatEventSensor(
        SimpleNamespace(device_id=device_id, description="Back Door"), store
    )
    sensor.async_write_ha_state = MagicMock()
    event = Event(
        device_id=device_id,
        event_id=1179,
        frame_count=12,
        event_trigger_source=EventTriggerSource.OUTDOOR_MOTION,
        event_classification=EventClassification.CONTRABAND,
        access_token="must-not-be-published",  # noqa: S106
        rfid_codes=[],
    )
    subevent = SubEvent.from_api_response(
        {
            "startFrameIndex": 1,
            "endFrameIndex": 11,
            "rfidCode": "958000000000001",
            "direction": "INWARD",
            "action": "LOCKED",
        }
    )
    assert subevent is not None
    summary = EventSummary(device_id=device_id, event_id=1179, subevents=[subevent])

    await sensor.on_history_replay(event, summary, True)  # noqa: FBT003

    assert sensor.extra_state_attributes == {
        "eventId": 1179,
        "timestamp": None,
        "eventTriggerSource": "OUTDOOR_MOTION",
        "eventClassification": "CONTRABAND",
        "eventSummary": [
            {
                "startFrameIndex": 1,
                "endFrameIndex": 11,
                "rfidCode": "958000000000001",
                "direction": "INWARD",
                "action": "LOCKED",
            }
        ],
        "rfidCodes": ["958000000000001"],
    }
    assert sensor.is_on is False
    assert "accessToken" not in sensor.extra_state_attributes
