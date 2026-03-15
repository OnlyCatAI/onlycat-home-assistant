"""Camera platform for OnlyCat."""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
from http import HTTPStatus
from typing import TYPE_CHECKING

from homeassistant.components.camera import (
    Camera,
    CameraEntityDescription,
    CameraEntityFeature,
    StreamType,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data.event import Event

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .data.__init__ import OnlyCatConfigEntry
    from .data.device import Device
    from .data.event_store import EventStore

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
    if not hasattr(entry.runtime_data, "camera_entities"):
        entry.runtime_data.camera_entities = {}

    entities: list[OnlyCatLastVideo] = [
        OnlyCatLastVideo(
            hass=hass, device=device, event_store=entry.runtime_data.event_store
        )
        for device in entry.runtime_data.devices
    ]

    async_add_entities(entities)

    _LOGGER.debug("Initializing camera entities with last events")
    for entity in entities:
        try:
            events_response = await entry.runtime_data.client.send_message(
                event="getDeviceEvents",
                data={"deviceId": entity.device.device_id},
            )
            if isinstance(events_response, list) and events_response:
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
        self, hass: HomeAssistant, device: Device, event_store: EventStore
    ) -> None:
        """Initialize the camera entity."""
        super().__init__()
        self.hass = hass
        self.device: Device = device
        self.entity_description = ENTITY_DESCRIPTION
        self._current_event: Event | None = None
        self._attr_unique_id = (
            device.device_id.replace("-", "_").lower() + "_last_activity_video"
        )
        self._event_store = event_store
        self.entity_id = "camera." + self._attr_unique_id
        self._cached_image: bytes | None = None

        self._event_store.add_event_listener(
            self.device.device_id, self.on_event_update
        )

    async def async_camera_image(
        self,
        width: int | None = None,  # noqa: ARG002
        height: int | None = None,  # noqa: ARG002
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
            f"{THUMB_BASEURL}"
            f"{self._current_event.device_id}/"
            f"{self._current_event.event_id}/"
            f"{frame_to_show}"
        )

        session = async_get_clientsession(self.hass)
        async with session.get(url) as resp:
            if resp.status == HTTPStatus.OK:
                return await resp.read()

        return None

    async def stream_source(self) -> str | None:
        """Return the source URL of the video stream."""
        if not self._current_event or not self._current_event.access_token:
            return None

        event = self._current_event
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
        if not event:
            return

        if (
            self._current_event
            and self._current_event.event_id is not None
            and event.event_id is not None
            and event.event_id < self._current_event.event_id
        ):
            return

        if self._current_event and self._current_event.event_id != event.event_id:
            self._reset_stream()

        self._current_event = event
        self.async_write_ha_state()

    async def on_event_update(self, event: Event) -> None:
        """Handle event update."""
        if (
            self._current_event
            and self._current_event.event_id is not None
            and event.event_id is not None
            and event.event_id < self._current_event.event_id
        ):
            return

        if self._current_event and self._current_event.event_id == event.event_id:
            self._current_event = event
            self.async_write_ha_state()
        else:
            self._reset_stream()
            self._current_event = event
            self.async_write_ha_state()
