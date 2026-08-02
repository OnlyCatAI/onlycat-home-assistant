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

BACKFILL_DELAY_SECONDS = 1.0
BACKFILL_PAGE_DELAY_SECONDS = 1.0
BACKFILL_PROGRESS_INTERVAL = 25
BACKFILL_SCHEMA = vol.Schema(
    {
        vol.Optional("all_history", default=False): cv.boolean,
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


async def _get_device_event_history(
    entry: OnlyCatConfigEntry,
    device_id: str,
    *,
    all_history: bool,
) -> tuple[list[Event], int, int]:
    """Fetch one recent page or paginate through all retained device events."""
    events_by_id: dict[int, Event] = {}
    before_global_id: int | None = None
    seen_cursors: set[int] = set()
    pages = 0
    listed = 0

    while True:
        request = {"deviceId": device_id, "subscribe": False}
        if before_global_id is not None:
            request["beforeGlobalId"] = before_global_id

        raw_events = await entry.runtime_data.client.send_message(
            "getDeviceEvents",
            request,
            notify_listeners=False,
        )
        pages += 1
        raw_events = raw_events if isinstance(raw_events, list) else []
        listed += len(raw_events)

        page_events = [
            event
            for raw_event in raw_events
            if (event := Event.from_api_response(raw_event)) is not None
            and event.device_id == device_id
            and event.event_id is not None
            and event.timestamp is not None
        ]
        for event in page_events:
            events_by_id[event.event_id] = event

        if not all_history or not raw_events:
            break

        global_ids = [
            event.global_id for event in page_events if isinstance(event.global_id, int)
        ]
        if not global_ids:
            _LOGGER.warning(
                "OnlyCat history page for %s had no global IDs; stopping pagination",
                device_id,
            )
            break

        next_cursor = min(global_ids)
        if next_cursor in seen_cursors or (
            before_global_id is not None and next_cursor >= before_global_id
        ):
            _LOGGER.warning(
                "OnlyCat history cursor did not move backwards for %s; stopping at %s",
                device_id,
                next_cursor,
            )
            break

        seen_cursors.add(next_cursor)
        before_global_id = next_cursor
        await asyncio.sleep(BACKFILL_PAGE_DELAY_SECONDS)

    return list(events_by_id.values()), pages, listed


async def _get_historical_event_summary(
    entry: OnlyCatConfigEntry,
    device_id: str,
    event: Event,
) -> EventSummary | None:
    """Fetch and validate one historical event summary."""
    if not event.access_token:
        return None

    raw_summary = await entry.runtime_data.client.send_message(
        "getEventSummary",
        {
            "deviceId": device_id,
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
        or summary.device_id != device_id
        or summary.event_id != event.event_id
    ):
        return None
    return summary


async def async_handle_backfill_event_summaries(
    call: ServiceCall,
    entry: OnlyCatConfigEntry,
) -> ServiceResponse:
    """Replay available gateway history into the event sensor and HA recorder."""
    all_history = call.data.get("all_history", False)
    days = call.data.get("days", 7)
    maximum_events = call.data.get("maximum_events", 100)
    cutoff = None if all_history else datetime.now(UTC) - timedelta(days=days)
    pages = 0
    listed = 0
    unique_events = 0
    eligible = 0
    replayed = 0
    skipped = 0
    failed = 0
    summaries = 0

    for device in entry.runtime_data.devices:
        try:
            events, device_pages, device_listed = await _get_device_event_history(
                entry, device.device_id, all_history=all_history
            )
            pages += device_pages
            listed += device_listed
            unique_events += len(events)
            events = [
                event for event in events if cutoff is None or event.timestamp >= cutoff
            ]
            events.sort(key=lambda event: event.timestamp)
            if not all_history:
                events = events[-maximum_events:]
            eligible += len(events)

            for index, event in enumerate(events, start=1):
                summary = None
                if event.access_token:
                    try:
                        summary = await _get_historical_event_summary(
                            entry, device.device_id, event
                        )
                    except Exception:
                        failed += 1
                        _LOGGER.exception(
                            "Could not fetch the summary for OnlyCat event %s; "
                            "replaying its base event",
                            event.event_id,
                        )
                    await asyncio.sleep(BACKFILL_DELAY_SECONDS)

                if summary is None:
                    skipped += 1
                else:
                    summaries += 1
                await entry.runtime_data.event_store.run_history_replay_listeners(
                    event, summary
                )
                replayed += 1

                if index % BACKFILL_PROGRESS_INTERVAL == 0:
                    _LOGGER.info(
                        "OnlyCat history backfill progress for %s: %s/%s events",
                        device.device_id,
                        index,
                        len(events),
                    )
        finally:
            await entry.runtime_data.event_store.restore_history_replay_listeners(
                device.device_id
            )

    result = {
        "pages": pages,
        "listed": listed,
        "unique_events": unique_events,
        "eligible": eligible,
        "replayed": replayed,
        "summaries": summaries,
        "skipped": skipped,
        "failed": failed,
    }
    _LOGGER.info("OnlyCat event-summary backfill completed: %s", result)
    return result
