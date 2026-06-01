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

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .data import OnlyCatConfigEntry
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
    async_add_entities(
        OnlyCatPetTracker(pet=pet, event_store=entry.runtime_data.event_store)
        for pet in entry.runtime_data.event_store.get_pets()
    )


class OnlyCatPetTracker(TrackerEntity):
    """OnlyCat Tracker class."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_source_type = SourceType.ROUTER

    def __init__(
        self,
        pet: Pet,
        event_store: EventStore,
    ) -> None:
        """Initialize the sensor class."""
        self.entity_description = ENTITY_DESCRIPTION
        self._attr_raw_data = None
        self.pet: Pet = pet
        self._event_store = event_store
        self.pet_name = pet.label if pet.label is not None else pet.rfid_code
        self._attr_translation_placeholders = {
            "pet_name": self.pet_name,
        }
        self._attr_unique_id = pet.rfid_code + "_tracker"
        self.entity_id = "device_tracker." + self._attr_unique_id
        self._attr_location_name = STATE_NOT_HOME
        self._event_store.add_pet_listener(pet.rfid_code, self.on_pet_update)

    async def on_pet_update(self, pet: Pet) -> None:
        """Handle updates to the pet data."""
        if pet.rfid_code != self.pet.rfid_code:
            return
        self.pet = pet
        self._attr_location_name = pet.location
        self._attr_last_seen = pet.last_seen
        self.async_write_ha_state()

    async def manual_update_location(self, location: str) -> None:
        """Manually override current state of a pets device tracker."""
        if location not in (STATE_HOME, STATE_NOT_HOME):
            _LOGGER.debug("Manual update of location cannot be set to %s", location)
            return
        self.pet.location = location
        self._attr_location_name = location
        self.async_write_ha_state()
