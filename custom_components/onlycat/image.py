"""Image platform for OnlyCat."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OnlyCatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the image platform."""
    entities = [
        OnlyCatLastImage(
            hass=hass,
            device=device,
            api_client=entry.runtime_data.client,
        )
        for device in entry.runtime_data.devices
    ]
    async_add_entities(entities)
    events = await entry.runtime_data.client.send_message(
        "getEvents", {"subscribe": True}
    )
    if events is None or len(events) == 0:
        return
    events.sort(key=lambda e: datetime.fromisoformat(e.get("timestamp")), reverse=True)
    for entity in entities:
        for event in events:
            if event.get("deviceId") == entity.device.device_id:
                await entity.update_event(Event.from_api_response(event))
                break


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
        self._current_event: Event = Event()
        self._attr_unique_id = (
            device.device_id.replace("-", "_").lower() + "_last_activity_image"
        )
        self._api_client = api_client
        self.entity_id = "image." + self._attr_unique_id
        self._attr_image_url: str = ""
        api_client.add_event_listener("eventUpdate", self.on_event_update)
        api_client.add_event_listener("deviceEventUpdate", self.on_event_update)

    async def on_event_update(self, data: dict) -> None:
        """Handle event update event."""
        if data["deviceId"] != self.device.device_id:
            return
        event_update = EventUpdate.from_api_response(data)
        _LOGGER.debug(
            "Processing event update for image:  %s: %s",
            self.device.device_id,
            str(data),
        )
        if event_update.event_id != self._current_event.event_id:
            self._current_event = event_update.event
            self._current_event.device_id = event_update.device_id
            self._current_event.event_id = event_update.event_id
        self._current_event.update_from(event_update.event)
        self._cached_image = None
        self._current_event.timestamp += timedelta(seconds=1)
        frame_to_show = (
            self._current_event.poster_frame_index
            if self._current_event.poster_frame_index is not None
            else self._current_event.frame_count / 2
            if self._current_event.frame_count is not None
            else 1
        )
        self._attr_image_url = (
            IMAGE_BASEURL
            + self._current_event.device_id
            + "/"
            + str(self._current_event.event_id)
            + "/"
            + str(frame_to_show)
        )
        self._attr_image_last_updated = self._current_event.timestamp
        _LOGGER.debug(
            "Updated image URL %s: %s",
            self._current_event.timestamp,
            self._attr_image_url,
        )
        self.async_write_ha_state()

    async def update_event(self, event: Event) -> None:
        """Update with event data."""
        _LOGGER.debug(
            "Updating event for device %s: %s", self.device.device_id, str(event)
        )
        self._current_event = event
        self._cached_image = None
        frame_to_show = (
            self._current_event.poster_frame_index
            if self._current_event.poster_frame_index is not None
            else self._current_event.frame_count / 2
            if self._current_event.frame_count is not None
            else 1
        )
        self._attr_image_url = (
            IMAGE_BASEURL
            + self._current_event.device_id
            + "/"
            + str(self._current_event.event_id)
            + "/"
            + str(frame_to_show)
        )
        self._attr_image_last_updated = self._current_event.timestamp
        _LOGGER.debug(
            "Updated image URL for device %s: %s",
            self._current_event.timestamp,
            self._attr_image_url,
        )
        self.async_write_ha_state()
