"""
Custom integration to integrate OnlyCat with Home Assistant.

For more details about this integration, please refer to
https://github.com/OnlyCatAI/onlycat-home-assistant
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OnlyCatApiClient
from .coordinator import OnlyCatDataUpdateCoordinator
from .data.__init__ import OnlyCatConfigEntry, OnlyCatData
from .data.device import Device
from .data.event import Event
from .data.pet import Pet
from .services import async_setup_services

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.DEVICE_TRACKER,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.SENSOR,
]
_LOGGER = logging.getLogger(__name__)


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(
    hass: HomeAssistant,
    entry: OnlyCatConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    entry.runtime_data = OnlyCatData(
        client=OnlyCatApiClient(
            token=entry.data["token"], session=async_get_clientsession(hass)
        ),
        devices=[],
        pets=[],
        settings=entry.data["settings"],
        coordinator=OnlyCatDataUpdateCoordinator(hass=hass, config_entry=entry),
    )
    await entry.runtime_data.client.connect()

    await _initialize_devices(entry)
    await _initialize_pets(entry)
    await entry.runtime_data.coordinator.async_config_entry_first_refresh()

    async def refresh_subscriptions(args: dict | None) -> None:
        _LOGGER.debug("Refreshing subscriptions, caused by event: %s", args)
        for device in entry.runtime_data.devices:
            await entry.runtime_data.client.send_message(
                "getDevice", {"deviceId": device.device_id, "subscribe": True}
            )
            await entry.runtime_data.client.send_message(
                "getDeviceEvents", {"deviceId": device.device_id, "subscribe": True}
            )

    async def subscribe_to_device_event(data: dict) -> None:
        """Subscribe to a device event to get updates about the event in the future."""
        await entry.runtime_data.client.send_message(
            "getEvent",
            {
                "deviceId": data["deviceId"],
                "eventId": data["eventId"],
                "subscribe": True,
            },
        )

    await refresh_subscriptions(None)
    entry.runtime_data.client.add_event_listener("connect", refresh_subscriptions)
    entry.runtime_data.client.add_event_listener("userUpdate", refresh_subscriptions)
    entry.runtime_data.client.add_event_listener(
        "deviceEventUpdate", subscribe_to_device_event
    )

    await async_setup_services(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def _initialize_devices(entry: OnlyCatConfigEntry) -> None:
    device_ids = (
        device["deviceId"]
        for device in await entry.runtime_data.client.send_message(
            "getDevices", {"subscribe": True}
        )
    )
    for device_id in device_ids:
        device = Device.from_api_response(
            await entry.runtime_data.client.send_message(
                "getDevice", {"deviceId": device_id, "subscribe": True}
            ),
            entry,
        )
        entry.runtime_data.devices.append(device)

    for device in entry.runtime_data.devices:
        device.settings = entry.runtime_data.settings
        entry.runtime_data.client.add_event_listener(
            "deviceUpdate", device.handle_device_update
        )
        entry.runtime_data.client.add_event_listener(
            "getDevice", device.update_device_from_api
        )
        entry.runtime_data.client.add_event_listener(
            "getDeviceTransitPolicy", device.update_device_transit_policy_from_api
        )
        if device.device_transit_policy_id is not None:
            await entry.runtime_data.client.send_message(
                "getDeviceTransitPolicy",
                {"deviceTransitPolicyId": device.device_transit_policy_id},
            )


async def _initialize_pets(entry: OnlyCatConfigEntry) -> None:
    for device in entry.runtime_data.devices:
        events = [
            Event.from_api_response(event)
            for event in await entry.runtime_data.client.send_message(
                "getDeviceEvents", {"deviceId": device.device_id}
            )
        ]
        rfids = await entry.runtime_data.client.send_message(
            "getLastSeenRfidCodesByDevice", {"deviceId": device.device_id}
        )
        for rfid in rfids:
            rfid_code = rfid["rfidCode"]
            try:
                last_seen = datetime.fromisoformat(rfid["timestamp"])
            except TypeError:
                last_seen = None
            rfid_profile = await entry.runtime_data.client.send_message(
                "getRfidProfile", {"rfidCode": rfid_code}
            )
            label = rfid_profile.get("label")
            pet = Pet(device, rfid_code, last_seen, label=label)
            _LOGGER.debug(
                "Found Pet %s for device %s",
                label or rfid_code,
                device.device_id,
            )
            entry.runtime_data.pets.append(pet)

            # Get last seen event to determine current presence state
            for event in events:
                if event.rfid_codes and pet.rfid_code in event.rfid_codes:
                    pet.last_seen_event = event
                    break


async def async_unload_entry(
    hass: HomeAssistant,
    entry: OnlyCatConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    await entry.runtime_data.client.disconnect()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: OnlyCatConfigEntry,
) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: OnlyCatConfigEntry
) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(
        "Migrating configuration from version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )
    if "settings" not in config_entry.data:
        new_data = {**config_entry.data}
        default_settings = {
            "ignore_flap_motion_rules": False,
            "ignore_motion_sensor_rules": False,
            "poll_interval_hours": 1,
        }
        new_data["settings"] = default_settings
    hass.config_entries.async_update_entry(
        config_entry, data=new_data, minor_version=1, version=2
    )
    return True
