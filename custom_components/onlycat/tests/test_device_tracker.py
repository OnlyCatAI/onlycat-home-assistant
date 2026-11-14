"""Tests for OnlyCat pet tracker."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_HOME
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.onlycat.data.event_store import EventStore
from custom_components.onlycat.data.pet import Pet
from custom_components.onlycat.device_tracker import OnlyCatPetTracker


@pytest.mark.asyncio
async def test_pet_listener_lifecycle() -> None:
    """Test that the tracker only listens to pet updates while added to hass."""
    store = EventStore(api_client=AsyncMock())
    pet = Pet(rfid_code="RFID-1", location=STATE_HOME, last_seen=None)
    store.add_pet(pet)
    tracker = OnlyCatPetTracker(pet=pet, event_store=store)
    tracker.async_write_ha_state = MagicMock()

    # Not added to hass yet (e.g. disabled entity): updates must not reach it
    await store.run_pet_listeners(pet.rfid_code)
    tracker.async_write_ha_state.assert_not_called()

    with (
        patch.object(RestoreEntity, "async_added_to_hass", AsyncMock()),
        patch.object(
            OnlyCatPetTracker, "async_get_last_state", AsyncMock(return_value=None)
        ),
    ):
        await tracker.async_added_to_hass()
    await store.run_pet_listeners(pet.rfid_code)
    tracker.async_write_ha_state.assert_called_once()

    # Removed from hass: updates must not reach it anymore
    for remove_callback in tracker._on_remove or []:  # noqa: SLF001
        remove_callback()
    await store.run_pet_listeners(pet.rfid_code)
    tracker.async_write_ha_state.assert_called_once()
