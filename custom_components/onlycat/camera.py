"""Camera platform for OnlyCat."""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging
from typing import TYPE_CHECKING

from homeassistant.components.camera import (
    Camera,
    CameraEntityDescription,
    CameraEntityFeature,
    StreamType,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data.event import Event, EventUpdate
from homeassistant.helpers.aiohttp_client import async_get_clientsession

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .api import OnlyCatApiClient
    from .data.__init__ import OnlyCatConfigEntry
    from .data.device import Device

_LOGGER = logging.getLogger(__name__)

VIDEO_BASEURL = "https://gateway.onlycat.com/sharing/video/"
THUMB_BASEURL = "https://gateway.onlycat.com/events/"

ENTITY_DESCRIPTION = CameraEntityDescription(
    key="OnlyCat",
    name="Last activity video",
    translation_key="onlycat_last_activity_video",
)


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

    _LOGGER.debug("Initializing camera entities with last events")
    for entity in entities:
        try:
            events_response = await entry.runtime_data.client.send_message(
                event="getDeviceEvents",
                data={"deviceId": entity.device.device_id},
            )
            if isinstance(events_response, list) and len(events_response) > 0:
                # Sort events by timestamp descending to get the latest one
                events_response.sort(
                    key=lambda e: dt.datetime.fromisoformat(e.get("timestamp")),
                    reverse=True,
                )
                entity.update_event(Event.from_api_response(events_response[0]))
        except Exception:
            _LOGGER.exception(
                "Error initializing camera for device %s", entity.device.device_id
            )


class OnlyCatLastVideo(Camera):
    """OnlyCat camera class for last activity video."""

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM
    # Force HLS stream type to prevent playback issues
    _attr_frontend_stream_type = StreamType.HLS

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
        self._current_event: Event | None = None
        self._attr_unique_id = (
            device.device_id.replace("-", "_").lower() + "_last_activity_video"
        )
        self._api_client = api_client
        self.entity_id = "camera." + self._attr_unique_id
        self._cached_image: bytes | None = None

        # Listen for real-time event updates
        api_client.add_event_listener("eventUpdate", self.on_event_update)
        api_client.add_event_listener("deviceEventUpdate", self.on_event_update)

    async def async_camera_image(
        self,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes | None:
        """Return a thumbnail image for the camera preview."""
        if not self._current_event:
            return None

        frame_to_show = (
            self._current_event.poster_frame_index
            if self._current_event.poster_frame_index is not None
            else self._current_event.frame_count // 2
            if self._current_event.frame_count is not None
            else 1
        )

        url = (
            f"https://gateway.onlycat.com/events/"
            f"{self._current_event.device_id}/"
            f"{self._current_event.event_id}/"
            f"{frame_to_show}"
        )

        session = async_get_clientsession(self.hass)

        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.read()

        return None

    async def stream_source(self) -> str | None:
        """Return the source URL of the video stream."""
        if not self._current_event or not self._current_event.access_token:
            return None

        event = self._current_event
        # Construct the URL with the mandatory access token
        return (
            f"{VIDEO_BASEURL}{event.device_id}/{event.event_id}?t={event.access_token}"
        )

    @callback
    def _reset_stream(self) -> None:
        """Stop and reset the current stream buffer."""
        if hasattr(self, "stream") and self.stream:
            with contextlib.suppress(Exception):
                self.stream.stop()
            self.stream = None

    @callback
    def update_event(self, event: Event | None) -> None:
        """Update the entity with new event data."""
        if event is None:
            return

        # Ignore events that are older than the currently displayed one
        if (
            self._current_event
            and self._current_event.event_id is not None
            and event.event_id is not None
            and event.event_id < self._current_event.event_id
        ):
            return

        # If it's a new event ID, clear the old stream
        if self._current_event and self._current_event.event_id != event.event_id:
            self._reset_stream()

        self._current_event = event
        self.async_write_ha_state()

    async def on_event_update(self, data: dict) -> None:
        """Handle incoming event updates via WebSockets."""
        if data.get("deviceId") != self.device.device_id:
            return

        event_update = EventUpdate.from_api_response(data)
        if not event_update or not event_update.event:
            return

        # Ignore older events
        if (
            self._current_event
            and self._current_event.event_id is not None
            and event_update.event_id is not None
            and event_update.event_id < self._current_event.event_id
        ):
            return

        # Check if this is a partial update for the current event
        if (
            self._current_event
            and self._current_event.event_id == event_update.event_id
        ):
            # Partial update to existing event
            self._current_event.update_from(event_update.event)
            self.async_write_ha_state()
        else:
            # Completely new event detected
            self._reset_stream()

            self._current_event = event_update.event
            self._current_event.device_id = event_update.device_id
            self._current_event.event_id = event_update.event_id

            # If the token is missing, wait and fetch full details
            if not self._current_event.access_token:
                try:
                    await asyncio.sleep(1.0)
                    events_response = await self._api_client.send_message(
                        event="getDeviceEvents",
                        data={"deviceId": self.device.device_id},
                    )
                    if isinstance(events_response, list) and len(events_response) > 0:
                        events_response.sort(
                            key=lambda e: dt.datetime.fromisoformat(e.get("timestamp")),
                            reverse=True,
                        )
                        latest_event = Event.from_api_response(events_response[0])
                        if (
                            latest_event
                            and latest_event.event_id == self._current_event.event_id
                        ):
                            self._current_event.update_from(latest_event)
                except Exception:
                    _LOGGER.exception("Failed to fetch full new event details")

            self.async_write_ha_state()
