"""Autel Charger HTTPS integration."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AutelClient
from .const import (
    CONF_DETAILS_INTERVAL,
    CONF_PIN,
    CONF_REQUEST_TIMEOUT,
    CONF_STATUS_INTERVAL,
    DEFAULT_DETAILS_INTERVAL,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_STATUS_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import AutelCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class AutelRuntimeData:
    client: AutelClient
    coordinator: AutelCoordinator


type AutelConfigEntry = ConfigEntry[AutelRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: AutelConfigEntry) -> bool:
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, False)
    client = AutelClient(
        async_get_clientsession(hass, verify_ssl=verify_ssl),
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PIN],
        verify_ssl=verify_ssl,
        timeout=entry.options.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT),
    )
    coordinator = AutelCoordinator(
        hass,
        entry,
        client,
        entry.options.get(CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL),
        entry.options.get(CONF_DETAILS_INTERVAL, DEFAULT_DETAILS_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = AutelRuntimeData(client, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AutelConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data.client.clear_token()
    return unloaded
