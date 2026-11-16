"""Sensor platform for OnlyCat."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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


# Measures the platform stores but this integration does not expose as attributes.
HIDDEN_MEASURES = frozenset(
    {
        "bluetooth_state",
        "bluetooth_state_change_count",
        "target_lock_state_change_count",
    }
)


def latest_measures(samples: Any) -> dict:
    """
    Return the measures of the newest telemetry sample.

    `samples` is the reply to getDeviceTelemetry, newest first:

        [{deviceId, timestamp, measures: {name: value, ...}}, ...]

    Anything else (no reply, an error object, no sample in the window) gives {}.
    Measures in HIDDEN_MEASURES are left out.
    """
    if not isinstance(samples, list) or not samples:
        return {}
    measures = samples[0].get("measures") if isinstance(samples[0], dict) else None
    if not isinstance(measures, dict):
        return {}
    return {
        name: value for name, value in measures.items() if name not in HIDDEN_MEASURES
    }


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
        self.entity_id = "binary_sensor." + self._attr_unique_id

    @callback
    def _handle_coordinator_update(self) -> None:
        """
        Handle updated data from the coordinator.

        The `errors` attribute now carries one object per reboot, from
        getDeviceRebootLogs:

            {deviceId, timestamp, build, cause, isError, summary, detail, message}

        With detailed metrics enabled, every measure of the device's latest
        telemetry sample is added as an attribute of its own.
        """
        self._attr_is_on = (
            len(self.coordinator.data[self.device.device_id]["errors"]) > 0
        )
        self._attr_extra_state_attributes = {
            "errors": self.coordinator.data[self.device.device_id]["errors"]
        } | latest_measures(self.coordinator.data[self.device.device_id].get("metrics"))
        self.async_write_ha_state()
