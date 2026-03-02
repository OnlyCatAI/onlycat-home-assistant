"""Tests for data/policy.py:RuleCriteria."""

from datetime import UTC

import pytest

from custom_components.onlycat.data.event import Event
from custom_components.onlycat.data.policy import (
    EventClassification,
    EventFlapstate,
    EventMotionstate,
    EventTriggerSource,
    RuleCriteria,
    TimeRange,
)


@pytest.mark.parametrize(
    "api_criteria",
    [
        {
            "criteria": {
                "eventTriggerSource": 2,
                "eventClassification": [1, 2, 4],
                "rfidCode": ["123456789"],
                "timeRange": ["08:00-10:00"],
                "motionSensorState": 3,
                "flapState": 1,
            },
            "result": {
                "event_trigger_sources": [EventTriggerSource.INDOOR_MOTION],
                "event_classifications": [
                    EventClassification.CLEAR,
                    EventClassification.SUSPICIOUS,
                    EventClassification.HUMAN_ACTIVITY,
                ],
                "rfid_codes": ["123456789"],
                "time_ranges": [TimeRange(8, 0, 10, 0)],
                "motion_sensor_states": [EventMotionstate.OUTDOOR],
                "flap_states": [EventFlapstate.OPEN_OUTWARD],
            },
        },
        {
            "criteria": {
                "eventTriggerSource": [1, 2, 3],
                "eventClassification": [1, 2, 4],
                "rfidCode": ["123456789"],
            },
            "result": {
                "event_trigger_sources": [
                    EventTriggerSource.REMOTE,
                    EventTriggerSource.INDOOR_MOTION,
                    EventTriggerSource.OUTDOOR_MOTION,
                ],
                "event_classifications": [
                    EventClassification.CLEAR,
                    EventClassification.SUSPICIOUS,
                    EventClassification.HUMAN_ACTIVITY,
                ],
                "rfid_codes": ["123456789"],
                "time_ranges": [],
                "motion_sensor_states": [],
                "flap_states": [],
            },
        },
    ],
)
def test_rulecriteria_from_api_response_empty(api_criteria: dict) -> None:
    """Test RuleCriteria.from_api_response method."""
    result = RuleCriteria.from_api_response(api_criteria["criteria"])
    assert (
        result.event_trigger_sources == api_criteria["result"]["event_trigger_sources"]
    )
    assert (
        result.event_classifications == api_criteria["result"]["event_classifications"]
    )
    assert result.rfid_codes == api_criteria["result"]["rfid_codes"]
    assert result.time_ranges == api_criteria["result"]["time_ranges"]
    assert result.motion_sensor_states == api_criteria["result"]["motion_sensor_states"]
    assert result.flap_states == api_criteria["result"]["flap_states"]


rulecriteria_matches_all_criteria = [
    # Lock after flap movement
    RuleCriteria.from_api_response({"flapState": [1, 2]}),
    # Allow out
    RuleCriteria.from_api_response(
        {"eventTriggerSource": 2, "rfidCode": ["123456789"]}
    ),
    # Deny contraband in
    RuleCriteria.from_api_response(
        {
            "eventClassification": [2, 3],
            "eventTriggerSource": 3,
            "rfidCode": ["123456789"],
        }
    ),
    # Allow in
    RuleCriteria.from_api_response(
        {"rfidCode": ["123456789"], "eventTriggerSource": 3}
    ),
    # Deny foreign cats
    RuleCriteria.from_api_response(
        {"rfidCode": ["223456789", "323456789"], "eventTriggerSource": 3}
    ),
]
rulecriteria_matches_all_events = [
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
            "rfidCodes": ["123456789"],
        }
    )
]
rulecriteria_matches_all_results = [[True, True, False, False, False]]


@pytest.mark.parametrize(
    ("event_idx", "event"), list(enumerate(rulecriteria_matches_all_events))
)
@pytest.mark.parametrize(
    ("criteria_idx", "criteria"), list(enumerate(rulecriteria_matches_all_criteria))
)
def test_rulecriteria_matches_all(
    event_idx: int, event: Event, criteria_idx: int, criteria: RuleCriteria
) -> None:
    """Test RuleCriteria.matches method for various criteria and events."""
    match = criteria.matches(event, UTC)
    expected = rulecriteria_matches_all_results[event_idx][criteria_idx]
    assert match == expected, (
        f"Event {event_idx}, Criteria {criteria_idx}: expected {expected}, got {match}"
    )
