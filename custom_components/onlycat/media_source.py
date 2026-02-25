"""Media Source platform for OnlyCat."""
from __future__ import annotations

import logging

from homeassistant.components.media_player.const import MediaClass, MediaType
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_get_media_source(hass: HomeAssistant) -> OnlyCatMediaSource:
    """Set up OnlyCat media source."""
    return OnlyCatMediaSource(hass)


class OnlyCatMediaSource(MediaSource):
    """Media source for OnlyCat."""

    name = "OnlyCat"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize OnlyCat media source."""
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve media to a URL."""
        # The item.identifier is the URL itself or we reconstruct it
        return PlayMedia(item.identifier, "image/jpeg")

    async def async_browse_media(
        self, item: MediaSourceItem
    ) -> BrowseMediaSource:
        """Browse media."""
        if item.identifier in [None, ""]:
            # Root level: list devices
            return self._browse_root()

        # Device level: list 10 images
        return self._browse_device(item.identifier)

    @callback
    def _browse_root(self) -> BrowseMediaSource:
        """Browse root level."""
        children = []
        # Get devices from config entries
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if not hasattr(entry, "runtime_data"):
                continue
            children.extend(
                [
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=device.device_id,
                        media_class=MediaClass.DIRECTORY,
                        media_content_type=MediaType.CHANNELS,
                        title=device.description or device.device_id,
                        can_browse=True,
                        can_play=False,
                    )
                    for device in entry.runtime_data.devices
                ]
            )

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier="",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.CHANNELS,
            title="OnlyCat",
            can_browse=True,
            can_play=False,
            children=children,
        )

    @callback
    def _browse_device(self, device_id: str) -> BrowseMediaSource:
        """Browse device level."""
        children = []
        # Find the image entity for this device
        image_entity = None
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if hasattr(entry, "runtime_data"):
                image_entity = entry.runtime_data.image_entities.get(device_id)
                if image_entity:
                    break
        if image_entity and hasattr(image_entity, "history"):
            for i, event in enumerate(image_entity.history):
                # We use the public get_url_for_event
                url = image_entity.get_url_for_event(event)
                if event.timestamp:
                    timestamp_str = event.timestamp.strftime("%d.%m %H:%M:%S")
                else:
                    timestamp_str = "Unbekannte Zeit"

                if i > 0:
                    title = f"Ereignis {i} - {timestamp_str}"
                else:
                    title = f"Neuestes Ereignis - {timestamp_str}"

                children.append(
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=url,
                        media_class=MediaClass.IMAGE,
                        media_content_type=MediaType.IMAGE,
                        title=title,
                        can_browse=False,
                        can_play=True,
                        thumbnail=url,
                    )
                )

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=device_id,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.IMAGE,
            title="Letzte Ereignisse",
            can_browse=True,
            can_play=False,
            children=children,
        )
