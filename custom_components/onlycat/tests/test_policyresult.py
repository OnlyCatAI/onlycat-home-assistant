"""Tests for data/policy.py:determine_policy_result."""

import pytest

from custom_components.onlycat.data.device import Device
from custom_components.onlycat.data.event import Event
from custom_components.onlycat.data.policy import (
    DeviceTransitPolicy,
    PolicyResult,
)

devices = [
    Device(
        device_id="OC-000000000000",
        settings={
            "ignore_flap_motion_rules": False,
            "ignore_motion_sensor_rules": False,
        },
    ),
    Device(
        device_id="OC-000000000000",
        settings={
            "ignore_flap_motion_rules": True,
            "ignore_motion_sensor_rules": False,
        },
    ),
]

transit_policies = [
    DeviceTransitPolicy.from_api_response(
        {
            "deviceTransitPolicyId": 1,
            "deviceId": "OC-000000000000",
            "name": "Test allow clean in but not out",
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
                                "000000000000000",
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
    ),
    DeviceTransitPolicy.from_api_response(
        {
            "deviceTransitPolicyId": 2,
            "deviceId": "OC-000000000000",
            "name": "Test allow out but lock on movement",
            "transitPolicy": {
                "rules": [
                    {
                        "action": {"lock": True, "final": True},
                        "criteria": {
                            "flapState": [1, 2],
                        },
                        "description": "Lock on Flap Movement",
                    },
                    {
                        "action": {"lock": False},
                        "enabled": True,
                        "criteria": {
                            "rfidCode": [
                                "000000000000000",
                                "000000000000001",
                                "000000000000002",
                            ],
                            "eventTriggerSource": 2,
                        },
                        "description": "Exit Rule",
                    },
                ],
                "idleLock": True,
                "idleLockBattery": True,
            },
        }
    ),
]

events = [
    Event.from_api_response(
        {
            "globalId": 1,
            "deviceId": "OC-000000000000",
            "eventId": 1,
            "timestamp": "2025-10-18T08:15:21Z",
            "frameCount": None,
            "eventTriggerSource": 2,
            "eventClassification": 1,
            "posterFrameIndex": None,
            "accessToken": "0000000",
            "rfidCodes": ["000000000000000"],
        }
    )
]


@pytest.mark.parametrize(
    "test_cases",
    [
        (devices[0], transit_policies[0], events[0], PolicyResult.LOCKED),
        (devices[0], transit_policies[1], events[0], PolicyResult.LOCKED),
        (devices[1], transit_policies[1], events[0], PolicyResult.UNLOCKED),
    ],
)
def test_determine_policy_result(test_cases: tuple) -> None:
    """Test determine_policy_result method of DeviceTransitPolicy."""
    device, transit_policy, event, expected_lock = test_cases
    transit_policy.device = device
    result = transit_policy.determine_policy_result(event)
    assert result == expected_lock
