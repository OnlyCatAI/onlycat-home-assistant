"""Tests for the OnlyCat API client."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.onlycat.api import OnlyCatApiClient


@pytest.mark.asyncio
async def test_send_message_can_skip_reply_listeners() -> None:
    """A backfill query can consume a reply without mutating live state."""
    socket = MagicMock()
    socket.call = AsyncMock(return_value={"value": 1})
    client = OnlyCatApiClient("token", MagicMock(), socket=socket)  # noqa: S106
    listener = AsyncMock()
    client.add_event_listener("getEventSummary", listener)

    reply = await client.send_message(
        "getEventSummary", {"eventId": 1}, notify_listeners=False
    )

    assert reply == {"value": 1}
    listener.assert_not_awaited()
