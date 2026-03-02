"""Tests for OnlyCat/__init.py."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.onlycat import _initialize_devices

get_devices = [
    # "Normal device"
    {
        "deviceId": "OC-00000000001",
        "description": "Device Name",
        "timeZone": "Europe/Zurich",
        "deviceTransitPolicyId": 0000,
        "cursorId": 0000,
    },
    # Fresh device with no transit policy
    {
        "deviceId": "OC-00000000002",
        "description": "Device Name",
        "timeZone": "Europe/Zurich",
        "cursorId": 0000,
    },
]
get_device = {
    "OC-00000000001": {
        "deviceId": "OC-00000000001",
        "description": "Device Name",
        "timeZone": "Europe/Zurich",
        "deviceTransitPolicyId": 0000,
        "connectivity": {
            "connected": True,
            "disconnectReason": None,
            "timestamp": 1743841488269,
        },
    },
    "OC-00000000002": {
        "deviceId": "OC-00000000002",
        "description": "Device Name",
        "timeZone": "Europe/Zurich",
        "connectivity": {
            "connected": True,
            "disconnectReason": None,
            "timestamp": 1743841488269,
        },
    },
}
get_device_transit_policy = {
    0: {
        "deviceTransitPolicyId": 0000,
        "deviceId": "OC-00000000001",
        "name": "Nachts",
        "transitPolicy": {
            "rules": [
                {
                    "action": {"lock": True},
                    "criteria": {
                        "eventTriggerSource": 3,
                        "eventClassification": [2, 3],
                    },
                    "description": "Contraband Rule",
                },
                {
                    "action": {"lock": False},
                    "enabled": True,
                    "criteria": {
                        "rfidCode": [
                            "000000000000003",
                            "000000000000001",
                            "000000000000002",
                        ],
                        "eventTriggerSource": 3,
                    },
                    "description": "Entry Rule",
                },
            ],
            "idleLock": True,
            "idleLockBattery": True,
        },
    }
}
device_update = [
    {
        "type": "update",
        "deviceId": "OC-00000000002",
        "body": {
            "connectivity": {
                "connected": False,
                "disconnectReason": "SERVER_INITIATED_DISCONNECT",
                "timestamp": 1754114553075,
            }
        },
    },
    {
        "deviceId": "OC-00000000002",
        "type": "update",
        "body": {"deviceId": "OC-00000000002", "deviceTransitPolicyId": 0000},
    },
]


async def mock_send_message(topic: str, data: dict) -> Any | None:
    """Mock of OnlyCatApiClient.send_message to return test api responses."""
    if topic == "getDevices":
        return get_devices
    if topic == "getDevice":
        return get_device[data["deviceId"]]
    if topic == "getDeviceTransitPolicy":
        return get_device_transit_policy[data["deviceTransitPolicyId"]]
    return None


@pytest.mark.asyncio
async def test_initialize_devices() -> None:
    """Test _initialize_devices."""
    mock_entry = AsyncMock()
    mock_entry.runtime_data.devices = []
    mock_entry.runtime_data.client = AsyncMock()
    mock_entry.runtime_data.client.send_message.side_effect = mock_send_message
    await _initialize_devices(mock_entry)

    assert len(mock_entry.runtime_data.devices) == len(get_devices)
    mock_entry.runtime_data.client.send_message.assert_any_call(
        "getDevices", {"subscribe": True}
    )
    for device_id in get_device:
        mock_entry.runtime_data.client.send_message.assert_any_call(
            "getDevice", {"deviceId": device_id, "subscribe": True}
        )
    assert mock_entry.runtime_data.devices[1].device_transit_policy_id is None
