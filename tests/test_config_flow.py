"""Exercise real HA setup, duplicate prevention, options, and credential changes."""

from unittest.mock import AsyncMock, patch

import probatio
import pytest
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    SOURCE_USER,
)
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.selector import NumberSelector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.autel_http.const import DOMAIN
from custom_components.autel_http.polling import polling_settings

from .conftest import CONFIG, SERIAL


@pytest.fixture(autouse=True)
def skip_runtime_setup():
    # Runtime and platforms are tested separately; flows must remain read-only.
    with patch(
        "custom_components.autel_http.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        yield


async def test_setup_and_deduplication(hass, charger):
    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert form["type"] == FlowResultType.FORM
    assert form["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], CONFIG.copy()
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERIAL
    assert result["data"] == CONFIG
    assert "token" not in result["data"]
    assert [c["cmd"] for c in charger.calls] == [
        "account_login",
        "get_baseinfo",
        "get_param_value",
    ]
    await hass.async_block_till_done()
    duplicate = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=CONFIG.copy()
    )
    assert duplicate["type"] == FlowResultType.ABORT
    assert duplicate["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("auth", "invalid_auth"),
        ("timeout", "cannot_connect"),
        ("unsupported", "unsupported_charger"),
        ("bad_response", "invalid_response"),
        ("bad_host", "invalid_host"),
    ],
)
async def test_setup_failures(hass, charger, scenario, expected):
    config = CONFIG.copy()
    if scenario == "auth":
        charger.overrides["account_login"] = [
            {"cmd": "account_login", "errcode": "1003", "success": "0"}
        ]
    elif scenario == "timeout":
        charger.overrides["account_login"] = [TimeoutError()]
    elif scenario == "unsupported":
        charger.base["AC"]["connectors"] = []
    elif scenario == "bad_response":
        charger.overrides["get_baseinfo"] = [
            {"cmd": "get_baseinfo", "data": {}, "errcode": "0", "success": "1"}
        ]
    elif scenario == "bad_host":
        config["host"] = "http://charger.local"
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=config
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_options_validation_and_save(hass, entry):
    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["type"] == FlowResultType.FORM
    timeout_selector = next(
        value
        for key, value in form["data_schema"].schema.items()
        if key.schema == "request_timeout"
    )
    assert isinstance(timeout_selector, NumberSelector)
    assert timeout_selector.config["mode"] == "box"
    assert form["data_schema"]({}) == {
        "polling_preset": "medium",
        "request_timeout": 15,
    }
    with pytest.raises(probatio.Invalid):
        form["data_schema"]({"polling_preset": "invalid"})
    with pytest.raises(probatio.Invalid):
        form["data_schema"]({"request_timeout": 0})
    with pytest.raises(probatio.Invalid):
        form["data_schema"]({"request_timeout": 61})
    custom = await hass.config_entries.options.async_configure(
        form["flow_id"], {"polling_preset": "custom", "request_timeout": 20}
    )
    assert custom["step_id"] == "custom"
    data = {
        "unplugged_interval": 20,
        "unplugged_status_interval": 120,
        "unplugged_details_interval": 300,
        "charging_interval": 10,
        "status_interval": 60,
        "details_interval": 30,
    }
    bad = await hass.config_entries.options.async_configure(custom["flow_id"], data)
    assert bad["errors"] == {"details_interval": "details_too_fast"}
    with pytest.raises(probatio.Invalid):
        bad["data_schema"]({**data, "status_interval": 1})
    with pytest.raises(probatio.Invalid):
        bad["data_schema"]({**data, "charging_interval": 4})
    slow_charging = await hass.config_entries.options.async_configure(
        bad["flow_id"], {**data, "details_interval": 300, "charging_interval": 61}
    )
    assert slow_charging["errors"] == {"charging_interval": "charging_too_slow"}
    too_fast = await hass.config_entries.options.async_configure(
        bad["flow_id"],
        {**data, "details_interval": 300, "unplugged_status_interval": 10},
    )
    assert too_fast["errors"] == {
        "unplugged_status_interval": "unplugged_status_too_fast"
    }
    too_fast = await hass.config_entries.options.async_configure(
        bad["flow_id"],
        {**data, "details_interval": 300, "unplugged_status_interval": 400},
    )
    assert too_fast["errors"] == {
        "unplugged_details_interval": "unplugged_details_too_fast"
    }
    good = {**data, "details_interval": 300, "charging_interval": 5}
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await hass.config_entries.options.async_configure(bad["flow_id"], good)
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert entry.options == {
            **good,
            "polling_preset": "custom",
            "request_timeout": 20,
        }
        reload.assert_called_once_with(entry.entry_id)


async def test_options_preserve_existing_idle_interval(hass, entry):
    hass.config_entries.async_update_entry(
        entry, options={"status_interval": 30, "details_interval": 300}
    )
    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["data_schema"]({})["polling_preset"] == "custom"
    custom = await hass.config_entries.options.async_configure(
        form["flow_id"], {"polling_preset": "custom", "request_timeout": 15}
    )
    defaults = custom["data_schema"]({})
    assert defaults["status_interval"] == 30
    assert defaults["details_interval"] == 300
    assert defaults["charging_interval"] == 10
    assert defaults["unplugged_interval"] == 20
    assert defaults["unplugged_status_interval"] == 120
    assert defaults["unplugged_details_interval"] == 300
    assert polling_settings(entry.options).status_interval == 30


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("high", (10, 60, 150, 10, 5, 60)),
        ("medium", (20, 120, 300, 20, 10, 120)),
        ("low", (30, 240, 600, 40, 20, 240)),
    ],
)
async def test_polling_presets_save_without_exposing_custom_fields(
    hass, entry, preset, expected
):
    form = await hass.config_entries.options.async_init(entry.entry_id)
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await hass.config_entries.options.async_configure(
            form["flow_id"], {"polling_preset": preset, "request_timeout": 20}
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    polling = polling_settings(entry.options)
    assert (
        polling.unplugged_interval,
        polling.unplugged_status_interval,
        polling.unplugged_details_interval,
        polling.status_interval,
        polling.charging_interval,
        polling.details_interval,
    ) == expected


async def test_reconfigure_preserves_pin(hass, entry, charger):
    form = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"],
            {
                "host": CONFIG["host"],
                "username": "admin",
                "verify_ssl": True,
                "pin": "",
            },
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["pin"] == CONFIG["pin"]
    assert entry.data["verify_ssl"] is True


async def test_reconfigure_does_not_replace_device(hass, entry, charger):
    charger.base["sn"] = "OTHER-CHARGER"
    # Validation must still return its discovered identity before checking the
    # mismatch. Do not emulate parameter access to our original device instead.
    with patch(
        "custom_components.autel_http.config_flow.validate_connection",
        return_value=type("Info", (), {"serial": "OTHER-CHARGER"})(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
            data=CONFIG.copy(),
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert entry.unique_id == SERIAL


async def test_reauth(hass, charger):
    bad_config = {**CONFIG, "pin": "wrong-pin"}
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data=bad_config)
    entry.add_to_hass(hass)
    form = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert form["step_id"] == "reauth_confirm"
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], {"username": "admin", "pin": CONFIG["pin"]}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["pin"] == CONFIG["pin"]
