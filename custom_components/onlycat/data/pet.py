"""Custom types for onlycat representing a pet."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.const import STATE_HOME, STATE_NOT_HOME

from .const import (
    ONLYCAT_DIRECTION_INWARD,
    ONLYCAT_DIRECTION_OUTWARD,
    ONLYCAT_SUBEVENT_ACTION_TRANSIT,
)

if TYPE_CHECKING:
    from datetime import datetime

    from .event import Event
    from .event_summary import EventSummary, SubEvent

_LOGGER = logging.getLogger(__name__)


@dataclass
class Pet:
    """Data representing a pet."""

    rfid_code: str
    location: str
    last_seen: datetime | None
    last_seen_event: Event | None = None
    last_seen_summary: EventSummary | None = None
    label: str | None = None

    def update_from_subevent(self, subevent: SubEvent) -> None:
        """Update pet data from a subevent."""
        if subevent.direction == ONLYCAT_DIRECTION_INWARD:
            if subevent.action == ONLYCAT_SUBEVENT_ACTION_TRANSIT:
                self.location = STATE_HOME
            else:
                self.location = STATE_NOT_HOME
        elif subevent.direction == ONLYCAT_DIRECTION_OUTWARD:
            if subevent.action == ONLYCAT_SUBEVENT_ACTION_TRANSIT:
                self.location = STATE_NOT_HOME
            else:
                self.location = STATE_HOME
        _LOGGER.debug(
            "Updated pet %s location to %s based on subevent",
            self.rfid_code,
            self.location,
        )
