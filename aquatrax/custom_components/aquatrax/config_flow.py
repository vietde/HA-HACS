"""Config flow for the AquaTrax integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AquaTraxAuthError, AquaTraxClient, AquaTraxConnectionError
from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_UTILITY,
    CONF_UTILITY_ID,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
    FALLBACK_UTILITIES,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_UTILITY): vol.In(FALLBACK_UTILITIES),
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class AquaTraxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AquaTrax."""

    VERSION = 1

    def __init__(self) -> None:
        self._utilities: dict[str, str] = {}

    async def _fetch_utilities(self) -> list[str]:
        """Load the utility list from the portal's login page."""
        try:
            client = AquaTraxClient(async_get_clientsession(self.hass))
            self._utilities = await client.fetch_utilities()
        except AquaTraxConnectionError:
            self._utilities = {}
        if self._utilities:
            return sorted(self._utilities)
        return FALLBACK_UTILITIES

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        utilities = await self._fetch_utilities()
        if user_input is not None:
            utility_name = user_input[CONF_UTILITY]
            utility_id = self._utilities.get(utility_name)
            if utility_id is None:
                # Fallback list has no ids; the portal login will resolve it
                # from the live dropdown at setup time.
                utility_id = ""
            await self.async_set_unique_id(f"{utility_name}:{user_input[CONF_EMAIL]}")
            self._abort_if_unique_id_configured()
            client = AquaTraxClient(async_get_clientsession(self.hass))
            try:
                if not utility_id:
                    found = await client.fetch_utilities()
                    utility_id = found.get(utility_name, "")
                await client.login(
                    utility_id, user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
            except AquaTraxAuthError:
                errors["base"] = "invalid_auth"
            except AquaTraxConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - surface as unknown error
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"AquaTrax ({utility_name})",
                    data={
                        CONF_UTILITY: utility_name,
                        CONF_UTILITY_ID: utility_id,
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UTILITY): vol.In(utilities),
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-auth when credentials stop working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm new credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            client = AquaTraxClient(async_get_clientsession(self.hass))
            try:
                await client.login(
                    entry.data[CONF_UTILITY_ID],
                    user_input[CONF_EMAIL],
                    user_input[CONF_PASSWORD],
                )
            except AquaTraxAuthError:
                errors["base"] = "invalid_auth"
            except AquaTraxConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={
                        **entry.data,
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_EMAIL, default=entry.data.get(CONF_EMAIL, "")
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return AquaTraxOptionsFlow(config_entry)


class AquaTraxOptionsFlow(OptionsFlow):
    """Handle AquaTrax options (polling interval)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_HOURS
                        ),
                    ): vol.In([1, 6, 12, 24]),
                }
            ),
        )
