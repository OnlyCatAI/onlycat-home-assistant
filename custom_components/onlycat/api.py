"""OnlyCat API Client."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiohttp

    from .data import OnlyCatData

import socketio

_LOGGER = logging.getLogger(__name__)

ONLYCAT_URL = "https://gateway.onlycat.com"


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
        self._socket = socket or socketio.AsyncClient(
            http_session=self._session,
            reconnection=True,
            reconnection_attempts=0,
            reconnection_delay=10,
            reconnection_delay_max=10,
            ssl_verify=True,
        )
        self._socket.on("*", self.handle_event)
        self.add_event_listener("connect", self.on_connected)

    async def connect(self) -> None:
        """Connect to wesocket client."""
        if self._socket.connected:
            return
        _LOGGER.debug("Connecting to API")

        await self._socket.connect(
            ONLYCAT_URL,
            transports=["websocket"],
            namespaces="/",
            headers={"platform": "home-assistant", "device": "onlycat-hass"},
            auth={"token": self._token},
        )

    async def disconnect(self) -> None:
        """Disconnect websocket client."""
        _LOGGER.debug("Disconnecting from API")
        await self._socket.disconnect()
        await self._socket.shutdown()

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

    async def send_message(self, event: str, data: any) -> Any | None:
        """Send a message to the API."""
        _LOGGER.debug("Sending %s message to API: %s", event, data)
        return await self._socket.call(event, data)

    async def wait(self) -> None:
        """Wait until client is disconnected."""
        await self._socket.wait()

    async def on_connected(self) -> None:
        """Handle connected event."""
        _LOGGER.debug("(Re)connected to API")
