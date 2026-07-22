"""Manage global store of events per device."""

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.const import STATE_UNKNOWN

from custom_components.onlycat.api import OnlyCatApiClient
from custom_components.onlycat.data.pet import Pet

from .event import Event, EventUpdate
from .event_summary import EventSummary

_LOGGER = logging.getLogger(__name__)


class EventStore:
    """Store events for each device and manage callbacks."""

    def __init__(self, api_client: OnlyCatApiClient) -> None:
        """Initialize EventStore with given api client."""
        self._event_update_listeners: dict[str, list[Callable]] = {}
        self._event_summary_update_listeners: dict[str, list[Callable]] = {}
        self._pet_update_listeners: dict[str, list[Callable]] = {}
        self._current_events: dict[str, Event] = {}
        self._current_summaries: dict[str, EventSummary] = {}
        self._current_images: dict[str, bytes] = {}
        self._pets: dict[str, Pet] = {}
        self._api_client: OnlyCatApiClient = api_client

    async def send_get_event_message(
        self,
        device_id: str,
        event_id: int,
        subscribe: bool = True,  # noqa: FBT001,FBT002
    ) -> None:
        """Send getEvent message to get latest full event."""
        await self._api_client.send_message(
            "getEvent",
            {
                "deviceId": device_id,
                "eventId": event_id,
                "subscribe": subscribe,
            },
        )

    async def send_get_event_summary(
        self,
        device_id: str,
        event_id: int,
        access_token: str,
        subscribe: bool = True,  # noqa: FBT001,FBT002
    ) -> Any:
        """Send getEventSummary message and subscribe."""
        return await self._api_client.send_message(
            "getEventSummary",
            {
                "deviceId": device_id,
                "eventId": event_id,
                "accessToken": access_token,
                "subscribe": subscribe,
            },
        )

    async def on_device_event_update(self, data: dict) -> None:
        """Handle deviceEventUpdate messages."""
        await self.send_get_event_message(data["deviceId"], data["eventId"])
        if "body" in data and "accessToken" in data["body"]:
            await self.send_get_event_summary(
                data["deviceId"], data["eventId"], data["body"]["accessToken"]
            )

    async def on_event_update(self, data: dict) -> None:
        """Handle eventUpdate messages."""
        update = EventUpdate.from_api_response(data)
        if not update:
            return
        if self._current_events[update.device_id].frame_count is not None:
            await self.send_get_event_message(
                update.device_id, update.event_id, subscribe=False
            )
        else:
            await self.on_get_event(update.event)

    async def on_get_event(self, data: dict | Event) -> None:
        """Handle replies from getEvent messages."""
        event = Event.from_api_response(data) if isinstance(data, dict) else data
        if not event:
            return
        if event.device_id not in self._current_events:
            self._current_events[event.device_id] = event
        if self._current_events[event.device_id].event_id != event.event_id:
            self._current_events[event.device_id] = event
        else:
            self._current_events[event.device_id].update_from(event)
        for rfid_code in event.rfid_codes:
            pet = self.get_pet_by_rfid(rfid_code)
            if (
                pet
                and event.timestamp is not None
                and (pet.last_seen is None or pet.last_seen < event.timestamp)
            ):
                pet.last_seen = event.timestamp
                pet.last_seen_event = event
                await self.run_pet_listeners(pet.rfid_code)
        await self.run_event_listeners(event.device_id)

    async def on_get_event_summary(self, data: dict) -> None:
        """Handle replies from getEventSummary messages."""
        summary = EventSummary.from_api_response(data)
        if not summary:
            return
        if (
            summary.device_id not in self._current_summaries
            or self._current_summaries[summary.device_id].event_id != summary.event_id
        ):
            self._current_summaries[summary.device_id] = summary
        else:
            self._current_summaries[summary.device_id].update_from(summary)
        changed_pets = set()
        for subevent in summary.subevents:
            if subevent.rfid_code:
                pet = self.get_pet_by_rfid(subevent.rfid_code)
                pet.last_seen_summary = summary
                if (
                    pet.last_seen_event
                    and pet.last_seen_event.event_id == summary.event_id
                ):
                    pet.last_seen = pet.last_seen_event.timestamp
                    _LOGGER.debug(
                        "Updated pet %s last seen time to %s based on event",
                        pet.rfid_code,
                        pet.last_seen,
                    )
                pet.update_from_subevent(subevent)
                changed_pets.add(pet.rfid_code)
        for rfid_code in changed_pets:
            await self.run_pet_listeners(rfid_code)
        await self.run_summary_listeners(summary.device_id)

    async def on_event_summary_update(self, data: dict) -> None:
        """Handle eventSummaryUpdate messages."""
        if "body" not in data:
            _LOGGER.warning("Received event summary update with no body: %s", data)
            return
        await self.on_get_event_summary(data["body"])

    async def run_event_listeners(self, device_id: str) -> None:
        """Call all listeners for a given device."""
        if device_id not in self._event_update_listeners:
            return
        event = self._current_events.get(device_id, None)
        if event is not None:
            for callback in self._event_update_listeners[device_id]:
                await callback(event)

    async def run_summary_listeners(self, device_id: str) -> None:
        """Call all event summary listeners for a given device."""
        if device_id not in self._event_summary_update_listeners:
            return
        summary = self._current_summaries.get(device_id, None)
        if summary is not None:
            for callback in self._event_summary_update_listeners[device_id]:
                await callback(summary)

    async def run_pet_listeners(self, rfid_code: str) -> None:
        """Call all pet listeners for a given RFID code."""
        if rfid_code not in self._pet_update_listeners:
            return
        pet = self.get_pet_by_rfid(rfid_code)
        if pet is not None:
            for callback in self._pet_update_listeners[rfid_code]:
                await callback(pet)

    def add_event_listener(self, device_id: str, callback: Callable) -> None:
        """Add function to a devices listener list."""
        if device_id not in self._event_update_listeners:
            self._event_update_listeners[device_id] = []
        self._event_update_listeners[device_id].append(callback)

    def add_event_summary_listener(self, device_id: str, callback: Callable) -> None:
        """Add function to a devices event summary listener list."""
        if device_id not in self._event_summary_update_listeners:
            self._event_summary_update_listeners[device_id] = []
        self._event_summary_update_listeners[device_id].append(callback)

    def add_pet_listener(self, rfid_code: str, callback: Callable) -> None:
        """Add function to a pets listener list."""
        if rfid_code not in self._pet_update_listeners:
            self._pet_update_listeners[rfid_code] = []
        self._pet_update_listeners[rfid_code].append(callback)

    def get_current_image(self, device_id: str) -> bytes | None:
        """Return cached image for given device."""
        return self._current_images.get(device_id, None)

    def set_current_image(self, device_id: str, image: bytes) -> None:
        """Cache image for given device."""
        self._current_images[device_id] = image

    def get_pet_by_rfid(self, rfid_code: str) -> Pet:
        """Return pet with given RFID code, or None if not found."""
        pet = self._pets.get(rfid_code, None)
        if pet is None:
            self.add_pet(
                Pet(rfid_code=rfid_code, location=STATE_UNKNOWN, last_seen=None)
            )
            pet = self._pets[rfid_code]
        return pet

    def add_pet(self, pet: Pet) -> None:
        """Add pet to store."""
        self._pets[pet.rfid_code] = pet

    def get_pets(self) -> list[Pet]:
        """Return list of all pets in store."""
        return list(self._pets.values())
