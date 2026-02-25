"""Camera platform for OnlyCat."""
from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.camera import (
    Camera,
    CameraEntityDescription,
    CameraEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data.event import Event, EventUpdate

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .api import OnlyCatApiClient
    from .data.__init__ import OnlyCatConfigEntry
    from .data.device import Device
    from .image import OnlyCatLastImage

ENTITY_DESCRIPTION = CameraEntityDescription(
    key="OnlyCat",
    name="Last activity video",
    translation_key="onlycat_last_activity_video",
)

IMAGE_BASEURL = "https://gateway.onlycat.com/events/"
MAX_HISTORY_SIZE = 11  # Same as image.py


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OnlyCatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the camera platform."""
    entities: list[OnlyCatLastVideo] = [
        OnlyCatLastVideo(
            hass=hass,
            device=device,
            api_client=entry.runtime_data.client,
        )
        for device in entry.runtime_data.devices
    ]

    async_add_entities(entities)

    for entity in entities:
        entry.runtime_data.camera_entities[entity.device.device_id] = entity

    # Try to initialize history from API if possible
    events_response = await entry.runtime_data.client.send_message(
        "getEvents", {"subscribe": True}
    )
    if isinstance(events_response, list) and len(events_response) > 0:
        events_response.sort(
            key=lambda e: dt.datetime.fromisoformat(e.get("timestamp")), reverse=True
        )
        for entity in entities:
            device_events = [
                Event.from_api_response(e)
                for e in events_response
                if e.get("deviceId") == entity.device.device_id
            ]
            device_events = [e for e in device_events if e is not None]
            if device_events:
                entity.async_initialize_history(device_events)


class OnlyCatLastVideo(Camera):
    """OnlyCat camera class for video history."""

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM

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
        """Initialize the camera entity."""
        Camera.__init__(self)
        self.hass = hass
        self.entity_description = ENTITY_DESCRIPTION
        self.device: Device = device
        self._history: list[Event] = []
        self._selected_index: int = 0
        self._attr_unique_id = (
            device.device_id.replace("-", "_").lower() + "_last_activity_video"
        )
        self._api_client = api_client
        self.entity_id = "camera." + self._attr_unique_id

        api_client.add_event_listener("eventUpdate", self.on_event_update)
        api_client.add_event_listener("deviceEventUpdate", self.on_event_update)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self._history:
            return {}
        return {
            "selected_index": self._selected_index,
        }

    async def async_camera_image(
        self, _width: int | None = None, _height: int | None = None
    ) -> bytes | None:
        """Return a still image response from the camera."""
        # Use the photo from the same event as the thumbnail
        if not self._history:
            return None

        idx = self._selected_index
        if idx >= len(self._history):
            idx = 0

        image_entities = self.device.config_entry.runtime_data.image_entities
        image_entity: OnlyCatLastImage = image_entities.get(self.device.device_id)

        if image_entity:
            return await image_entity.async_image()

        return None

    async def stream_source(self) -> str | None:
        """Return the source of the stream."""
        if not self._history:
            return None

        idx = self._selected_index
        if idx >= len(self._history):
            idx = 0

        event = self._history[idx]
        if not event or not event.access_token or not event.device_id or not event.event_id:
            return None

        # Return the raw video stream URL instead of the HTML sharing page
        return (
            f"https://gateway.onlycat.com/sharing/video/{event.device_id}/"
            f"{event.event_id}?t={event.access_token}"
        )

    @callback
    def async_initialize_history(self, events: list[Event]) -> None:
        """Initialize history with fetched events."""
        self._history = events[:MAX_HISTORY_SIZE]
        self.async_write_ha_state()

    async def async_set_history_index(self, index: int) -> None:
        """Set the history index to display."""
        self._selected_index = index
        self.async_write_ha_state()

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

        self.async_write_ha_state()
