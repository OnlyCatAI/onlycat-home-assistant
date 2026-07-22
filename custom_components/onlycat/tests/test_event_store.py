"""Tests for EventStore."""

from unittest.mock import AsyncMock, call

import pytest

from custom_components.onlycat.data.event import Event
from custom_components.onlycat.data.event_store import EventStore
from custom_components.onlycat.data.event_summary import EventSummary


@pytest.mark.asyncio
async def test_run_listeners_no_current_event() -> None:
    """Test run_listeners when listeners are registered but no event data exists."""
    api_client = AsyncMock()
    store = EventStore(api_client)

    device_id = "OC-00000000001"

    # Register 7 listeners, matching the entity types that call add_event_listener
    listener_lock = AsyncMock(name="lock_on_event_update")
    listener_contraband = AsyncMock(name="contraband_on_event_update")
    listener_event = AsyncMock(name="event_on_event_update")
    listener_human = AsyncMock(name="human_on_event_update")
    listener_camera = AsyncMock(name="camera_on_event_update")
    listener_image = AsyncMock(name="image_on_event_update")
    listener_device_tracker = AsyncMock(name="device_tracker_on_event_update")

    store.add_event_listener(device_id, listener_lock)
    store.add_event_listener(device_id, listener_contraband)
    store.add_event_listener(device_id, listener_event)
    store.add_event_listener(device_id, listener_human)
    store.add_event_listener(device_id, listener_camera)
    store.add_event_listener(device_id, listener_image)
    store.add_event_listener(device_id, listener_device_tracker)

    # _current_events and _current_images are empty — no event data yet
    assert store._current_events == {}  # noqa: SLF001
    assert store._current_images == {}  # noqa: SLF001

    await store.run_event_listeners(device_id)

    # No callback should have been called since there is no event for this device
    listener_lock.assert_not_called()
    listener_contraband.assert_not_called()
    listener_event.assert_not_called()
    listener_human.assert_not_called()
    listener_camera.assert_not_called()
    listener_image.assert_not_called()
    listener_device_tracker.assert_not_called()


@pytest.mark.asyncio
async def test_run_listeners_never_calls_with_none() -> None:
    """
    Test that listeners are never called with None as the event parameter.

    Covers two scenarios:
    1. _current_events has an explicit None value for the device.
    2. _current_events has a real Event — callbacks should receive it, not None.
    """
    api_client = AsyncMock()
    store = EventStore(api_client)

    device_id = "OC-00000000001"

    listener_lock = AsyncMock(name="lock_on_event_update")
    listener_contraband = AsyncMock(name="contraband_on_event_update")
    listener_event = AsyncMock(name="event_on_event_update")
    listener_human = AsyncMock(name="human_on_event_update")
    listener_camera = AsyncMock(name="camera_on_event_update")
    listener_image = AsyncMock(name="image_on_event_update")
    listener_device_tracker = AsyncMock(name="device_tracker_on_event_update")

    all_listeners = [
        listener_lock,
        listener_contraband,
        listener_event,
        listener_human,
        listener_camera,
        listener_image,
        listener_device_tracker,
    ]

    store.add_event_listener(device_id, listener_lock)
    store.add_event_listener(device_id, listener_contraband)
    store.add_event_listener(device_id, listener_event)
    store.add_event_listener(device_id, listener_human)
    store.add_event_listener(device_id, listener_camera)
    store.add_event_listener(device_id, listener_image)
    store.add_event_listener(device_id, listener_device_tracker)

    # Scenario 1: _current_events entry is explicitly None
    store._current_events[device_id] = None  # noqa: SLF001

    await store.run_event_listeners(device_id)

    for listener in all_listeners:
        listener.assert_not_called()

    # Scenario 2: _current_events has a real Event — ensure it's passed, not None
    real_event = Event(device_id=device_id, event_id=42)
    store._current_events[device_id] = real_event  # noqa: SLF001

    await store.run_event_listeners(device_id)

    for listener in all_listeners:
        listener.assert_called_once_with(real_event)
        # Verify the argument was never None in any call
        for c in listener.call_args_list:
            assert c != call(None), "Listener must never be called with None"


@pytest.mark.asyncio
async def test_history_replay_restores_current_event() -> None:
    """Historical replay uses isolated listeners and restores the live event."""
    store = EventStore(AsyncMock())
    device_id = "OC-00000000001"
    historical_event = Event(device_id=device_id, event_id=41)
    historical_summary = EventSummary(device_id=device_id, event_id=41)
    current_event = Event(device_id=device_id, event_id=42)
    current_summary = EventSummary(device_id=device_id, event_id=42)
    listener = AsyncMock()
    store.add_history_replay_listener(device_id, listener)
    store._current_events[device_id] = current_event  # noqa: SLF001
    store._current_summaries[device_id] = current_summary  # noqa: SLF001

    await store.run_history_replay_listeners(historical_event, historical_summary)
    await store.restore_history_replay_listeners(device_id)

    assert listener.await_args_list == [
        call(historical_event, historical_summary, True),
        call(current_event, current_summary, False),
    ]
