"""Image platform for OnlyCat."""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import TYPE_CHECKING

from homeassistant.components.image import ImageEntity, ImageEntityDescription
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data.event import Event

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .data.__init__ import OnlyCatConfigEntry
    from .data.device import Device
    from .data.event_store import EventStore

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
            hass=hass, device=device, event_store=entry.runtime_data.event_store
        )
        for device in entry.runtime_data.devices
    ]
    async_add_entities(entities)


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
        self, hass: HomeAssistant, device: Device, event_store: EventStore
    ) -> None:
        """Initialize the sensor class."""
        ImageEntity.__init__(self, hass)
        self.entity_description = ENTITY_DESCRIPTION
        self.device: Device = device
        self._current_event: Event = Event()
        self._attr_unique_id = (
            device.device_id.replace("-", "_").lower() + "_last_activity_image"
        )
        self._event_store = event_store
        self.entity_id = "image." + self._attr_unique_id
        self._attr_image_url: str = ""
        self._cached_image: bytes | None = None
        self._event_store.add_event_listener(
            self.device.device_id, self.on_event_update
        )

    async def async_image(self) -> bytes | None:
        """Return the cached image from eventstore."""
        image = self._event_store.get_current_image(self.device.device_id)
        if image is None and self._current_event is not None:
            frame_to_show = (
                self._current_event.poster_frame_index
                if self._current_event.poster_frame_index is not None
                else self._current_event.frame_count // 2
                if self._current_event.frame_count is not None
                else 1
            )
            url = (
                f"{IMAGE_BASEURL}"
                f"{self._current_event.device_id}/"
                f"{self._current_event.event_id}/"
                f"{frame_to_show}"
            )
            session = async_get_clientsession(self.hass)
            async with session.get(url) as resp:
                if resp.status == HTTPStatus.OK:
                    image = await resp.read()
                    self._event_store.set_current_image(self.device.device_id, image)
        return image

    async def on_event_update(self, event: Event) -> None:
        """Handle event update."""
        if (
            self._current_event
            and self._current_event.event_id is not None
            and event.event_id is not None
            and event.event_id < self._current_event.event_id
        ):
            return
        self._current_event = event
        self.image_last_updated = self._current_event.timestamp
        self.async_write_ha_state()
