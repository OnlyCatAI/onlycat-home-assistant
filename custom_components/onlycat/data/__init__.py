"""Custom types for onlycat."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from custom_components.onlycat.api import OnlyCatApiClient
    from custom_components.onlycat.coordinator import OnlyCatDataUpdateCoordinator

    from .device import Device
    from .pet import Pet

_LOGGER = logging.getLogger(__name__)


type OnlyCatConfigEntry = ConfigEntry[OnlyCatData]


@dataclass
class OnlyCatData:
    """Data for the OnlyCat integration."""

    client: OnlyCatApiClient
    devices: list[Device]
    pets: list[Pet]
    settings: dict[str, object]
    coordinator: OnlyCatDataUpdateCoordinator
