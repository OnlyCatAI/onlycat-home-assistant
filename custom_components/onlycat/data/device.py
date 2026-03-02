"""Custom types for onlycat representing a Device."""

from __future__ import annotations

import logging
import zoneinfo
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime, tzinfo
from typing import TYPE_CHECKING

from .event import EventTriggerSource
from .pet import PolicyResult
from .type import Type

if TYPE_CHECKING:
    from custom_components.onlycat.data import OnlyCatConfigEntry

    from .event import Event

from .policy import DeviceTransitPolicy

_LOGGER = logging.getLogger(__name__)


@dataclass
class DeviceConnectivity:
    """Data representing the connectivity of an OnlyCat device."""

    connected: bool
    disconnect_reason: str
    timestamp: datetime

    @classmethod
    def from_api_response(cls, api_connectivity: dict) -> DeviceConnectivity | None:
        """Create a DeviceConnectivity instance from API response data."""
        if api_connectivity is None:
            return None

        return cls(
            connected=api_connectivity.get("connected"),
            disconnect_reason=api_connectivity.get("disconnectReason"),
            timestamp=datetime.fromtimestamp(
                api_connectivity.get("timestamp") / 1000.0, tz=UTC
            ),
        )


@dataclass
class Device:
    """Data representing an OnlyCat device."""

    device_id: str
    config_entry: OnlyCatConfigEntry | None = None
    connectivity: DeviceConnectivity | None = None
    description: str | None = None
    time_zone: tzinfo | None = UTC
    device_transit_policy_id: int | None = None
    device_transit_policies: dict[int, DeviceTransitPolicy] | None = None
    settings: dict | None = None

    _policy_update_listeners: list[callable] = field(default_factory=list)

    @property
    def device_transit_policy(self) -> DeviceTransitPolicy | None:
        """Get the current transit policy object for the device via its id."""
        if not self.device_transit_policies or self.device_transit_policy_id is None:
            return None
        return self.device_transit_policies.get(self.device_transit_policy_id, None)

    @classmethod
    def from_api_response(
        cls,
        api_device: dict,
        config_entry: OnlyCatConfigEntry | None = None,
        device_id: str | None = None,
    ) -> Device | None:
        """Create a Device instance from API response data."""
        if api_device is None:
            return None
        timezone_str = api_device.get("timeZone")
        if timezone_str is not None:
            try:
                timezone = zoneinfo.ZoneInfo(timezone_str)
            except zoneinfo.ZoneInfoNotFoundError:
                _LOGGER.warning("Unable to parse timezone: %s", timezone_str)
                timezone = UTC
        else:
            timezone = UTC
        device_id = api_device.get("deviceId", device_id)
        if device_id is None:
            return None
        return cls(
            device_id=device_id,
            config_entry=config_entry,
            connectivity=DeviceConnectivity.from_api_response(
                api_device.get("connectivity")
            ),
            time_zone=timezone,
            description=api_device.get("description"),
            device_transit_policy_id=api_device.get("deviceTransitPolicyId"),
        )

    async def handle_device_update(self, data: dict) -> None:
        """Update the device with data from another Device instance."""
        if data.get("deviceId") != self.device_id:
            return
        update = DeviceUpdate.from_api_response(data)
        await self.config_entry.runtime_data.client.send_message(
            "getDevice", {"deviceId": update.device_id, "subscribe": True}
        )

    async def update_device_from_api(self, data: dict) -> None:
        """Update the device with data from an API response."""
        if data.get("deviceId") != self.device_id:
            return
        updated_device = Device.from_api_response(
            data, self.config_entry, self.device_id
        )
        if updated_device is None:
            return
        for obj_field in fields(self):
            new_value = getattr(updated_device, obj_field.name, None)
            if new_value is not None:
                setattr(self, obj_field.name, new_value)
        if self.device_transit_policy_id is not None:
            await self.config_entry.runtime_data.client.send_message(
                "getDeviceTransitPolicy",
                {"deviceTransitPolicyId": self.device_transit_policy_id},
            )

    def is_unlocked_in_idle_state(self) -> bool | None:
        """Check if the device is unlocked in idle state."""
        if (
            not self.device_transit_policy
            or not self.device_transit_policy.transit_policy
        ):
            _LOGGER.debug("Unable to determine lock state, no transit policy set.")
            return None

        return not self.device_transit_policy.transit_policy.idle_lock

    def is_unlocked_by_event(self, event: Event) -> bool | None:
        """Check if the device is unlocked by the given event."""
        if event.event_trigger_source == EventTriggerSource.REMOTE:
            return True
        policy_result = self.device_transit_policy.determine_policy_result(event)
        if policy_result == PolicyResult.UNLOCKED:
            return True
        if policy_result == PolicyResult.LOCKED:
            return False
        return None

    async def update_device_transit_policy(
        self, transit_policy: DeviceTransitPolicy
    ) -> None:
        """Update the device's transit policy."""
        if self.device_transit_policies is None:
            self.device_transit_policies = {}
        self.device_transit_policies.update(
            {transit_policy.device_transit_policy_id: transit_policy}
        )
        for listener in self._policy_update_listeners:
            listener()

    async def update_device_transit_policy_from_api(self, data: dict) -> None:
        """Update the device's transit policy with API response data."""
        transit_policy = DeviceTransitPolicy.from_api_response(data, self)
        await self.update_device_transit_policy(transit_policy)

    def add_policy_update_listener(self, listener: callable) -> None:
        """Add a listener to be called when the device transit policy is updated."""
        self._policy_update_listeners.append(listener)


@dataclass
class DeviceUpdate:
    """Data representing an update to a device."""

    device_id: str
    type: Type
    body: Device

    @classmethod
    def from_api_response(cls, api_event: dict) -> DeviceUpdate | None:
        """Create a DeviceUpdate instance from API response data."""
        if api_event is None:
            return None
        return cls(
            device_id=api_event["deviceId"],
            type=Type(api_event["type"]) if api_event.get("type") else Type.UNKNOWN,
            body=Device.from_api_response(
                api_event.get("body"),
                device_id=api_event["deviceId"],
            ),
        )
