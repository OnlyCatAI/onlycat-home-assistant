"""Tests for the OnlyCat API client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import socketio

from custom_components.onlycat import api
from custom_components.onlycat.api import OnlyCatApiClient


def create_socket(*, connected: bool = True) -> MagicMock:
    """Create a Socket.IO client mock with realistic connection state."""
    socket = MagicMock()
    socket.connected = connected
    socket.namespaces = {"/": "sid"} if connected else {}
    socket.call = AsyncMock(return_value={"value": 1})
    socket.connect = AsyncMock()
    socket.disconnect = AsyncMock()
    socket.shutdown = AsyncMock()
    return socket


@pytest.mark.asyncio
async def test_send_message_can_skip_reply_listeners() -> None:
    """A backfill query can consume a reply without mutating live state."""
    socket = create_socket()
    client = OnlyCatApiClient("token", MagicMock(), socket=socket)
    listener = AsyncMock()
    client.add_event_listener("getEventSummary", listener)

    reply = await client.send_message(
        "getEventSummary", {"eventId": 1}, notify_listeners=False
    )

    assert reply == {"value": 1}
    listener.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_message_connects_when_namespace_is_missing() -> None:
    """Calls reconnect before use when the default namespace is absent."""
    socket = create_socket(connected=False)

    async def connect(*_args: object, **_kwargs: object) -> None:
        socket.connected = True
        socket.namespaces = {"/": "sid"}

    socket.connect.side_effect = connect
    client = OnlyCatApiClient("token", MagicMock(), socket=socket)

    reply = await client.send_message("getDevices", {"subscribe": True})

    assert reply == {"value": 1}
    socket.connect.assert_awaited_once()
    socket.call.assert_awaited_once_with("getDevices", {"subscribe": True})


@pytest.mark.asyncio
async def test_send_message_repairs_bad_namespace_and_retries_once() -> None:
    """A proven unsent call is retried after replacing its broken namespace."""
    socket = create_socket()
    socket.call.side_effect = [
        socketio.exceptions.BadNamespaceError("/ is not connected"),
        {"value": 2},
    ]

    async def disconnect() -> None:
        socket.connected = False
        socket.namespaces = {}

    async def connect(*_args: object, **_kwargs: object) -> None:
        socket.connected = True
        socket.namespaces = {"/": "new-sid"}

    socket.disconnect.side_effect = disconnect
    socket.connect.side_effect = connect
    client = OnlyCatApiClient("token", MagicMock(), socket=socket)

    reply = await client.send_message("getDevices", {"subscribe": True})

    assert reply == {"value": 2}
    socket.disconnect.assert_awaited_once()
    socket.connect.assert_awaited_once()
    expected_call_count = 2
    assert socket.call.await_count == expected_call_count


@pytest.mark.asyncio
async def test_disconnect_event_starts_single_reconnect_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated disconnect notifications share one reconnect attempt."""
    monkeypatch.setattr(api, "RECONNECT_INITIAL_DELAY_SECONDS", 0)
    socket = create_socket(connected=False)
    connect_started = asyncio.Event()
    allow_connect = asyncio.Event()

    async def connect(*_args: object, **_kwargs: object) -> None:
        connect_started.set()
        await allow_connect.wait()
        socket.connected = True
        socket.namespaces = {"/": "new-sid"}

    socket.connect.side_effect = connect
    client = OnlyCatApiClient("token", MagicMock(), socket=socket)
    disconnected = AsyncMock()
    client.add_event_listener("disconnect", disconnected)

    await client.on_disconnected("transport error")
    await client.on_disconnected("transport error")
    await asyncio.wait_for(connect_started.wait(), timeout=1)
    allow_connect.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    socket.connect.assert_awaited_once()
    expected_disconnect_notifications = 2
    assert disconnected.await_count == expected_disconnect_notifications
    await client.disconnect()


@pytest.mark.asyncio
async def test_connect_event_refreshes_registered_subscriptions() -> None:
    """Reconnect listeners run after the namespace is restored."""
    socket = create_socket()
    client = OnlyCatApiClient("token", MagicMock(), socket=socket)
    refresh_subscriptions = AsyncMock()
    client.add_event_listener("connect", refresh_subscriptions)

    await client.on_connected()

    refresh_subscriptions.assert_awaited_once_with()
