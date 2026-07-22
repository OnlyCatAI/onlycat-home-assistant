"""
Custom integration to integrate OnlyCat with Home Assistant.

For more details about this integration, please refer to
https://github.com/OnlyCatAI/onlycat-home-assistant
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OnlyCatApiClient, OnlyCatApiClientCommunicationError
from .coordinator import OnlyCatDataUpdateCoordinator
from .data.__init__ import OnlyCatConfigEntry, OnlyCatData
from .data.device import Device
from .data.event_store import EventStore
from .data.event_summary import SubEvent
from .services import async_setup_services

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.DEVICE_TRACKER,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.IMAGE,
    Platform.CAMERA,
]
_LOGGER = logging.getLogger(__name__)


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(
    hass: HomeAssistant,
    entry: OnlyCatConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    client = OnlyCatApiClient(
        token=entry.data["token"], session=async_get_clientsession(hass)
    )
    entry.runtime_data = OnlyCatData(
        client=client,
        devices=[],
        pets=[],
        event_store=EventStore(api_client=client),
        settings=entry.data["settings"],
        coordinator=OnlyCatDataUpdateCoordinator(hass=hass, config_entry=entry),
    )
    await entry.runtime_data.client.connect()

    await _initialize_devices(entry)
    await _initialize_pets(entry)
    await entry.runtime_data.coordinator.async_config_entry_first_refresh()

    entry.runtime_data.client.add_event_listener(
        "deviceEventUpdate", entry.runtime_data.event_store.on_device_event_update
    )
    entry.runtime_data.client.add_event_listener(
        "eventUpdate", entry.runtime_data.event_store.on_event_update
    )
    entry.runtime_data.client.add_event_listener(
        "getEvent", entry.runtime_data.event_store.on_get_event
    )
    entry.runtime_data.client.add_event_listener(
        "getEventSummary", entry.runtime_data.event_store.on_get_event_summary
    )
    entry.runtime_data.client.add_event_listener(
        "eventSummaryUpdate", entry.runtime_data.event_store.on_event_summary_update
    )

    async def refresh_subscriptions(args: dict | None) -> None:
        _LOGGER.debug("Refreshing subscriptions, caused by event: %s", args)
        for device in entry.runtime_data.devices:
            await entry.runtime_data.client.send_message(
                "getDevice", {"deviceId": device.device_id, "subscribe": True}
            )
            events = await entry.runtime_data.client.send_message(
                "getDeviceEvents", {"deviceId": device.device_id, "subscribe": True}
            )
            if events:
                events.sort(
                    key=lambda e: datetime.fromisoformat(
                        e.get(
                            "timestamp",
                            None,
                        )
                        or datetime.min.replace(tzinfo=UTC).isoformat()
                    ),
                    reverse=True,
                )
            if events and "eventId" in events[0]:
                latest_event = events[0]
                await entry.runtime_data.event_store.send_get_event_message(
                    device.device_id, latest_event["eventId"], subscribe=False
                )
                if latest_event.get("accessToken"):
                    await entry.runtime_data.event_store.send_get_event_summary(
                        device.device_id,
                        latest_event["eventId"],
                        latest_event["accessToken"],
                        subscribe=False,
                    )

    await refresh_subscriptions(None)

    async def mark_disconnected(*_args: object) -> None:
        """Make entity availability reflect a lost OnlyCat cloud connection."""
        entry.runtime_data.coordinator.async_set_update_error(
            OnlyCatApiClientCommunicationError(
                "Disconnected from the OnlyCat cloud gateway"
            )
        )

    async def handle_reconnect() -> None:
        """Restore subscriptions and entity availability after reconnecting."""
        await refresh_subscriptions(None)
        await entry.runtime_data.coordinator.async_refresh()

    entry.runtime_data.client.add_event_listener("connect", handle_reconnect)
    entry.runtime_data.client.add_event_listener("disconnect", mark_disconnected)
    entry.runtime_data.client.add_event_listener("userUpdate", refresh_subscriptions)
    await async_setup_services(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    for device in entry.runtime_data.devices:
        await entry.runtime_data.event_store.run_event_listeners(device.device_id)
    for pet in entry.runtime_data.event_store.get_pets():
        await entry.runtime_data.event_store.run_pet_listeners(pet.rfid_code)
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
        rfids = await entry.runtime_data.client.send_message(
            "getLastSeenRfidCodesByDevice", {"deviceId": device.device_id}
        )
        last_seens = await entry.runtime_data.client.send_message(
            "getRfidLastSeenByDevice", {"deviceId": device.device_id}
        )
        last_seen_rfids = {last_seen["rfidCode"]: last_seen for last_seen in last_seens}
        for rfid in rfids:
            rfid_code = rfid["rfidCode"]
            rfid_profile = await entry.runtime_data.client.send_message(
                "getRfidProfile", {"deviceId": device.device_id, "rfidCode": rfid_code}
            )
            label = rfid_profile.get("label", rfid_code)
            pet = entry.runtime_data.event_store.get_pet_by_rfid(rfid_code)
            pet.label = label
            if rfid_code in last_seen_rfids:
                last_seen = last_seen_rfids[rfid_code]
                pet.last_seen = datetime.fromisoformat(
                    last_seen.get(
                        "eventTimestamp", datetime.min.replace(tzinfo=UTC).isoformat()
                    )
                )
                pet.update_from_subevent(
                    SubEvent.from_api_response(last_seen.get("lastSubevent", None))
                )


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
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: OnlyCatConfigEntry
) -> bool:
    """Migrate old entry."""
    _LOGGER.info(
        "Migrating configuration from version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )
    if config_entry.version == 1 and "settings" in config_entry.data:
        return True
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
