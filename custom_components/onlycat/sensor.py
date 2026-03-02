"""Sensor platform for OnlyCat."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import MATCH_ALL
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .api import OnlyCatApiClient
    from .coordinator import OnlyCatDataUpdateCoordinator
    from .data import Device, OnlyCatConfigEntry
    from .data.policy import DeviceTransitPolicy


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: OnlyCatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the text platform."""
    entities = [
        OnlyCatPolicySensor(
            coordinator=entry.runtime_data.coordinator,
            device=device,
            policy=policy,
            policy_id=policy_id,
            api_client=entry.runtime_data.client,
        )
        for device in entry.runtime_data.devices
        for policy_id, policy in (device.device_transit_policies or {}).items()
    ]
    async_add_entities(entities)
    entry.runtime_data.coordinator.async_update_listeners()


class OnlyCatPolicySensor(CoordinatorEntity, SensorEntity):
    """Door policy for the flap."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "onlycat_policy_sensor"
    _unrecorded_attributes = frozenset({MATCH_ALL})

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to map to a device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device.device_id)},
            name=self.device.description,
            serial_number=self.device.device_id,
        )

    def __init__(
        self,
        coordinator: OnlyCatDataUpdateCoordinator,
        device: Device,
        policy: DeviceTransitPolicy,
        policy_id: int,
        api_client: OnlyCatApiClient,
    ) -> None:
        """Initialize the sensor class."""
        CoordinatorEntity.__init__(self, coordinator, device.device_id)
        self.coordinator = coordinator
        self.entity_description = SensorEntityDescription(
            key="OnlyCat",
            name="Door Policy: " + policy.name,
            icon="mdi:home-clock",
            translation_key="onlycat_policy_sensor",
        )
        self._api_client = api_client
        self._attr_unique_id = (
            device.device_id.replace("-", "_").lower()
            + "_policy_"
            + policy.name.replace(" ", "_").lower()
        )
        self.policy_id = policy_id
        self.policy = policy
        self.device: Device = device
        self.coordinator.async_add_listener(self.update_sensor)
        self.device.add_policy_update_listener(self.update_sensor)

    @callback
    def update_sensor(self) -> None:
        """Update the sensor state."""
        self._attr_native_value = "Configured"
        self.policy = self.device.device_transit_policies.get(self.policy_id)
        self._attr_extra_state_attributes = {
            "policy": self.policy.to_dict(),
            "policy_json": json.dumps(self.policy.to_dict()),
        }
        self.async_write_ha_state()
