"""Set up the AquaTrax integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
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
)
from .coordinator import AquaTraxCoordinator

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AquaTrax from a config entry."""
    client = AquaTraxClient(async_get_clientsession(hass))
    coordinator = AquaTraxCoordinator(
        hass,
        client,
        utility_id=entry.data[CONF_UTILITY_ID],
        utility_name=entry.data.get(CONF_UTILITY, ""),
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        update_interval_hours=entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_HOURS
        ),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except AquaTraxAuthError as err:
        raise ConfigEntryAuthFailed(f"AquaTrax sign-in failed: {err}") from err
    except AquaTraxConnectionError as err:
        raise ConfigEntryNotReady(f"Could not reach AquaTrax: {err}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an AquaTrax config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
