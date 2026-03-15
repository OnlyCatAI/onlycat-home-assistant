"""Tracker platform for OnlyCat."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.device_tracker import (
    SourceType,
    TrackerEntity,
    TrackerEntityDescription,
)
from homeassistant.const import STATE_HOME, STATE_NOT_HOME
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data.event import Event

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .data import OnlyCatConfigEntry
    from .data.device import Device
    from .data.event import Event
    from .data.event_store import EventStore
    from .data.pet import Pet


ENTITY_DESCRIPTION = TrackerEntityDescription(
    key="OnlyCat",
    name="Pet Tracker",
    icon="mdi:cat",
    translation_key="onlycat_pet_tracker",
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: OnlyCatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the tracker platform."""
    if entry.runtime_data.pets:
        async_add_entities(
            sensor
            for pet in entry.runtime_data.pets
            for sensor in (
                OnlyCatPetTracker(pet=pet, event_store=entry.runtime_data.event_store),
            )
        )


class OnlyCatPetTracker(TrackerEntity):
    """OnlyCat Tracker class."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_source_type = SourceType.ROUTER

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to map to a device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device.device_id)},
            name=self.device.description,
            serial_number=self.device.device_id,
        )

    def determine_new_state(self, event: Event) -> None:
        """Determine the new state of the sensor based on the event."""
        present = self.pet.is_present(event)
        if present is not None:
            self._attr_location_name = STATE_HOME if present else STATE_NOT_HOME

    def __init__(
        self,
        pet: Pet,
        event_store: EventStore,
    ) -> None:
        """Initialize the sensor class."""
        self.entity_description = ENTITY_DESCRIPTION
        self._attr_raw_data = None
        self.device: Device = pet.device
        self.pet: Pet = pet
        self._event_store = event_store
        self.pet_name = pet.label if pet.label is not None else pet.rfid_code
        self._attr_translation_placeholders = {
            "pet_name": self.pet_name,
        }
        self._attr_unique_id = (
            self.device.device_id.replace("-", "_").lower()
            + "_"
            + pet.rfid_code
            + "_tracker"
        )
        self.entity_id = "sensor." + self._attr_unique_id
        self._attr_location_name = STATE_NOT_HOME
        if pet.last_seen_event:
            self.determine_new_state(pet.last_seen_event)
        self._event_store.add_event_listener(
            self.device.device_id, self.on_event_update
        )

    async def on_event_update(self, event: Event) -> None:
        """Handle event update event."""
        if event.rfid_codes is None or self.pet.rfid_code not in event.rfid_codes:
            return
        self.determine_new_state(event)
        self.async_write_ha_state()

    async def manual_update_location(self, location: str) -> None:
        """Manually override current state of a pets device tracker."""
        if location not in (STATE_HOME, STATE_NOT_HOME):
            _LOGGER.debug("Manual update of location cannot be set to %s", location)
            return
        self._attr_location_name = location
        self.async_write_ha_state()
