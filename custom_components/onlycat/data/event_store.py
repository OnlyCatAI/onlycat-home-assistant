"""Manage global store of events per device."""

import logging
from collections.abc import Callable

from custom_components.onlycat.api import OnlyCatApiClient

from .event import Event, EventUpdate

_LOGGER = logging.getLogger(__name__)


class EventStore:
    """Store events for each device and manage callbacks."""

    def __init__(self, api_client: OnlyCatApiClient) -> None:
        """Initialize EventStore with given api client."""
        self._event_update_listeners: dict[str, list[Callable]] = {}
        self._current_events: dict[str, Event] = {}
        self._api_client: OnlyCatApiClient = api_client

    async def send_get_event_message(self, device_id: str, event_id: int, subscribe: bool = True) -> None:
        """Send getEvent message to get latest full event."""
        await self._api_client.send_message(
            "getEvent",
            {
                "deviceId": device_id,
                "eventId": event_id,
                "subscribe": subscribe,
            },
        )

    async def on_device_event_update(self, data: dict) -> None:
        """Handle deviceEventUpdate messages."""
        await self.send_get_event_message(data["deviceId"], data["eventId"])

    async def on_event_update(self, data: dict) -> None:
        """Handle eventUpdate messages."""
        update = EventUpdate.from_api_response(data)
        if not update:
            return
        if update.device_id not in self._current_events:
            self._current_events[update.device_id] = update.event
        else:
            self._current_events[update.device_id].update_from(update.event)
        if self._current_events[update.device_id].frame_count is not None:
            await self.send_get_event_message(update.device_id, update.event_id, subscribe=False)
            return
        await self.run_listeners(update.device_id)

    async def on_get_event(self, data: dict) -> None:
        """Handle replies from getEvent messages."""
        event = Event.from_api_response(data)
        if not event:
            return
        if event.device_id not in self._current_events:
            self._current_events[event.device_id] = event
        else:
            self._current_events[event.device_id].update_from(event)
        await self.run_listeners(event.device_id)

    async def run_listeners(self, device_id: str) -> None:
        """Call all listeners for a given device."""
        for callback in self._event_update_listeners[device_id]:
            await callback(self._current_events.get(device_id, None))

    def add_event_listener(self, device_id: str, callback: Callable) -> None:
        """Add function to a devices listener list."""
        if device_id not in self._event_update_listeners:
            self._event_update_listeners[device_id] = []
        self._event_update_listeners[device_id].append(callback)
