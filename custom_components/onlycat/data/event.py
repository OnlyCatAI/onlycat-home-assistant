"""Custom types for onlycat representing a flap event."""

from __future__ import annotations

import logging
from dataclasses import dataclass, fields
from datetime import datetime
from enum import Enum

from .type import Type

_LOGGER = logging.getLogger(__name__)


class EventTriggerSource(Enum):
    """Enum representing the source of an OnlyCat flap event."""

    UNKNOWN = -1
    MANUAL = 0
    REMOTE = 1
    INDOOR_MOTION = 2
    OUTDOOR_MOTION = 3

    @classmethod
    def _missing_(cls, value: str) -> EventTriggerSource:
        """Handle missing enum values in case of API extensions."""
        _LOGGER.warning("Unknown event trigger source: %s", value)
        return cls.UNKNOWN


class EventClassification(Enum):
    """Enum representing the classification of an OnlyCat flap event."""

    UNKNOWN = 0
    CLEAR = 1
    SUSPICIOUS = 2
    CONTRABAND = 3
    HUMAN_ACTIVITY = 4
    REMOTE_UNLOCK = 10

    @classmethod
    def _missing_(cls, value: str) -> EventClassification:
        """Handle missing enum values in case of API extensions."""
        _LOGGER.warning("Unknown event classification: %s", value)
        return cls.UNKNOWN


class EventFlapstate(Enum):
    """Enum representing the flap state during an OnlyCat flap event."""

    CLOSED = 0
    OPEN_INWARD = 1
    OPEN_OUTWARD = 2
    INVALID = 3

    @classmethod
    def _missing_(cls, value: str) -> EventFlapstate:
        """Handle missing enum values in case of API extensions."""
        _LOGGER.warning("Unknown event flap state: %s", value)
        return cls.UNKNOWN


class EventMotionstate(Enum):
    """Enum representing the motion sensor state during an OnlyCat flap event."""

    UNKNOWN = 0
    NONE = 1
    INDOOR = 2
    OUTDOOR = 3

    @classmethod
    def _missing_(cls, value: str) -> EventMotionstate:
        """Handle missing enum values in case of API extensions."""
        _LOGGER.warning("Unknown event motion sensor state: %s", value)
        return cls.UNKNOWN


@dataclass
class Event:
    """Data representing an OnlyCat flap event."""

    global_id: int | None = None
    device_id: str | None = None
    event_id: int | None = None
    timestamp: datetime | None = None
    frame_count: int | None = None
    event_trigger_source: EventTriggerSource | None = EventTriggerSource.UNKNOWN
    event_classification: EventClassification | None = EventClassification.UNKNOWN
    poster_frame_index: int | None = None
    access_token: str | None = None
    rfid_codes: list[str] | None = None

    @classmethod
    def from_api_response(cls, api_event: dict) -> Event | None:
        """Create an Event instance from API response data."""
        if not api_event:
            return None
        timestamp = api_event.get("timestamp")
        trigger_source = api_event.get("eventTriggerSource")
        classification = api_event.get("eventClassification")

        return cls(
            global_id=api_event.get("globalId"),
            device_id=api_event.get("deviceId"),
            event_id=api_event.get("eventId"),
            timestamp=datetime.fromisoformat(timestamp) if timestamp else None,
            frame_count=api_event.get("frameCount"),
            event_trigger_source=EventTriggerSource(int(trigger_source))
            if trigger_source
            else None,
            event_classification=EventClassification(int(classification))
            if classification
            else None,
            poster_frame_index=api_event.get("posterFrameIndex"),
            access_token=api_event.get("accessToken"),
            rfid_codes=api_event.get("rfidCodes", []),
        )

    def update_from(self, updated_event: Event) -> None:
        """Update the event with data from another event instance."""
        if updated_event is None:
            return

        for field in fields(self):
            new_value = getattr(updated_event, field.name, None)
            if new_value is not None:
                setattr(self, field.name, new_value)


@dataclass
class EventUpdate:
    """Data representing an update to an OnlyCat flap event."""

    device_id: str
    event_id: int
    type: Type
    event: Event

    @classmethod
    def from_api_response(cls, api_event: dict) -> EventUpdate | None:
        """Create an EventUpdate instance from API response data."""
        device_id = api_event.get("deviceId", api_event.get("body").get("deviceId"))
        event_id = api_event.get("eventId", api_event.get("body").get("eventId"))
        event_type = (
            Type(api_event.get("type")) if api_event.get("type") else Type.UNKNOWN
        )
        event = Event.from_api_response(api_event.get("body"))
        if event.event_id is None:
            event.event_id = event_id
        return cls(
            device_id=device_id,
            event_id=event_id,
            type=event_type,
            event=event,
        )
