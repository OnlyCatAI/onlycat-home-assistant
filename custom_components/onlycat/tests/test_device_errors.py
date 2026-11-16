"""Test of the detailed-metrics attributes on the OnlyCat error sensor."""

from custom_components.onlycat.binary_sensor_device_errors import latest_measures


def test_latest_measures_takes_the_newest_sample() -> None:
    """The reply is newest first, so the first sample's measures are used."""
    samples = [
        {
            "deviceId": "OC-00000000001",
            "timestamp": "2026-11-16T18:00:00.000Z",
            "measures": {"tcpu": 41.5, "wifi_rssi": -58, "build": 520},
        },
        {
            "deviceId": "OC-00000000001",
            "timestamp": "2026-11-16T17:59:00.000Z",
            "measures": {"tcpu": 40.0, "wifi_rssi": -60, "build": 520},
        },
    ]
    assert latest_measures(samples) == {"tcpu": 41.5, "wifi_rssi": -58, "build": 520}


def test_latest_measures_leaves_out_hidden_measures() -> None:
    """The bluetooth and target-lock measures are not exposed as attributes."""
    samples = [
        {
            "deviceId": "OC-00000000001",
            "timestamp": "2026-11-16T18:00:00.000Z",
            "measures": {
                "tcpu": 41.5,
                "bluetooth_state": 2,
                "bluetooth_state_change_count": 1,
                "target_lock_state_change_count": 0,
                "lock_state_change_count": 3,
            },
        }
    ]
    assert latest_measures(samples) == {"tcpu": 41.5, "lock_state_change_count": 3}


def test_latest_measures_without_a_usable_reply() -> None:
    """No reply, an error object or an empty window all give no attributes."""
    assert latest_measures(None) == {}
    assert latest_measures([]) == {}
    assert latest_measures({"message": "Failed to fetch device telemetry."}) == {}
    assert latest_measures([{"deviceId": "OC-00000000001"}]) == {}
