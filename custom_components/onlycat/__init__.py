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
from .data.device import Device, DeviceUpdate
from .data.event import Event
from .data.pet import Pet
from .data.policy import DeviceTransitPolicy
from .services import async_setup_services

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.DEVICE_TRACKER,
    Platform.BUTTON,
    Platform.IMAGE,
]
_LOGGER = logging.getLogger(__name__)


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(
    hass: HomeAssistant,
    entry: OnlyCatConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    default_settings = {
        "ignore_flap_motion_rules": False,
        "ignore_motion_sensor_rules": False,
        "poll_interval_hours": 6,
    }
    entry.runtime_data = OnlyCatData(
        client=OnlyCatApiClient(
            token=entry.data["token"], session=async_get_clientsession(hass)
        ),
        devices=[],
        pets=[],
        settings=entry.data.get("settings", default_settings),
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

    async def update_device(data: dict) -> None:
        """Update a device in our runtime data when it is changed."""
        update = DeviceUpdate.from_api_response(data)

        for device in entry.runtime_data.devices:
            if device.device_id == update.device_id:
                updated_device = Device.from_api_response(
                    await entry.runtime_data.client.send_message(
                        "getDevice", {"deviceId": update.device_id, "subscribe": True}
                    )
                )
                device.update_from(updated_device)
                if device.device_transit_policy_id is not None:
                    await _retrieve_current_transit_policy(entry, device)
                _LOGGER.debug("Updated device: %s", device)
                break
        else:
            _LOGGER.warning(
                "Device with ID %s not found in runtime data", update.device_id
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
    entry.runtime_data.client.add_event_listener("deviceUpdate", update_device)
    entry.runtime_data.client.add_event_listener(
        "deviceEventUpdate", subscribe_to_device_event
    )

    await async_setup_services(hass)
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
            )
        )
        entry.runtime_data.devices.append(device)

    for device in entry.runtime_data.devices:
        device.settings = entry.runtime_data.settings
        if device.device_transit_policy_id is not None:
            await _retrieve_current_transit_policy(entry, device)


async def _retrieve_current_transit_policy(
    entry: OnlyCatConfigEntry, device: Device
) -> None:
    if device.device_transit_policy_id is None:
        return
    transit_policy = DeviceTransitPolicy.from_api_response(
        await entry.runtime_data.client.send_message(
            "getDeviceTransitPolicy",
            {"deviceTransitPolicyId": device.device_transit_policy_id},
        )
    )
    transit_policy.device = device
    device.device_transit_policy = transit_policy


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
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: OnlyCatConfigEntry,
) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
