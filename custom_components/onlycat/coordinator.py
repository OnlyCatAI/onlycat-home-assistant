"""Coordinator for OnlyCat integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data.__init__ import OnlyCatConfigEntry
    from .data.device import Device
import logging
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class OnlyCatDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching polling OnlyCat sensor data."""

    def __init__(self, hass: HomeAssistant, config_entry: OnlyCatConfigEntry) -> None:
        """Initialize global OnlyCat data updater."""
        interval = timedelta(
            hours=config_entry.data["settings"].get("poll_interval_hours", 1)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=interval,
        )

    async def fetch_device_transit_policies(self, device: Device) -> None:
        """Fetch transit policies for a device and update the device object."""
        if not self.config_entry.runtime_data.client:
            return
        transit_policies = await self.config_entry.runtime_data.client.send_message(
            "getDeviceTransitPolicies", {"deviceId": device.device_id}
        )
        if transit_policies is None:
            return
        for policy in transit_policies:
            await self.config_entry.runtime_data.client.send_message(
                "getDeviceTransitPolicy",
                {"deviceTransitPolicyId": policy["deviceTransitPolicyId"]},
            )

    async def _async_update_data(self) -> dict:
        """Fetch data."""
        _LOGGER.debug("Updating OnlyCat coordinator data")
        data = {}
        for device in self.config_entry.runtime_data.devices:
            await self.fetch_device_transit_policies(device)
            data[device.device_id] = {}
            try:
                data[device.device_id][
                    "errors"
                ] = await self.config_entry.runtime_data.client.send_message(
                    "getDeviceErrorLogs",
                    {
                        "deviceId": device.device_id,
                        "limit": 100,
                        "hours": self.config_entry.data["settings"].get(
                            "poll_interval_hours", 1
                        ),
                        "measureName": "message",
                    },
                )
            except TimeoutError:
                _LOGGER.exception("Error fetching OnlyCat errors: %s")
            if self.config_entry.data["settings"].get("enable_detailed_metrics", False):
                try:
                    data[device.device_id][
                        "metrics"
                    ] = await self.config_entry.runtime_data.client.send_message(
                        "getDeviceTelemetryMetrics",
                        {
                            "deviceId": device.device_id,
                        },
                    )
                except TimeoutError:
                    _LOGGER.exception("Error fetching OnlyCat metrics: %s")
        return data
