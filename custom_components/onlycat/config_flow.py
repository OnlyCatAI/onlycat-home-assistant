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
from .const import (
    CONF_ENABLE_DETAILED_METRICS,
    CONF_IGNORE_FLAP_MOTION_RULES,
    CONF_IGNORE_MOTION_SENSOR_RULES,
    CONF_POLL_INTERVAL_HOURS,
    DOMAIN,
    LOGGER,
)

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

                settings = {}
                settings["ignore_flap_motion_rules"] = user_input[
                    CONF_IGNORE_FLAP_MOTION_RULES
                ]
                settings["ignore_motion_sensor_rules"] = user_input[
                    CONF_IGNORE_MOTION_SENSOR_RULES
                ]
                settings["poll_interval_hours"] = user_input[CONF_POLL_INTERVAL_HOURS]
                settings["enable_detailed_metrics"] = user_input.get(
                    CONF_ENABLE_DETAILED_METRICS, False
                )
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
                    "settings": settings,
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
                    ),
                    vol.Required(
                        CONF_IGNORE_FLAP_MOTION_RULES,
                        default=(user_input or {}).get(
                            CONF_IGNORE_FLAP_MOTION_RULES, False
                        ),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_IGNORE_MOTION_SENSOR_RULES,
                        default=(user_input or {}).get(
                            CONF_IGNORE_MOTION_SENSOR_RULES, False
                        ),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_POLL_INTERVAL_HOURS,
                        default=(user_input or {}).get(CONF_POLL_INTERVAL_HOURS, 1),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=24,
                            step=1,
                        )
                    ),
                    vol.Optional(
                        CONF_ENABLE_DETAILED_METRICS,
                        default=(user_input or {}).get(
                            CONF_ENABLE_DETAILED_METRICS, False
                        ),
                    ): selector.BooleanSelector(),
                },
            ),
            errors=_errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle a reconfiguration flow."""
        errors: dict[str, str] = {}
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        settings = {
            "ignore_flap_motion_rules": False,
            "ignore_motion_sensor_rules": False,
            "poll_interval_hours": 1,
            "enable_detailed_metrics": False,
        }
        if user_input is not None and config_entry is not None:
            settings["ignore_flap_motion_rules"] = user_input[
                CONF_IGNORE_FLAP_MOTION_RULES
            ]
            settings["ignore_motion_sensor_rules"] = user_input[
                CONF_IGNORE_MOTION_SENSOR_RULES
            ]
            settings["poll_interval_hours"] = user_input[CONF_POLL_INTERVAL_HOURS]
            settings["enable_detailed_metrics"] = user_input.get(
                CONF_ENABLE_DETAILED_METRICS, False
            )
            return self.async_update_reload_and_abort(
                config_entry,
                unique_id=config_entry.unique_id,
                data={
                    "user_id": config_entry.data["user_id"],
                    "token": config_entry.data["token"],
                    "settings": settings,
                },
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_IGNORE_FLAP_MOTION_RULES,
                        default=(user_input or {}).get(
                            CONF_IGNORE_FLAP_MOTION_RULES, False
                        ),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_IGNORE_MOTION_SENSOR_RULES,
                        default=(user_input or {}).get(
                            CONF_IGNORE_MOTION_SENSOR_RULES, False
                        ),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_POLL_INTERVAL_HOURS,
                        default=(user_input or {}).get(CONF_POLL_INTERVAL_HOURS, 6),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=24,
                            step=1,
                        )
                    ),
                    vol.Optional(
                        CONF_ENABLE_DETAILED_METRICS,
                        default=(user_input or {}).get(
                            CONF_ENABLE_DETAILED_METRICS, False
                        ),
                    ): selector.BooleanSelector(),
                },
            ),
            errors=errors,
        )

    async def _validate_connection(self, client: OnlyCatApiClient) -> None:
        """Validate connection."""
        await client.connect()
        await client.send_message("getDevices", {"subscribe": False})
        await client.disconnect()
