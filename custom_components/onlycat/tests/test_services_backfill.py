"""Tests for the OnlyCat historical event-summary backfill."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.onlycat.data.event_store import EventStore
from custom_components.onlycat.services import async_handle_backfill_event_summaries


def make_event(
    device_id: str,
    event_id: int,
    global_id: int,
    *,
    access_token: str | None = "ephemeral-token",
) -> dict:
    """Build a gateway event response."""
    return {
        "globalId": global_id,
        "deviceId": device_id,
        "eventId": event_id,
        "timestamp": f"2026-07-16T00:{event_id % 60:02d}:25+00:00",
        "frameCount": 12,
        "eventTriggerSource": 3,
        "eventClassification": 3,
        "accessToken": access_token,
        "rfidCodes": [],
    }


def make_summary(device_id: str, event_id: int) -> dict:
    """Build a gateway event-summary response."""
    return {
        "deviceId": device_id,
        "eventId": event_id,
        "subevents": [
            {
                "startFrameIndex": 1,
                "endFrameIndex": 11,
                "rfidCode": "958000000000001",
                "direction": "INWARD",
                "action": "DENY",
            }
        ],
    }


def make_entry(device_id: str, client: SimpleNamespace) -> tuple[object, AsyncMock]:
    """Build a minimal config entry and capture its replay listener."""
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
    return entry, replay_listener


@pytest.mark.asyncio
async def test_bounded_backfill_uses_only_the_latest_gateway_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default backfill remains bounded and does not paginate."""
    device_id = "OC-00000000001"
    event = make_event(device_id, 1179, 2179)

    async def send_message(topic: str, data: dict, **kwargs: bool) -> object:
        assert kwargs == {"notify_listeners": False}
        if topic == "getDeviceEvents":
            assert data == {"deviceId": device_id, "subscribe": False}
            return [event]
        if topic == "getEventSummary":
            return make_summary(device_id, data["eventId"])
        raise AssertionError(f"Unexpected topic: {topic}")

    client = SimpleNamespace(send_message=AsyncMock(side_effect=send_message))
    entry, replay_listener = make_entry(device_id, client)
    call = SimpleNamespace(
        data={"all_history": False, "days": 31, "maximum_events": 1}
    )
    monkeypatch.setattr("custom_components.onlycat.services.BACKFILL_DELAY_SECONDS", 0)

    result = await async_handle_backfill_event_summaries(call, entry)

    assert result == {
        "pages": 1,
        "listed": 1,
        "unique_events": 1,
        "eligible": 1,
        "replayed": 1,
        "summaries": 1,
        "skipped": 0,
        "failed": 0,
    }
    replay_listener.assert_awaited_once()
    replay_event, replay_summary, historical = replay_listener.await_args.args
    assert replay_event.event_id == 1179
    assert replay_summary.event_id == 1179
    assert historical is True


@pytest.mark.asyncio
async def test_full_backfill_pages_backwards_and_deduplicates_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All-history mode follows the oldest global ID until an empty page."""
    device_id = "OC-00000000001"
    newest = make_event(device_id, 103, 203)
    overlap = make_event(device_id, 102, 202)
    oldest = make_event(device_id, 101, 201)
    page_requests: list[dict] = []

    async def send_message(topic: str, data: dict, **kwargs: bool) -> object:
        assert kwargs == {"notify_listeners": False}
        if topic == "getDeviceEvents":
            page_requests.append(data)
            before = data.get("beforeGlobalId")
            if before is None:
                return [newest, overlap]
            if before == 202:
                return [overlap, oldest]
            if before == 201:
                return []
            raise AssertionError(f"Unexpected cursor: {before}")
        if topic == "getEventSummary":
            return make_summary(device_id, data["eventId"])
        raise AssertionError(f"Unexpected topic: {topic}")

    client = SimpleNamespace(send_message=AsyncMock(side_effect=send_message))
    entry, replay_listener = make_entry(device_id, client)
    call = SimpleNamespace(data={"all_history": True})
    monkeypatch.setattr("custom_components.onlycat.services.BACKFILL_DELAY_SECONDS", 0)
    monkeypatch.setattr(
        "custom_components.onlycat.services.BACKFILL_PAGE_DELAY_SECONDS", 0
    )

    result = await async_handle_backfill_event_summaries(call, entry)

    assert page_requests == [
        {"deviceId": device_id, "subscribe": False},
        {
            "deviceId": device_id,
            "subscribe": False,
            "beforeGlobalId": 202,
        },
        {
            "deviceId": device_id,
            "subscribe": False,
            "beforeGlobalId": 201,
        },
    ]
    assert result == {
        "pages": 3,
        "listed": 4,
        "unique_events": 3,
        "eligible": 3,
        "replayed": 3,
        "summaries": 3,
        "skipped": 0,
        "failed": 0,
    }
    assert [
        invocation.args[0].event_id
        for invocation in replay_listener.await_args_list
    ] == [101, 102, 103]


@pytest.mark.asyncio
async def test_backfill_preserves_base_event_without_a_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An old event remains useful even when its summary token is absent."""
    device_id = "OC-00000000001"
    event = make_event(device_id, 1179, 2179, access_token=None)

    async def send_message(topic: str, _data: dict, **kwargs: bool) -> object:
        assert kwargs == {"notify_listeners": False}
        if topic == "getDeviceEvents":
            return [event]
        raise AssertionError(f"Unexpected topic: {topic}")

    client = SimpleNamespace(send_message=AsyncMock(side_effect=send_message))
    entry, replay_listener = make_entry(device_id, client)
    call = SimpleNamespace(
        data={"all_history": False, "days": 31, "maximum_events": 1}
    )
    monkeypatch.setattr("custom_components.onlycat.services.BACKFILL_DELAY_SECONDS", 0)

    result = await async_handle_backfill_event_summaries(call, entry)

    assert result["replayed"] == 1
    assert result["summaries"] == 0
    assert result["skipped"] == 1
    replay_event, replay_summary, historical = replay_listener.await_args.args
    assert replay_event.event_id == 1179
    assert replay_summary is None
    assert historical is True
