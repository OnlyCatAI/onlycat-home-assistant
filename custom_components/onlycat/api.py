"""OnlyCat API Client."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import suppress
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiohttp

    from .data import OnlyCatData

import socketio

_LOGGER = logging.getLogger(__name__)

ONLYCAT_URL = "https://gateway.onlycat.com"
RECONNECT_INITIAL_DELAY_SECONDS = 5.0
RECONNECT_MAX_DELAY_SECONDS = 60.0


class OnlyCatApiClientError(Exception):
    """Exception to indicate a general API error."""


class OnlyCatApiClientCommunicationError(
    OnlyCatApiClientError,
):
    """Exception to indicate a communication error."""


class OnlyCatApiClientAuthenticationError(
    OnlyCatApiClientError,
):
    """Exception to indicate an authentication error."""


class OnlyCatApiClient:
    """Only Cat API Client."""

    def __init__(
        self,
        token: str,
        session: aiohttp.ClientSession,
        data: OnlyCatData | None = None,
        socket: socketio.AsyncClient | None = None,
    ) -> None:
        """Sample API Client."""
        self._token = token
        self._data = data
        self._session = session
        self._listeners = defaultdict(list)
        self._connect_lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task[None] | None = None
        self._closing = False
        self._socket = socket or socketio.AsyncClient(
            http_session=self._session,
            reconnection=False,
            ssl_verify=True,
        )
        self._socket.on("*", self.handle_event)
        self._socket.on("connect", self.on_connected)
        self._socket.on("disconnect", self.on_disconnected)

    def _is_connected(self) -> bool:
        """Return whether the default namespace is ready for calls."""
        if not self._socket.connected:
            return False

        namespaces = getattr(self._socket, "namespaces", None)
        return not isinstance(namespaces, dict) or "/" in namespaces

    async def _connect_locked(self) -> None:
        """Connect while the caller holds the connection lock."""
        if self._is_connected():
            return

        _LOGGER.debug("Connecting to API")
        await self._socket.connect(
            ONLYCAT_URL,
            transports=["websocket"],
            namespaces="/",
            headers={"platform": "home-assistant", "device": "onlycat-hass"},
            auth={"token": self._token},
        )

    async def connect(self) -> None:
        """Connect to websocket client."""
        self._closing = False

        try:
            async with self._connect_lock:
                await self._connect_locked()
        except Exception as exception:
            raise OnlyCatApiClientError from exception

    async def disconnect(self) -> None:
        """Disconnect websocket client."""
        self._closing = True
        reconnect_task = self._reconnect_task
        self._reconnect_task = None
        if reconnect_task and reconnect_task is not asyncio.current_task():
            reconnect_task.cancel()
            with suppress(asyncio.CancelledError):
                await reconnect_task

        _LOGGER.debug("Disconnecting from API")
        if self._socket.connected:
            await self._socket.disconnect()
        await self._socket.shutdown()

    def _start_reconnect(self) -> None:
        """Start one background reconnect loop if one is not already running."""
        if self._closing or self._is_connected():
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return

        self._reconnect_task = asyncio.create_task(
            self._reconnect_loop(), name="onlycat-reconnect"
        )

    async def _reconnect_loop(self) -> None:
        """Reconnect with bounded exponential backoff until connected or closed."""
        delay = RECONNECT_INITIAL_DELAY_SECONDS
        try:
            while not self._closing and not self._is_connected():
                await asyncio.sleep(delay)
                try:
                    async with self._connect_lock:
                        await self._connect_locked()
                except Exception:  # noqa: BLE001
                    _LOGGER.warning(
                        "Could not reconnect to OnlyCat; retrying in %.0f seconds",
                        min(delay * 2, RECONNECT_MAX_DELAY_SECONDS),
                        exc_info=True,
                    )
                    delay = min(delay * 2, RECONNECT_MAX_DELAY_SECONDS)
        finally:
            if self._reconnect_task is asyncio.current_task():
                self._reconnect_task = None

    async def _repair_namespace(self) -> None:
        """Replace a transport that is connected without the default namespace."""
        async with self._connect_lock:
            if self._socket.connected:
                await self._socket.disconnect()
            await self._connect_locked()

    def add_event_listener(self, event: str, callback: Any) -> None:
        """Add an event listener."""
        self._listeners[event].append(callback)
        _LOGGER.debug(
            "Added event listener for event %s: %s", event, callback.__module__
        )

    async def handle_event(self, event: str, *args: Any) -> None:
        """Handle an event."""
        _LOGGER.debug("Received event: %s with args: %s", event, args)
        for callback in self._listeners[event]:
            try:
                await callback(*args)
            except Exception:
                _LOGGER.exception(
                    "Error while handling event %s with args %s", event, args
                )

    async def send_message(
        self,
        event: str,
        data: any,
        *,
        notify_listeners: bool = True,
    ) -> Any | None:
        """Send a message to the API."""
        _LOGGER.debug(
            "Sending message to API - Event: %s, Data: %s, Data Type: %s",
            event,
            data,
            type(data),
        )

        if not self._is_connected():
            try:
                await self.connect()
            except OnlyCatApiClientError as exception:
                self._start_reconnect()
                raise OnlyCatApiClientCommunicationError from exception

        try:
            reply = await self._socket.call(event, data)
        except socketio.exceptions.BadNamespaceError:
            _LOGGER.warning(
                "OnlyCat namespace disconnected during %s; reconnecting", event
            )
            try:
                await self._repair_namespace()
                reply = await self._socket.call(event, data)
            except Exception as exception:
                self._start_reconnect()
                _LOGGER.exception(
                    "Error retrying socket.call for event %s with data %s", event, data
                )
                raise OnlyCatApiClientCommunicationError from exception
        except Exception as exception:
            self._start_reconnect()
            _LOGGER.exception(
                "Error during socket.call for event %s with data %s", event, data
            )
            raise OnlyCatApiClientCommunicationError from exception
        _LOGGER.debug("Received reply for event %s: %s", event, reply)
        if reply is None:
            return None
        if notify_listeners:
            for callback in self._listeners[event]:
                try:
                    await callback(reply)
                except Exception:
                    _LOGGER.exception(
                        "Error while handling reply for event %s with data %s: %s",
                        event,
                        data,
                        reply,
                    )
        return reply

    async def wait(self) -> None:
        """Wait until client is disconnected."""
        await self._socket.wait()

    async def on_connected(self) -> None:
        """Handle connected event."""
        _LOGGER.debug("(Re)connected to API")
        for callback in self._listeners["connect"]:
            try:
                await callback()
            except Exception:
                _LOGGER.exception("Error while handling API reconnection")

    async def on_disconnected(self, *args: Any) -> None:
        """Handle a lost websocket connection."""
        if self._closing:
            return
        _LOGGER.warning("Disconnected from OnlyCat API: %s", args or "unknown reason")
        for callback in self._listeners["disconnect"]:
            try:
                await callback(*args)
            except Exception:
                _LOGGER.exception("Error while handling API disconnection")
        self._start_reconnect()
