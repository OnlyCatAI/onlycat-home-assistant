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
from .data.event import Event, EventClassification

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .data.device import Device
    from .data.event import Event
    from .data.event_store import EventStore

ENTITY_DESCRIPTION = BinarySensorEntityDescription(
    key="OnlyCat",
    name="Contraband",
    device_class=BinarySensorDeviceClass.PROBLEM,
    icon="mdi:rodent",
    translation_key="onlycat_contraband_sensor",
)


class OnlyCatContrabandSensor(BinarySensorEntity):
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
        event_store: EventStore,
    ) -> None:
        """Initialize the sensor class."""
        self.entity_description = ENTITY_DESCRIPTION
        self._attr_is_on = False
        self._attr_raw_data = None
        self.device: Device = device
        self._attr_unique_id = (
            device.device_id.replace("-", "_").lower() + "_contraband"
        )
        self._event_store = event_store
        self.entity_id = "sensor." + self._attr_unique_id
        self._event_store.add_event_listener(
            self.device.device_id, self.on_event_update
        )

    async def on_event_update(self, event: Event) -> None:
        """Handle event update event."""
        if not event:
            return
        if event.frame_count:
            self._attr_is_on = False
        elif event.event_classification == EventClassification.CONTRABAND:
            self._attr_is_on = True
        self.async_write_ha_state()
