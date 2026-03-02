"""Provides services for OnlyCat."""

import json
import logging

import voluptuous as vol
from homeassistant.const import STATE_HOME, STATE_NOT_HOME
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from custom_components.onlycat.data import OnlyCatConfigEntry

from .const import DOMAIN
from .device_tracker import OnlyCatPetTracker

_LOGGER = logging.getLogger(__name__)


def _get_pet_tracker_entity(call: ServiceCall) -> OnlyCatPetTracker:
    """Get the pet tracker entity from the service call."""
    device_tracker_id: str = call.data["device_tracker"]
    entity_component = call.hass.data.get("entity_components", {}).get("device_tracker")
    if not entity_component:
        error = "Device tracker component not found"
        raise ServiceValidationError(error)
    entity_obj = entity_component.get_entity(device_tracker_id)
    if not entity_obj:
        error = f"Entity {device_tracker_id} not found"
        raise ServiceValidationError(error)
    if not isinstance(entity_obj, OnlyCatPetTracker):
        error = f"Entity {device_tracker_id} is not an OnlyCatPetTracker entity"
        raise ServiceValidationError(error)
    return entity_obj


async def async_setup_services(hass: HomeAssistant, entry: OnlyCatConfigEntry) -> None:
    """Create services for OnlyCat."""
    hass.services.async_register(
        DOMAIN,
        "set_pet_location",
        async_handle_set_pet_presence,
        schema=vol.Schema(
            {
                vol.Required("device_tracker"): cv.entity_id,
                vol.Required("location"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "toggle_pet_location",
        async_handle_toggle_pet_presence,
        schema=vol.Schema(
            {
                vol.Required("device_tracker"): cv.entity_id,
            }
        ),
    )

    async def update_device_policy_handler(call: ServiceCall) -> ServiceResponse:
        """Handle service call and inject entry."""
        return await async_handle_update_device_policy(call, entry)

    hass.services.async_register(
        DOMAIN,
        "update_device_policy",
        update_device_policy_handler,
        schema=vol.Schema(
            {
                vol.Required("policy_data"): cv.string,
            }
        ),
    )


async def async_handle_set_pet_presence(call: ServiceCall) -> ServiceResponse:
    """Handle the set presence service call."""
    location: str = call.data["location"]
    entity_obj = _get_pet_tracker_entity(call)
    new_state = STATE_HOME if location.lower() == "home" else STATE_NOT_HOME
    await entity_obj.manual_update_location(new_state)
    _LOGGER.info("Set %s presence to: %s", entity_obj.entity_id, location)


async def async_handle_toggle_pet_presence(call: ServiceCall) -> ServiceResponse:
    """Handle the toggle presence service call."""
    entity_obj = _get_pet_tracker_entity(call)
    current_state = entity_obj.state
    new_state = STATE_NOT_HOME if current_state == STATE_HOME else STATE_HOME
    await entity_obj.manual_update_location(new_state)
    _LOGGER.info("Toggled %s presence to: %s", entity_obj.entity_id, new_state)


async def async_handle_update_device_policy(
    call: ServiceCall,
    entry: OnlyCatConfigEntry,
) -> ServiceResponse:
    """Handle the set device policy service call."""
    policy_data: str = call.data["policy_data"]
    policy_dict = json.loads(policy_data)
    response = await entry.runtime_data.client.send_message(
        "updateDeviceTransitPolicy", policy_dict
    )
    await entry.runtime_data.coordinator.async_refresh()
    _LOGGER.info("Updated device policy %s: %s", policy_data, response)
