"""Provides services for OnlyCat."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import voluptuous as vol
from homeassistant.const import STATE_HOME, STATE_NOT_HOME
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from custom_components.onlycat.data import OnlyCatConfigEntry

from .const import DOMAIN
from .data.event import Event
from .data.event_summary import EventSummary
from .device_tracker import OnlyCatPetTracker

_LOGGER = logging.getLogger(__name__)

BACKFILL_DELAY_SECONDS = 0.5
BACKFILL_SCHEMA = vol.Schema(
    {
        vol.Optional("days", default=7): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=31)
        ),
        vol.Optional("maximum_events", default=100): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=500)
        ),
    }
)


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

    async def backfill_event_summaries_handler(
        call: ServiceCall,
    ) -> ServiceResponse:
        """Handle a bounded, manually requested event-summary backfill."""
        return await async_handle_backfill_event_summaries(call, entry)

    hass.services.async_register(
        DOMAIN,
        "backfill_event_summaries",
        backfill_event_summaries_handler,
        schema=BACKFILL_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
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


async def async_handle_backfill_event_summaries(
    call: ServiceCall,
    entry: OnlyCatConfigEntry,
) -> ServiceResponse:
    """Replay available gateway history into the event sensor and HA recorder."""
    days = call.data["days"]
    maximum_events = call.data["maximum_events"]
    cutoff = datetime.now(UTC) - timedelta(days=days)
    listed = 0
    eligible = 0
    replayed = 0
    skipped = 0
    failed = 0

    for device in entry.runtime_data.devices:
        try:
            raw_events = await entry.runtime_data.client.send_message(
                "getDeviceEvents",
                {"deviceId": device.device_id, "subscribe": False},
                notify_listeners=False,
            )
            raw_events = raw_events if isinstance(raw_events, list) else []
            listed += len(raw_events)
            events = [
                event
                for raw_event in raw_events
                if (event := Event.from_api_response(raw_event)) is not None
                and event.device_id == device.device_id
                and event.timestamp is not None
                and event.timestamp >= cutoff
                and event.access_token
            ]
            events.sort(key=lambda event: event.timestamp)
            events = events[-maximum_events:]
            eligible += len(events)

            for event in events:
                try:
                    raw_summary = await entry.runtime_data.client.send_message(
                        "getEventSummary",
                        {
                            "deviceId": device.device_id,
                            "eventId": event.event_id,
                            "accessToken": event.access_token,
                            "subscribe": False,
                        },
                        notify_listeners=False,
                    )
                    summary = (
                        EventSummary.from_api_response(raw_summary)
                        if isinstance(raw_summary, dict)
                        else None
                    )
                    if (
                        summary is None
                        or summary.device_id != device.device_id
                        or summary.event_id != event.event_id
                    ):
                        skipped += 1
                        continue
                    await entry.runtime_data.event_store.run_history_replay_listeners(
                        event, summary
                    )
                    replayed += 1
                except Exception:  # noqa: BLE001
                    failed += 1
                    _LOGGER.exception(
                        "Could not backfill OnlyCat event %s", event.event_id
                    )
                finally:
                    await asyncio.sleep(BACKFILL_DELAY_SECONDS)
        finally:
            await entry.runtime_data.event_store.restore_history_replay_listeners(
                device.device_id
            )

    result = {
        "listed": listed,
        "eligible": eligible,
        "replayed": replayed,
        "skipped": skipped,
        "failed": failed,
    }
    _LOGGER.info("OnlyCat event-summary backfill completed: %s", result)
    return result
