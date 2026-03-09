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
        _LOGGER.debug("Resolving media: %s", item.identifier)
        mime_type = "video/mp4" if "/sharing/" in item.identifier else "image/jpeg"
        return PlayMedia(item.identifier, mime_type)

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Browse media."""
        _LOGGER.debug("Browsing media: identifier=%s", item.identifier)
        try:
            if item.identifier in [None, "", "root"]:
                # Root level: list devices
                return self._browse_root()

            identifier = item.identifier
            if "/" in identifier and not identifier.startswith("https://"):
                parts = identifier.split("/")
                device_id = parts[0]
                media_type = parts[1]
                if media_type == "photos":
                    return self._browse_media_type(device_id, "photos")
                if media_type == "videos":
                    return self._browse_media_type(device_id, "videos")

            # Device level: list Photos/Videos folders
            return self._browse_device(identifier)
        except Exception:
            _LOGGER.exception("Error browsing OnlyCat media")
            raise

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
                        media_content_type=MediaType.ALBUM,
                        title=device.description or device.device_id,
                    )
                    for device in entry.runtime_data.devices
                ]
            )

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier="root",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.ALBUM,
            title="OnlyCat",
            children=children,
            children_media_class=MediaClass.DIRECTORY,
        )

    @callback
    def _browse_device(self, device_id: str) -> BrowseMediaSource:
        """Browse device level (Folders)."""
        device_name = device_id
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if hasattr(entry, "runtime_data"):
                # Try to get a nicer name
                for dev in entry.runtime_data.devices:
                    if dev.device_id == device_id:
                        device_name = dev.description or device_id
                        break

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=device_id,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.ALBUM,
            title=device_name,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{device_id}/photos",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.ALBUM,
                    title="Fotos",
                ),
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{device_id}/videos",
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.ALBUM,
                    title="Videos",
                ),
            ],
            children_media_class=MediaClass.DIRECTORY,
        )

    @callback
    def _browse_media_type(self, device_id: str, media_type: str) -> BrowseMediaSource:
        """Browse specific media type (Photos or Videos)."""
        children = []
        image_entity = None
        device_name = device_id
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if hasattr(entry, "runtime_data"):
                image_entity = entry.runtime_data.image_entities.get(device_id)
                if image_entity:
                    device_name = image_entity.device.description or device_id
                    break

        title = "Fotos" if media_type == "photos" else "Videos"
        media_class = MediaClass.IMAGE if media_type == "photos" else MediaClass.VIDEO

        if image_entity and hasattr(image_entity, "history"):
            for i, event in enumerate(image_entity.history):
                timestamp_str = (
                    event.timestamp.strftime("%d.%m %H:%M:%S")
                    if event.timestamp
                    else "Unbekannt"
                )
                label_prefix = "Neuestes" if i == 0 else f"Ereignis {i}"

                if media_type == "photos":
                    url = image_entity.get_url_for_event(event)
                    children.append(
                        BrowseMediaSource(
                            domain=DOMAIN,
                            identifier=url,
                            media_class=MediaClass.IMAGE,
                            media_content_type=MediaType.IMAGE,
                            title=f"{label_prefix} ({timestamp_str})",
                            thumbnail=url,
                            can_browse=False,
                            can_play=True,
                        )
                    )
                else:
                    vid_url = image_entity.get_video_url_for_event(event)
                    if vid_url:
                        img_url = image_entity.get_url_for_event(
                            event
                        )  # Use photo as thumbnail
                        children.append(
                            BrowseMediaSource(
                                domain=DOMAIN,
                                identifier=vid_url,
                                media_class=MediaClass.VIDEO,
                                media_content_type=MediaType.VIDEO,
                                title=f"{label_prefix} ({timestamp_str})",
                                thumbnail=img_url,
                                can_browse=False,
                                can_play=True,
                            )
                        )

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=f"{device_id}/{media_type}",
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.ALBUM,
            title=f"{device_name} - {title}",
            children=children,
            children_media_class=media_class,
        )
