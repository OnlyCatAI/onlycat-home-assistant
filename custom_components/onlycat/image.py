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
    entities: list[ImageEntity] = [
        OnlyCatLastImage(
            hass=hass,
            device=device,
            api_client=entry.runtime_data.client,
        )
        for device in entry.runtime_data.devices
    ]

    history_managers = []
    for device in entry.runtime_data.devices:
        manager = OnlyCatImageHistoryManager(
            hass=hass, device=device, api_client=entry.runtime_data.client
        )
        history_managers.append(manager)
        entities.extend(manager.entities)

    async_add_entities(entities)

    events = await entry.runtime_data.client.send_message(
        "getEvents", {"subscribe": True}
    )
    if events is None or len(events) == 0:
        return

    events.sort(key=lambda e: datetime.fromisoformat(e.get("timestamp")), reverse=True)

    for device in entry.runtime_data.devices:
        device_events = [
            Event.from_api_response(e)
            for e in events
            if e.get("deviceId") == device.device_id
        ]
        # Remove any Nones
        device_events = [e for e in device_events if e is not None]

        if not device_events:
            continue

        for entity in entities:
            if (
                isinstance(entity, OnlyCatLastImage)
                and entity.device.device_id == device.device_id
            ):
                await entity.update_event(device_events[0])
                break

        for manager in history_managers:
            if manager.device.device_id == device.device_id:
                manager.populate_initial(device_events)
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


HISTORY_SIZE = 10

class OnlyCatImageHistoryManager:
    """Manages a history of the last 10 OnlyCat images."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: Device,
        api_client: OnlyCatApiClient,
    ) -> None:
        """Initialize the history manager."""
        self.hass = hass
        self.device = device
        self._api_client = api_client
        self.entities: list[OnlyCatHistoryImage] = [
            OnlyCatHistoryImage(hass, device, i + 1) for i in range(HISTORY_SIZE)
        ]
        self._events: list[Event] = []

        self._api_client.add_event_listener("eventUpdate", self.on_event_update)
        self._api_client.add_event_listener("deviceEventUpdate", self.on_event_update)

    async def on_event_update(self, data: dict) -> None:
        """Handle event update event by adding or parsing."""
        if data.get("deviceId") != self.device.device_id:
            return

        event_update = EventUpdate.from_api_response(data)
        if not event_update or not event_update.event:
            return

        self.update_with_event(event_update.event)

    def update_with_event(self, event: Event) -> None:
        """Add or update an event in the history."""
        existing_idx = -1
        for i, ev in enumerate(self._events):
            if ev.event_id == event.event_id:
                existing_idx = i
                break

        if existing_idx != -1:
            self._events[existing_idx].update_from(event)
            # Find the corresponding entity that has this event
            for entity in self.entities:
                if (
                    entity._current_event  # noqa: SLF001
                    and entity._current_event.event_id == event.event_id  # noqa: SLF001
                ):
                    self.hass.async_create_task(
                        entity.update_event(self._events[existing_idx])
                    )
            return

        # New event, insert at top
        self._events.insert(0, event)
        if len(self._events) > HISTORY_SIZE:
            self._events.pop()

        self._update_entities()

    def _update_entities(self) -> None:
        """Push the events to the entities based on index."""
        for i, entity in enumerate(self.entities):
            if i < len(self._events):
                self.hass.async_create_task(entity.update_event(self._events[i]))

    def populate_initial(self, events: list[Event]) -> None:
        """Populate initial history from fetch."""
        self._events = events[:HISTORY_SIZE]
        self._update_entities()


class OnlyCatHistoryImage(ImageEntity):
    """Image entity representing a historical event."""

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
        index: int,
    ) -> None:
        """Initialize the history image class."""
        ImageEntity.__init__(self, hass)
        self.device: Device = device
        self.index = index
        self._current_event: Event | None = None

        self.entity_description = ImageEntityDescription(
            key=f"OnlyCat_history_{index}",
            name=f"History Image {index}",
            translation_key="onlycat_history_image",
            translation_placeholders={"index": str(index)},
        )

        self._attr_unique_id = (
            f"{device.device_id.replace('-', '_').lower()}_history_image_{index}"
        )
        self.entity_id = "image." + self._attr_unique_id
        self._attr_image_url: str = ""

    async def update_event(self, event: Event) -> None:
        """Update with event data."""
        self._current_event = event
        self._attr_image_url = ""

        # We need device_id and event_id to build the URL
        if not self._current_event.device_id and self.device.device_id:
            self._current_event.device_id = self.device.device_id

        if getattr(self._current_event, "timestamp", None):
            self._attr_image_last_updated = self._current_event.timestamp

        frame_to_show = (
            self._current_event.poster_frame_index
            if self._current_event.poster_frame_index is not None
            else self._current_event.frame_count / 2
            if self._current_event.frame_count is not None
            else 1
        )

        if self._current_event.event_id is not None and self._current_event.device_id:
            self._attr_image_url = (
                f"{IMAGE_BASEURL}{self._current_event.device_id}/"
                f"{self._current_event.event_id}/{frame_to_show}"
            )

        _LOGGER.debug(
            "Updated history %s image URL for device %s: %s",
            self.index,
            self._current_event.timestamp if self._current_event else "None",
            self._attr_image_url,
        )
        self.async_write_ha_state()
