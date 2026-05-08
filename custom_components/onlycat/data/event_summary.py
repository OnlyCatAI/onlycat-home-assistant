"""Custom types for onlycat representing a flap event summary."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields
from datetime import datetime

_LOGGER = logging.getLogger(__name__)


class SubEvent:
    """Data representing a subevent of an OnlyCat flap event summary."""

    start_frame_index: int
    end_frame_index: int
    rfid_code: str | None
    direction: str
    action: str

    @classmethod
    def from_api_response(cls, api_subevent: dict) -> SubEvent | None:
        """Create a SubEvent instance from API response data."""
        if not all(
            key in api_subevent
            for key in (
                "startFrameIndex",
                "endFrameIndex",
                "rfidCode",
                "direction",
                "action",
            )
        ):
            _LOGGER.warning(
                "Skipping incomplete subevent in API response: %s", api_subevent
            )
            return None
        subevent = cls()
        subevent.start_frame_index = api_subevent["startFrameIndex"]
        subevent.end_frame_index = api_subevent["endFrameIndex"]
        subevent.rfid_code = api_subevent.get("rfidCode")
        subevent.direction = api_subevent.get("direction")
        subevent.action = api_subevent.get("action")
        return subevent


@dataclass
class EventSummary:
    """Data representing an OnlyCat flap event summary."""

    device_id: str
    event_id: int
    subevents: list[SubEvent] = field(default_factory=list)
    processed_frame_count: int | None = None
    invalidated_at: None = None
    processing_at: None = None
    processing_by: None = None
    timestamp: datetime | None = None

    @classmethod
    def from_api_response(cls, api_summary: dict) -> EventSummary | None:
        """Create an Event instance from API response data."""
        timestamp_str = api_summary.get("timestamp")
        api_summary = api_summary.get("body", api_summary)
        if "deviceId" not in api_summary or "eventId" not in api_summary:
            return None
        device_id = api_summary.get("deviceId")
        event_id = api_summary.get("eventId")
        processed_frame_count = api_summary.get("processedFrameCount")
        invalidated_at = api_summary.get("invalidatedAt")
        processing_at = api_summary.get("processingAt")
        processing_by = api_summary.get("processingBy")
        subevents = []
        for subevent_data in api_summary.get("subevents", []):
            subevent = SubEvent.from_api_response(subevent_data)
            if subevent:
                subevents.append(subevent)
        return cls(
            device_id=device_id,
            event_id=event_id,
            subevents=subevents,
            processed_frame_count=processed_frame_count,
            invalidated_at=invalidated_at,
            processing_at=processing_at,
            processing_by=processing_by,
            timestamp=datetime.fromisoformat(timestamp_str) if timestamp_str else None,
        )

    def update_from(self, updated_summary: EventSummary) -> None:
        """Update the event summary with data from another event summary instance."""
        if updated_summary is None:
            return
        for obj_field in fields(self):
            new_value = getattr(updated_summary, obj_field.name, None)
            if new_value is not None:
                setattr(self, obj_field.name, new_value)
