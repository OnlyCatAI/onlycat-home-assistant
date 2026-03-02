"""Test of OnlyCat Policy Select entity."""

from unittest.mock import AsyncMock

from homeassistant.components.select import SelectEntityDescription

from custom_components.onlycat import Device
from custom_components.onlycat.select import OnlyCatPolicySelect

get_device_transit_policies = [
    [],
    [
        {"deviceTransitPolicyId": 0, "deviceId": "OC-00000000001", "name": "Policy1"},
        {"deviceTransitPolicyId": 1, "deviceId": "OC-00000000001", "name": "Policy2"},
        {"deviceTransitPolicyId": 2, "deviceId": "OC-00000000001", "name": "Policy3"},
    ],
]


def test_empty_onlycat_policy_slect() -> None:
    """Tests initialization of OnlyCatPolicySelect with no active or known policies."""
    mock_device = Device(
        device_id="OC-00000000001",
        description="Test Cat Flap",
        device_transit_policy_id=None,
    )
    entity_description = SelectEntityDescription(
        key="onlycat_policy_select",
    )
    mock_api_client = AsyncMock()
    mock_coordinator = AsyncMock()
    select = OnlyCatPolicySelect(
        coordinator=mock_coordinator,
        device=mock_device,
        entity_description=entity_description,
        api_client=mock_api_client,
    )

    assert select.device.device_id == "OC-00000000001"
    mock_coordinator.async_add_listener.assert_called_once()
