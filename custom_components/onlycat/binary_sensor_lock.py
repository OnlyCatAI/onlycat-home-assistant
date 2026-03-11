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
from .data.event import Event, EventUpdate

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .api import OnlyCatApiClient
    from .data.device import Device

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
    ) -> None:
        """Initialize the sensor class."""
        self.entity_description = ENTITY_DESCRIPTION
        self.device: Device = device
        self._current_event: Event = Event()
        self._attr_is_on = self.device.is_unlocked_in_idle_state()
        self._attr_unique_id = device.device_id.replace("-", "_").lower() + "_lock"
        self._api_client = api_client
        self.entity_id = "sensor." + self._attr_unique_id

        api_client.add_event_listener("deviceEventUpdate", self.on_event_update)
        api_client.add_event_listener("eventUpdate", self.on_event_update)
        api_client.add_event_listener("deviceUpdate", self.on_device_update)
        api_client.add_event_listener("getEvent", self.on_event)

    async def on_event(self, data: dict) -> None:
        """Handle bare event like returned from getEvent."""
        if data["deviceId"] != self.device.device_id:
            return
        self._current_event.update_from(Event.from_api_response(data))
        self.determine_new_state(self._current_event)
        self.async_write_ha_state()

    async def on_event_update(self, data: dict) -> None:
        """Handle event update event."""
        if data["deviceId"] != self.device.device_id:
            return

        self._current_event.update_from(EventUpdate.from_api_response(data).event)
        self.determine_new_state(self._current_event)
        self.async_write_ha_state()

    async def on_device_update(self, data: dict) -> None:
        """Handle device update event."""
        if data["deviceId"] != self.device.device_id:
            return

        self._attr_is_on = self.device.is_unlocked_in_idle_state()
        self.async_write_ha_state()

    def determine_new_state(self, event: Event) -> None:
        """Determine the new state of the sensor based on the event."""
        if event.frame_count:
            self._attr_is_on = self.device.is_unlocked_in_idle_state()
            self._current_event = Event()
        else:
            unlocked = self.device.is_unlocked_by_event(event)
            if unlocked is not None:
                _LOGGER.debug("Lock state changed to %s for event %s", unlocked, event)
                self._attr_is_on = unlocked
