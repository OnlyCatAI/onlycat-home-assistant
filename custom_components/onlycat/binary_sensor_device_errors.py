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
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .api import OnlyCatApiClient
    from .coordinator import OnlyCatDataUpdateCoordinator
    from .data.device import Device

ENTITY_DESCRIPTION = BinarySensorEntityDescription(
    key="OnlyCat",
    name="Device errors",
    entity_category=EntityCategory.DIAGNOSTIC,
    device_class=BinarySensorDeviceClass.PROBLEM,
    translation_key="onlycat_error_sensor",
)


class OnlyCatErrorSensor(CoordinatorEntity, BinarySensorEntity):
    """OnlyCat Error Sensor class."""

    _attr_has_entity_name = True

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
        api_client: OnlyCatApiClient,
    ) -> None:
        """Initialize the sensor class."""
        CoordinatorEntity.__init__(self, coordinator, device.device_id)
        self.coordinator = coordinator
        self.entity_description = ENTITY_DESCRIPTION
        self._attr_is_on = False
        self._attr_extra_state_attributes = {}
        self._attr_raw_data = None
        self.device: Device = device
        self._attr_unique_id = device.device_id.replace("-", "_").lower() + "_errors"
        self._api_client = api_client
        self.entity_id = "sensor." + self._attr_unique_id
        self.coordinator.async_add_listener(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = (
            len(self.coordinator.data[self.device.device_id]["errors"]) > 0
        )
        if (
            self.coordinator.data[self.device.device_id].get("metrics", None)
            is not None
        ):
            metrics = {}
            for key in [
                x["measureName"]
                for x in self.coordinator.data[self.device.device_id]["metrics"]
            ]:
                tmp = [
                    x
                    for x in self.coordinator.data[self.device.device_id]["metrics"]
                    if x["measureName"] == key
                ]
                if len(tmp) == 0:
                    continue
                tmp.sort(key=lambda x: x["time"], reverse=True)
                metrics[key] = tmp[0]["value"]
        self._attr_extra_state_attributes = {
            "errors": self.coordinator.data[self.device.device_id]["errors"]
        } | (
            metrics
            if self.coordinator.data[self.device.device_id].get("metrics", None)
            is not None
            else {}
        )
        _LOGGER.debug(
            "Updating OnlyCatErrorSensor for device %s: %s",
            self.device.device_id,
            self._attr_extra_state_attributes,
        )
        self.async_write_ha_state()
