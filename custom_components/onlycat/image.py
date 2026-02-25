"""Image platform for OnlyCat."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.image import ImageEntity, ImageEntityDescription
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data.event import Event, EventUpdate

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .api import OnlyCatApiClient
    from .data.__init__ import OnlyCatConfigEntry
    from .data.device import Device

ENTITY_DESCRIPTION = ImageEntityDescription(
    key="OnlyCat",
    name="Last activity image",
    translation_key="onlycat_last_activity_image",
)

IMAGE_BASEURL = "https://gateway.onlycat.com/events/"
HISTORY_SIZE = 10
MAX_HISTORY_SIZE = HISTORY_SIZE + 1  # Latest + history


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OnlyCatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the image platform."""
    entities: list[OnlyCatLastImage] = [
        OnlyCatLastImage(
            hass=hass,
            device=device,
            api_client=entry.runtime_data.client,
        )
        for device in entry.runtime_data.devices
    ]

    async_add_entities(entities)

    for entity in entities:
        entry.runtime_data.image_entities[entity.device.device_id] = entity

    events = await entry.runtime_data.client.send_message(
        "getEvents", {"subscribe": True}
    )
    if events is None or len(events) == 0:
        return

    events.sort(key=lambda e: datetime.fromisoformat(e.get("timestamp")), reverse=True)

    for entity in entities:
        device_events = [
            Event.from_api_response(e)
            for e in events
            if e.get("deviceId") == entity.device.device_id
        ]
        device_events = [e for e in device_events if e is not None]
        if device_events:
            await entity.async_initialize_history(device_events)


class OnlyCatLastImage(ImageEntity):
    """OnlyCat image class."""

    _attr_has_entity_name = True
    _attr_content_type = "image/jpeg"

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
        hass: HomeAssistant,
        device: Device,
        api_client: OnlyCatApiClient,
    ) -> None:
        """Initialize the sensor class."""
        ImageEntity.__init__(self, hass)
        self.entity_description = ENTITY_DESCRIPTION
        self.device: Device = device
        self._history: list[Event] = []
        self._selected_index: int = 0  # 0 = Latest, 1-10 = History
        self._attr_unique_id = (
            device.device_id.replace("-", "_").lower() + "_last_activity_image"
        )
        self._api_client = api_client
        self.entity_id = "image." + self._attr_unique_id
        self._attr_image_url: str = ""
        api_client.add_event_listener("eventUpdate", self.on_event_update)
        api_client.add_event_listener("deviceEventUpdate", self.on_event_update)

    @property
    def history(self) -> list[Event]:
        """Return the image history."""
        return self._history

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._history:
            return {}
        return {
            "image_history": [self.get_url_for_event(ev) for ev in self._history],
            "selected_index": self._selected_index,
        }

    def get_url_for_event(self, event: Event) -> str:
        """Get the URL for a specific event."""
        if not event or not event.event_id:
            return ""

        frame_to_show = (
            event.poster_frame_index
            if event.poster_frame_index is not None
            else event.frame_count / 2
            if event.frame_count is not None
            else 1
        )
        device_id = event.device_id or self.device.device_id
        return f"{IMAGE_BASEURL}{device_id}/{event.event_id}/{int(frame_to_show)}"

    def get_video_url_for_event(self, event: Event) -> str:
        """Get the video URL for a specific event."""
        if (
            not event
            or not event.access_token
            or not event.device_id
            or not event.event_id
        ):
            return ""
        return (
            f"https://gateway.onlycat.com/sharing/video/{event.device_id}/"
            f"{event.event_id}?t={event.access_token}"
        )

    async def async_initialize_history(self, events: list[Event]) -> None:
        """Initialize history with fetched events."""
        self._history = events[:MAX_HISTORY_SIZE]
        self._update_image_from_history()

    async def async_set_history_index(self, index: int) -> None:
        """Set the history index to display."""
        self._selected_index = index
        self._update_image_from_history()
        self.async_write_ha_state()

    def _update_image_from_history(self) -> None:
        """Update the displayed image based on history and selection."""
        if not self._history:
            return

        idx = self._selected_index
        if idx >= len(self._history):
            idx = 0

        event = self._history[idx]
        self._attr_image_url = self.get_url_for_event(event)
        self._attr_image_last_updated = event.timestamp
        self._cached_image = None

    async def on_event_update(self, data: dict) -> None:
        """Handle event update event."""
        if data["deviceId"] != self.device.device_id:
            return

        event_update = EventUpdate.from_api_response(data)
        if not event_update or not event_update.event:
            return

        new_event = event_update.event
        if not new_event.device_id:
            new_event.device_id = self.device.device_id

        # Update existing or add new
        existing_idx = next(
            (
                i
                for i, ev in enumerate(self._history)
                if ev.event_id == new_event.event_id
            ),
            None,
        )

        if existing_idx is not None:
            self._history[existing_idx].update_from(new_event)
        else:
            self._history.insert(0, new_event)
            if len(self._history) > MAX_HISTORY_SIZE:
                self._history.pop()

        self._update_image_from_history()
        self.async_write_ha_state()

    async def update_event(self, event: Event) -> None:
        """Legacy update method for compatibility during setup."""
        if not self._history or self._history[0].event_id != event.event_id:
            self._history.insert(0, event)
            if len(self._history) > MAX_HISTORY_SIZE:
                self._history.pop()
        else:
            self._history[0].update_from(event)

        self._update_image_from_history()
        self.async_write_ha_state()


HISTORY_SIZE = 10
