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
    name="Flap event",
    device_class=BinarySensorDeviceClass.MOTION,
    translation_key="onlycat_event_sensor",
)


class OnlyCatEventSensor(BinarySensorEntity):
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
        self._attr_is_on = False
        self._attr_extra_state_attributes = {}
        self._attr_raw_data = None
        self.device: Device = device
        self._attr_unique_id = device.device_id.replace("-", "_").lower() + "_event"
        self._api_client = api_client
        self.entity_id = "sensor." + self._attr_unique_id

        api_client.add_event_listener("deviceEventUpdate", self.on_event_update)
        api_client.add_event_listener("eventUpdate", self.on_event_update)
        api_client.add_event_listener("getEvent", self.on_event)

    async def on_event(self, data: dict) -> None:
        """Handle bare event like returned from getEvent."""
        if data["deviceId"] != self.device.device_id:
            return
        self.determine_new_state(Event.from_api_response(data))
        self.async_write_ha_state()

    async def on_event_update(self, data: dict) -> None:
        """Handle event update event."""
        if data["deviceId"] != self.device.device_id:
            return

        self.determine_new_state(EventUpdate.from_api_response(data).event)
        self.async_write_ha_state()

    def determine_new_state(self, event: Event) -> None:
        """Determine the new state of the sensor based on the event."""
        if (self._attr_extra_state_attributes.get("eventId")) != event.event_id:
            _LOGGER.debug(
                "Event ID has changed (%s -> %s), updating state.",
                self._attr_extra_state_attributes.get("eventId"),
                event.event_id,
            )
            self._attr_is_on = True

            self._attr_extra_state_attributes = {
                "eventId": event.event_id,
                "timestamp": event.timestamp,
                "eventTriggerSource": event.event_trigger_source.name,
            }
            if event.rfid_codes:
                self._attr_extra_state_attributes["rfidCodes"] = event.rfid_codes
        elif event.frame_count:
            # Frame count is present, event is concluded
            self._attr_is_on = False
            self._attr_extra_state_attributes = {}
        else:
            if event.event_classification:
                self._attr_extra_state_attributes["eventClassification"] = (
                    event.event_classification.name
                )
            if event.rfid_codes:
                self._attr_extra_state_attributes["rfidCodes"] = event.rfid_codes
