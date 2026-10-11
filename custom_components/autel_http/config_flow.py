"""Configure the local HTTPS address, credentials, and polling cadence."""

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

import probatio
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    AutelAuthError,
    AutelClient,
    AutelConnectionError,
    AutelProtocolError,
    ChargerInfo,
    UnsupportedCharger,
    normalize_host,
)
from .const import (
    CONF_CHARGING_INTERVAL,
    CONF_DETAILS_INTERVAL,
    CONF_PIN,
    CONF_POLLING_PRESET,
    CONF_REQUEST_TIMEOUT,
    CONF_STATUS_INTERVAL,
    CONF_UNPLUGGED_DETAILS_INTERVAL,
    CONF_UNPLUGGED_INTERVAL,
    CONF_UNPLUGGED_STATUS_INTERVAL,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
    MIN_CHARGING_INTERVAL,
    MIN_STATUS_INTERVAL,
)
from .coordinator import connector_record
from .polling import PRESETS, polling_preset, polling_settings


def connection_schema(defaults: Mapping[str, Any], *, reuse_pin: bool = False):
    schema = {
        probatio.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
        probatio.Required(
            CONF_USERNAME, default=defaults.get(CONF_USERNAME, "admin")
        ): str,
        probatio.Optional(
            CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, False)
        ): bool,
    }
    pin_key = probatio.Optional(CONF_PIN) if reuse_pin else probatio.Required(CONF_PIN)
    schema[pin_key] = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
    return probatio.Schema(schema)


async def validate_connection(hass: HomeAssistant, data: dict) -> ChargerInfo:
    """Log in and check read-only discovery/current data; never actuate."""
    data[CONF_HOST] = normalize_host(data[CONF_HOST])
    if not data[CONF_USERNAME].strip() or not data[CONF_PIN]:
        raise AutelAuthError("Username and PIN are required")
    verify = data.get(CONF_VERIFY_SSL, False)
    client = AutelClient(
        async_get_clientsession(hass, verify_ssl=verify),
        data[CONF_HOST],
        data[CONF_USERNAME],
        data[CONF_PIN],
        verify_ssl=verify,
    )
    try:
        info = await client.discover()
        connector_record(await client.parameters(5), "connectorId")
        return info
    finally:
        client.clear_token()


def error_key(error: Exception) -> str:
    if isinstance(error, AutelAuthError):
        return "invalid_auth"
    if isinstance(error, AutelConnectionError):
        return "cannot_connect"
    if isinstance(error, UnsupportedCharger):
        return "unsupported_charger"
    if isinstance(error, ValueError):
        return "invalid_host"
    return "invalid_response"


CONNECTION_ERRORS = (
    AutelAuthError,
    AutelConnectionError,
    AutelProtocolError,
    UnsupportedCharger,
    ValueError,
)


class AutelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return AutelOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                info = await validate_connection(self.hass, user_input)
            except CONNECTION_ERRORS as err:
                errors["base"] = error_key(err)
            else:
                await self.async_set_unique_id(info.serial)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Autel {info.serial}", data=user_input
                )
        return self.async_show_form(
            step_id="user",
            data_schema=connection_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                info = await validate_connection(self.hass, data)
            except CONNECTION_ERRORS as err:
                errors["base"] = error_key(err)
            else:
                await self.async_set_unique_id(info.serial)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_USERNAME, default=entry.data[CONF_USERNAME]
                    ): str,
                    probatio.Required(CONF_PIN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            if not user_input.get(CONF_PIN):
                data[CONF_PIN] = entry.data[CONF_PIN]
            try:
                info = await validate_connection(self.hass, data)
            except CONNECTION_ERRORS as err:
                errors["base"] = error_key(err)
            else:
                await self.async_set_unique_id(info.serial)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=connection_schema(entry.data, reuse_pin=True),
            errors=errors,
        )


class AutelOptionsFlow(config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            if user_input[CONF_POLLING_PRESET] == "custom":
                self._request_timeout = int(user_input[CONF_REQUEST_TIMEOUT])
                return await self.async_step_custom()
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_POLLING_PRESET,
                        default=polling_preset(self.config_entry.options),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[*PRESETS, "custom"],
                            translation_key="polling_preset",
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    probatio.Required(
                        CONF_REQUEST_TIMEOUT,
                        default=self.config_entry.options.get(
                            CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT
                        ),
                    ): self._seconds_selector(5, 60),
                }
            ),
        )

    @staticmethod
    def _seconds_selector(minimum: int, maximum: int) -> NumberSelector:
        return NumberSelector(
            NumberSelectorConfig(
                min=minimum,
                max=maximum,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="s",
            )
        )

    async def async_step_custom(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input[CONF_CHARGING_INTERVAL] > user_input[CONF_STATUS_INTERVAL]:
                errors[CONF_CHARGING_INTERVAL] = "charging_too_slow"
            elif user_input[CONF_DETAILS_INTERVAL] < user_input[CONF_STATUS_INTERVAL]:
                errors[CONF_DETAILS_INTERVAL] = "details_too_fast"
            elif (
                user_input[CONF_UNPLUGGED_STATUS_INTERVAL]
                < user_input[CONF_UNPLUGGED_INTERVAL]
            ):
                errors[CONF_UNPLUGGED_STATUS_INTERVAL] = "unplugged_status_too_fast"
            elif (
                user_input[CONF_UNPLUGGED_DETAILS_INTERVAL]
                < user_input[CONF_UNPLUGGED_STATUS_INTERVAL]
            ):
                errors[CONF_UNPLUGGED_DETAILS_INTERVAL] = "unplugged_details_too_fast"
            else:
                return self.async_create_entry(
                    data={
                        **user_input,
                        CONF_POLLING_PRESET: "custom",
                        CONF_REQUEST_TIMEOUT: self._request_timeout,
                    }
                )
        defaults = user_input or asdict(polling_settings(self.config_entry.options))
        limits = {
            CONF_UNPLUGGED_INTERVAL: (MIN_STATUS_INTERVAL, 3600),
            CONF_UNPLUGGED_STATUS_INTERVAL: (MIN_STATUS_INTERVAL, 86400),
            CONF_UNPLUGGED_DETAILS_INTERVAL: (MIN_STATUS_INTERVAL, 86400),
            CONF_STATUS_INTERVAL: (MIN_STATUS_INTERVAL, 3600),
            CONF_CHARGING_INTERVAL: (MIN_CHARGING_INTERVAL, 3600),
            CONF_DETAILS_INTERVAL: (MIN_STATUS_INTERVAL, 86400),
        }
        return self.async_show_form(
            step_id="custom",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        key, default=defaults[key]
                    ): self._seconds_selector(minimum, maximum)
                    for key, (minimum, maximum) in limits.items()
                }
            ),
            errors=errors,
        )
