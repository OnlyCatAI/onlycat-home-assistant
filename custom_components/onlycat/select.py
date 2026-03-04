"""Select platform for OnlyCat."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.select import (
    SelectEntity,
    SelectEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .data.device import DeviceUpdate

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .api import OnlyCatApiClient
    from .coordinator import OnlyCatDataUpdateCoordinator
    from .data import Device, OnlyCatConfigEntry


ENTITY_DESCRIPTION = SelectEntityDescription(
    key="OnlyCat",
    name="Door Policy",
    entity_category=EntityCategory.CONFIG,
    icon="mdi:home-clock",
    translation_key="onlycat_policy_select",
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: OnlyCatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    entities = [
        OnlyCatPolicySelect(
            coordinator=entry.runtime_data.coordinator,
            device=device,
            entity_description=ENTITY_DESCRIPTION,
            api_client=entry.runtime_data.client,
        )
        for device in entry.runtime_data.devices
    ]
    async_add_entities(entities)
    entry.runtime_data.coordinator.async_update_listeners()


class OnlyCatPolicySelect(CoordinatorEntity, SelectEntity):
    """Door policy for the flap."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_category = EntityCategory.CONFIG
    _attr_translation_key = "onlycat_policy_select"

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
        entity_description: SelectEntityDescription,
        api_client: OnlyCatApiClient,
    ) -> None:
        """Initialize the sensor class."""
        CoordinatorEntity.__init__(self, coordinator, device.device_id)
        self.coordinator = coordinator
        self.entity_description = entity_description
        self._state = None
        self._attr_raw_data = None
        self._api_client = api_client
        self._attr_unique_id = device.device_id.replace("-", "_").lower() + "_policy"
        self.entity_id = "select." + self._attr_unique_id
        self._attr_options = [
            policy.name for policy in (device.device_transit_policies or {}).values()
        ]
        self.device: Device = device
        self._policies = device.device_transit_policies
        if device.device_transit_policy_id is not None:
            self.set_current_policy(device.device_transit_policy_id)
        api_client.add_event_listener("deviceUpdate", self.on_device_update)
        self.coordinator.async_add_listener(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._policies = self.device.device_transit_policies
        self._attr_options = [
            policy.name
            for policy in (self.device.device_transit_policies or {}).values()
        ]
        self.async_write_ha_state()

    def set_current_policy(self, policy_id: int) -> None:
        """Set the current policy."""
        _LOGGER.debug(
            "Setting policy %s for device %s", policy_id, self.device.device_id
        )
        policy = self.device.device_transit_policies.get(policy_id)
        if policy is None or policy.name is None:
            return
        self._attr_current_option = policy.name

    async def on_device_update(self, data: dict) -> None:
        """Handle device update event."""
        if data["deviceId"] != self.device.device_id:
            return
        _LOGGER.debug("Device update event received for select: %s", data)
        device_update = DeviceUpdate.from_api_response(data)
        self._attr_options = [
            policy.name
            for policy in (self.device.device_transit_policies or {}).values()
        ]
        if device_update.body.device_transit_policy_id:
            self.set_current_policy(device_update.body.device_transit_policy_id)
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Activate a device policy."""
        _LOGGER.debug("Setting policy %s for device %s", option, self.device.device_id)
        policy_id = next(
            (
                key
                for key, policy in self.device.device_transit_policies.items()
                if policy.name == option
            ),
            None,
        )
        await self._api_client.send_message(
            "activateDeviceTransitPolicy",
            {"deviceId": self.device.device_id, "deviceTransitPolicyId": policy_id},
        )
