"""Sensor platform for OnlyCat."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data.device import DeviceUpdate

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from . import Device
    from .api import OnlyCatApiClient

ENTITY_DESCRIPTION = BinarySensorEntityDescription(
    key="OnlyCat",
    name="Connectivity",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    translation_key="onlycat_connection_sensor",
)


class OnlyCatConnectionSensor(BinarySensorEntity):
    """OnlyCat Sensor class."""

    _attr_has_entity_name = True
    _attr_should_poll = False

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
        device: Device,
        api_client: OnlyCatApiClient,
    ) -> None:
        """Initialize the sensor class."""
        self.entity_description = ENTITY_DESCRIPTION
        self._attr_is_on = device.connectivity.connected
        self._attr_raw_data = None
        self.device = device
        self._attr_unique_id = (
            device.device_id.replace("-", "_").lower() + "_connectivity"
        )
        self._api_client = api_client
        self.entity_id = "binary_sensor." + self._attr_unique_id

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates once the entity has been added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._api_client.add_event_listener("deviceUpdate", self.on_device_update)
        )

    async def on_device_update(self, data: dict) -> None:
        """Handle device update event."""
        if data["deviceId"] != self.device.device_id:
            return

        device_update = DeviceUpdate.from_api_response(data)

        self._attr_raw_data = str(data)
        if device_update.body.connectivity:
            self._attr_is_on = device_update.body.connectivity.connected
        self.async_write_ha_state()
