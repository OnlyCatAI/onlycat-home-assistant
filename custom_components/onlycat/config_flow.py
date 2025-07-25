"""Adds config flow for OnlyCat."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import (
    OnlyCatApiClient,
    OnlyCatApiClientAuthenticationError,
    OnlyCatApiClientCommunicationError,
    OnlyCatApiClientError,
)
from .const import DOMAIN, LOGGER

_LOGGER = logging.getLogger(__name__)


class OnlyCatFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for OnlyCat."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        _errors = {}
        if user_input is not None:
            try:
                _LOGGER.debug("Initializing API client")
                client = OnlyCatApiClient(
                    user_input[CONF_ACCESS_TOKEN],
                    session=async_create_clientsession(self.hass),
                )
                user_id = None

                async def on_user_update(data: any) -> None:
                    nonlocal user_id
                    if data is not None and "id" in data:
                        user_id = str(data["id"])

                client.add_event_listener("userUpdate", on_user_update)
                await self._validate_connection(client)
            except OnlyCatApiClientAuthenticationError as exception:
                LOGGER.warning(exception)
                _errors["base"] = "auth"
            except OnlyCatApiClientCommunicationError as exception:
                LOGGER.error(exception)
                _errors["base"] = "connection"
            except OnlyCatApiClientError as exception:
                LOGGER.exception(exception)
                _errors["base"] = "unknown"
            else:
                _LOGGER.debug("Creating entry with id %s", user_id)
                await self.async_set_unique_id(unique_id=user_id)
                self._abort_if_unique_id_configured()
                return_data = {
                    "user_id": user_id,
                    "token": user_input[CONF_ACCESS_TOKEN],
                }
                return self.async_create_entry(
                    title=user_id,
                    data=return_data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ACCESS_TOKEN,
                        default=(user_input or {}).get(
                            CONF_ACCESS_TOKEN, vol.UNDEFINED
                        ),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    )
                },
            ),
            errors=_errors,
        )

    async def _validate_connection(self, client: OnlyCatApiClient) -> None:
        """Validate connection."""
        await client.connect()
        await client.send_message("getDevices", {"subscribe": False})
        await client.disconnect()
