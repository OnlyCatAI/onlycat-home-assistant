"""Sensor platform for OnlyCat."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .binary_sensor_connectivity import OnlyCatConnectionSensor
from .binary_sensor_contraband import OnlyCatContrabandSensor
from .binary_sensor_device_errors import OnlyCatErrorSensor
from .binary_sensor_event import OnlyCatEventSensor
from .binary_sensor_human import OnlyCatHumanSensor
from .binary_sensor_lock import OnlyCatLockSensor

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .data.__init__ import OnlyCatConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: OnlyCatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    async_add_entities(
        sensor
        for device in entry.runtime_data.devices
        for sensor in (
            OnlyCatEventSensor(
                device=device,
                api_client=entry.runtime_data.client,
            ),
            OnlyCatContrabandSensor(
                device=device,
                api_client=entry.runtime_data.client,
            ),
            OnlyCatLockSensor(
                device=device,
                api_client=entry.runtime_data.client,
            ),
            OnlyCatHumanSensor(
                device=device,
                api_client=entry.runtime_data.client,
            ),
            OnlyCatConnectionSensor(
                device=device,
                api_client=entry.runtime_data.client,
            ),
            OnlyCatErrorSensor(
                device=device,
                api_client=entry.runtime_data.client,
                coordinator=entry.runtime_data.coordinator,
            ),
        )
    )
    entry.runtime_data.coordinator.async_update_listeners()
