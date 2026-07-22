"""Tests for the OnlyCat historical event-summary backfill."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.onlycat.data.event_store import EventStore
from custom_components.onlycat.services import async_handle_backfill_event_summaries


@pytest.mark.asyncio
async def test_backfill_is_bounded_and_does_not_notify_live_api_listeners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The manual backfill replays summaries through its isolated listener path."""
    device_id = "OC-00000000001"
    event = {
        "deviceId": device_id,
        "eventId": 1179,
        "timestamp": "2026-07-16T00:19:25+00:00",
        "frameCount": 12,
        "eventTriggerSource": 3,
        "eventClassification": 3,
        "accessToken": "ephemeral-token",
        "rfidCodes": [],
    }
    summary = {
        "deviceId": device_id,
        "eventId": 1179,
        "subevents": [
            {
                "startFrameIndex": 1,
                "endFrameIndex": 11,
                "rfidCode": "958000000000001",
                "direction": "INWARD",
                "action": "LOCKED",
            }
        ],
    }

    async def send_message(topic: str, _data: dict, **kwargs: bool) -> object:
        assert kwargs == {"notify_listeners": False}
        if topic == "getDeviceEvents":
            return [event]
        if topic == "getEventSummary":
            return summary
        raise AssertionError(f"Unexpected topic: {topic}")

    client = SimpleNamespace(send_message=AsyncMock(side_effect=send_message))
    store = EventStore(client)
    replay_listener = AsyncMock()
    store.add_history_replay_listener(device_id, replay_listener)
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(
            client=client,
            devices=[SimpleNamespace(device_id=device_id)],
            event_store=store,
        )
    )
    call = SimpleNamespace(data={"days": 31, "maximum_events": 1})
    monkeypatch.setattr("custom_components.onlycat.services.BACKFILL_DELAY_SECONDS", 0)

    result = await async_handle_backfill_event_summaries(call, entry)

    assert result == {
        "listed": 1,
        "eligible": 1,
        "replayed": 1,
        "skipped": 0,
        "failed": 0,
    }
    replay_listener.assert_awaited_once()
    replay_event, replay_summary, historical = replay_listener.await_args.args
    assert replay_event.event_id == 1179
    assert replay_summary.event_id == 1179
    assert historical is True
