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

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .data.device import Device
    from .data.event import Event
    from .data.event_store import EventStore
    from .data.event_summary import EventSummary


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
        event_store: EventStore,
    ) -> None:
        """Initialize the sensor class."""
        self.entity_description = ENTITY_DESCRIPTION
        self._attr_is_on = False
        self._attr_extra_state_attributes = {}
        self._attr_raw_data = None
        self.device: Device = device
        self._attr_unique_id = device.device_id.replace("-", "_").lower() + "_event"
        self._event_store = event_store
        self.entity_id = "binary_sensor." + self._attr_unique_id

        self._event_store.add_event_listener(
            self.device.device_id, self.on_event_update
        )
        self._event_store.add_event_summary_listener(
            self.device.device_id, self.on_event_summary_update
        )
        self._event_store.add_history_replay_listener(
            self.device.device_id, self.on_history_replay
        )

    def _write_event(
        self,
        event: Event,
        summary: EventSummary | None = None,
        *,
        historical: bool = False,
    ) -> None:
        """Write an event and its exact subevent attribution to Home Assistant."""
        previous_event_id = self._attr_extra_state_attributes.get("eventId")
        if previous_event_id != event.event_id:
            _LOGGER.info(
                "Event ID has changed (%s -> %s), updating state.",
                previous_event_id,
                event.event_id,
            )

        attributes = {
            "eventId": event.event_id,
            "timestamp": event.timestamp,
        }
        if event.event_trigger_source:
            attributes["eventTriggerSource"] = event.event_trigger_source.name
        if event.event_classification:
            attributes["eventClassification"] = event.event_classification.name

        rfid_codes = set(event.rfid_codes or [])
        if summary is not None and summary.event_id == event.event_id:
            attributes["eventSummary"] = [
                {
                    "startFrameIndex": subevent.start_frame_index,
                    "endFrameIndex": subevent.end_frame_index,
                    "rfidCode": subevent.rfid_code,
                    "direction": subevent.direction,
                    "action": subevent.action,
                }
                for subevent in summary.subevents
            ]
            if summary.processed_frame_count is not None:
                attributes["processedFrameCount"] = summary.processed_frame_count
            rfid_codes.update(
                subevent.rfid_code
                for subevent in summary.subevents
                if subevent.rfid_code
            )
        if rfid_codes:
            attributes["rfidCodes"] = sorted(rfid_codes)

        self._attr_extra_state_attributes = attributes
        if historical or event.frame_count is not None:
            self._attr_is_on = False
        elif previous_event_id != event.event_id:
            self._attr_is_on = True
        self.async_write_ha_state()

    async def on_event_update(self, event: Event) -> None:
        """Handle event update."""
        if not event:
            return
        summary = self._event_store.get_current_summary(self.device.device_id)
        if summary is not None and summary.event_id != event.event_id:
            summary = None
        self._write_event(event, summary)

    async def on_event_summary_update(self, summary: EventSummary) -> None:
        """Merge exact RFID, direction, and action details into the current event."""
        event_id = self._attr_extra_state_attributes.get("eventId")
        if summary.event_id != event_id:
            return
        event = self._event_store.get_current_event(self.device.device_id)
        if event is not None and event.event_id == summary.event_id:
            self._write_event(event, summary)

    async def on_history_replay(
        self,
        event: Event,
        summary: EventSummary | None,
        historical: bool,
    ) -> None:
        """Record a historical event, then allow the live event to be restored."""
        self._write_event(event, summary, historical=historical)
