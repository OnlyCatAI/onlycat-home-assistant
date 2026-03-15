"""Sensor platform for OnlyCat."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data.event import Event

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .api import OnlyCatApiClient
    from .data.device import Device
    from .data.event_store import EventStore

ENTITY_DESCRIPTION = BinarySensorEntityDescription(
    key="OnlyCat",
    name="Lock",
    device_class=BinarySensorDeviceClass.LOCK,
    translation_key="onlycat_lock_sensor",
)


class OnlyCatLockSensor(BinarySensorEntity):
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
        event_store: EventStore,
    ) -> None:
        """Initialize the sensor class."""
        self.entity_description = ENTITY_DESCRIPTION
        self.device: Device = device
        self._current_event: Event = Event()
        self._attr_is_on = self.device.is_unlocked_in_idle_state()
        self._attr_unique_id = device.device_id.replace("-", "_").lower() + "_lock"
        self._event_store = event_store
        self.entity_id = "sensor." + self._attr_unique_id

        self._event_store.add_event_listener(
            self.device.device_id, self.on_event_update
        )
        api_client.add_event_listener("deviceUpdate", self.on_device_update)

    async def on_event_update(self, event: Event) -> None:
        """Handle event update event."""
        if event.frame_count:
            self._attr_is_on = self.device.is_unlocked_in_idle_state()
        else:
            unlocked = self.device.is_unlocked_by_event(event)
            if unlocked is not None:
                _LOGGER.debug("Lock state changed to %s for event %s", unlocked, event)
                self._attr_is_on = unlocked
        self.async_write_ha_state()

    async def on_device_update(self, data: dict) -> None:
        """Handle device update event."""
        if data["deviceId"] != self.device.device_id:
            return
        self._attr_is_on = self.device.is_unlocked_in_idle_state()
        self.async_write_ha_state()
