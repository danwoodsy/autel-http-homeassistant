"""Test installed entities, commands, availability and cadence in Home Assistant."""

import asyncio
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.autel_http.const import DOMAIN
from custom_components.autel_http.diagnostics import async_get_config_entry_diagnostics

from .conftest import SERIAL


@pytest.fixture
async def loaded(hass, charger, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED
    return entry


def entity_id(hass, platform, key):
    result = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{SERIAL}_{key}")
    assert result is not None
    return result


def state(hass, platform, key):
    result = hass.states.get(entity_id(hass, platform, key))
    assert result is not None
    return result


async def test_entities_and_units(hass, loaded):
    assert state(hass, "binary_sensor", "charging").state == "on"
    assert state(hass, "binary_sensor", "vehicle_connected").state == "on"
    assert state(hass, "binary_sensor", "autostart").state == "on"
    assert state(hass, "sensor", "status").state == "charging"
    assert float(state(hass, "sensor", "power").state) == 3.848
    assert state(hass, "sensor", "power").attributes["unit_of_measurement"] == "kW"
    assert float(state(hass, "sensor", "current").state) == pytest.approx(16.165)
    assert float(state(hass, "sensor", "voltage").state) == pytest.approx(238.2)
    assert float(state(hass, "sensor", "session_energy").state) == pytest.approx(0.148)
    assert float(state(hass, "sensor", "meter_energy").state) == pytest.approx(4.757)
    assert state(hass, "sensor", "session_duration").state == "152.0"
    assert "state_class" not in state(hass, "sensor", "meter_energy").attributes
    number = state(hass, "number", "current_limit")
    assert float(number.state) == 16
    assert number.attributes["min"] == 6
    assert number.attributes["max"] == 32
    assert number.attributes["mode"] == "box"
    registry = er.async_get(hass)
    current_entry = registry.async_get(entity_id(hass, "number", "current_limit"))
    assert current_entry.entity_category is EntityCategory.CONFIG
    for key in ("start_charging", "stop_charging"):
        button = registry.async_get(entity_id(hass, "button", key))
        assert button.entity_category is None
        assert button.disabled_by is None
    phase = registry.async_get(entity_id(hass, "sensor", "phase_b_current"))
    assert phase.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert phase.entity_category is EntityCategory.DIAGNOSTIC
    assert "pin" not in str(number.attributes)
    assert "token" not in str(number.attributes)


async def test_stop_readback_keeps_vehicle_connected(hass, loaded, charger):
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "stop_charging")},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert state(hass, "binary_sensor", "charging").state == "off"
    assert state(hass, "sensor", "status").state == "completed"
    assert state(hass, "binary_sensor", "vehicle_connected").state == "on"
    assert float(state(hass, "sensor", "power").state) == 0
    controls = [c for c in charger.calls if c["cmd"] == "debug_ctrl_pile_charge"]
    assert len(controls) == 1
    assert controls[0]["data"]["op"] == 2


async def test_start_and_current_readback(hass, loaded, charger, freezer):
    charger.telemetry.update(if_work_st=5, power=0)
    charger.controller["CPState"] = 2
    await loaded.runtime_data.coordinator.async_refresh()
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "start_charging")},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert state(hass, "binary_sensor", "charging").state == "on"
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_id(hass, "number", "current_limit"), "value": 10},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert float(state(hass, "number", "current_limit").state) == 10


async def test_control_failure_does_not_change_state_or_retry(hass, loaded, charger):
    charger.overrides["debug_ctrl_pile_charge"] = [TimeoutError()]
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id(hass, "button", "stop_charging")},
            blocking=True,
        )
    assert state(hass, "binary_sensor", "charging").state == "on"
    assert sum(c["cmd"] == "debug_ctrl_pile_charge" for c in charger.calls) == 1


async def test_status_and_detail_cadence(hass, loaded, charger):
    coordinator = loaded.runtime_data.coordinator
    assert coordinator.update_interval == timedelta(seconds=30)
    assert len(charger.calls) == 8  # login + identity + six read-only poll requests
    charger.calls.clear()
    with patch("custom_components.autel_http.coordinator.monotonic", return_value=100):
        coordinator._last_details_attempt = 90
        await coordinator.async_refresh()
    assert len(charger.calls) == 3
    assert [c["cmd"] for c in charger.calls] == [
        "get_realtime_data",
        "get_realtime_data",
        "get_param_value",
    ]
    charger.calls.clear()
    with patch("custom_components.autel_http.coordinator.monotonic", return_value=211):
        await coordinator.async_refresh()
    assert len(charger.calls) == 6
    assert charger.calls[3]["data"]["rtcode"] == 2561
    charger.calls.clear()
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "refresh")},
        blocking=True,
    )
    assert len(charger.calls) == 6


async def test_normal_poll_timer_uses_configured_interval(
    hass, charger, entry, freezer
):
    hass.config_entries.async_update_entry(
        entry,
        options={"status_interval": 60, "details_interval": 300, "request_timeout": 20},
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    coordinator = entry.runtime_data.coordinator
    assert coordinator.update_interval == timedelta(seconds=60)
    charger.calls.clear()
    freezer.tick(timedelta(seconds=45))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert charger.calls == []
    freezer.tick(timedelta(seconds=16))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(charger.calls) == 3


async def test_optional_failure_preserves_normal_sensors(hass, loaded, charger):
    charger.overrides["get_realtime_data"] = [
        # Let the two normal reads succeed with their actual snapshots, then fail
        # just the optional CCU measurement read.
        {
            "cmd": "get_realtime_data",
            "success": "1",
            "errcode": "0",
            "data": {"value": [charger.telemetry]},
        },
        {
            "cmd": "get_realtime_data",
            "success": "1",
            "errcode": "0",
            "data": {"value": charger.controller},
        },
        TimeoutError(),
    ]
    await loaded.runtime_data.coordinator.async_refresh_all()
    assert state(hass, "sensor", "meter_energy").state == "unavailable"
    assert state(hass, "sensor", "power").state == "3.848"
    assert state(hass, "binary_sensor", "vehicle_connected").state == "on"
    assert state(hass, "binary_sensor", "autostart").state == "on"


async def test_primary_failure_and_recovery(hass, loaded, charger):
    charger.overrides["get_realtime_data"] = [TimeoutError()]
    await loaded.runtime_data.coordinator.async_refresh()
    assert state(hass, "sensor", "power").state == "unavailable"
    assert state(hass, "binary_sensor", "charging").state == "unavailable"
    assert state(hass, "button", "refresh").state != "unavailable"
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "refresh")},
        blocking=True,
    )
    assert state(hass, "sensor", "power").state == "3.848"


@pytest.mark.parametrize(
    ("pilot", "connected"), [(1, "off"), (2, "on"), (3, "on"), (99, "unknown")]
)
async def test_connection_independent_of_charging(
    hass, loaded, charger, pilot, connected
):
    charger.telemetry.update(if_work_st=0, power=0, meter_current=0)
    charger.controller["CPState"] = pilot
    await loaded.runtime_data.coordinator.async_refresh()
    assert state(hass, "binary_sensor", "vehicle_connected").state == connected
    assert state(hass, "binary_sensor", "charging").state == "off"


async def test_unknown_state_and_bad_measurement(hass, loaded, charger):
    charger.telemetry.update(if_work_st=99, meter_current="not a number")
    await loaded.runtime_data.coordinator.async_refresh()
    assert state(hass, "sensor", "status").state == "unknown"
    assert state(hass, "binary_sensor", "charging").state == "unknown"
    assert state(hass, "sensor", "current").state == "unknown"


async def test_offline_limit_caps_number(hass, loaded, charger):
    charger.current["offlineCurr"] = "20"
    await loaded.runtime_data.coordinator.async_refresh()
    assert state(hass, "number", "current_limit").attributes["max"] == 20
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id(hass, "number", "current_limit"), "value": 21},
            blocking=True,
        )
    assert not any(c["cmd"] == "set_param_value" for c in charger.calls)


async def test_unload_cancels_polling_and_preserves_shared_session(
    hass, loaded, charger, freezer
):
    client = loaded.runtime_data.client
    assert await hass.config_entries.async_unload(loaded.entry_id)
    assert client._token is None
    assert not client._session.closed
    charger.calls.clear()
    freezer.tick(timedelta(seconds=360))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert charger.calls == []


async def test_rejected_credentials_start_reauth(hass, loaded, charger):
    rejection = {
        "cmd": "get_realtime_data",
        "data": "",
        "errcode": "1001",
        "success": "-1",
    }
    charger.overrides["get_realtime_data"] = [rejection, rejection]
    with patch.object(loaded, "async_start_reauth") as reauth:
        await loaded.runtime_data.coordinator.async_refresh()
        reauth.assert_called_once()
    assert state(hass, "sensor", "power").state == "unavailable"


async def test_control_returns_without_waiting_for_slow_status(hass, loaded):
    client = loaded.runtime_data.client
    reading_started = asyncio.Event()
    release = asyncio.Event()
    original = client.realtime

    async def slow_read(*args):
        reading_started.set()
        await release.wait()
        return await original(*args)

    with patch.object(client, "realtime", side_effect=slow_read):
        try:
            await asyncio.wait_for(
                hass.services.async_call(
                    "button",
                    "press",
                    {"entity_id": entity_id(hass, "button", "stop_charging")},
                    blocking=True,
                ),
                timeout=1,
            )
            await reading_started.wait()
            # An ACK alone must not flip the sensor, even though the service
            # has already returned while its readback is blocked.
            assert state(hass, "binary_sensor", "charging").state == "on"
        finally:
            release.set()
        await hass.async_block_till_done(wait_background_tasks=True)
    assert state(hass, "binary_sensor", "charging").state == "off"


async def test_polling_yields_to_a_pending_control(hass, loaded, charger):
    coordinator = loaded.runtime_data.coordinator
    client = loaded.runtime_data.client
    started = asyncio.Event()
    release = asyncio.Event()
    original = client._post
    blocked = False

    async def slow_post(payload):
        nonlocal blocked
        if not blocked and payload["cmd"] == "get_realtime_data":
            blocked = True
            started.set()
            await release.wait()
        return await original(payload)

    charger.calls.clear()
    with patch.object(client, "_post", side_effect=slow_post):
        refresh = asyncio.create_task(coordinator.async_refresh())
        await started.wait()
        control = asyncio.create_task(client.set_current(10, 32))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(refresh, control)
    assert [c["cmd"] for c in charger.calls] == [
        "get_realtime_data",
        "set_param_value",
        "get_realtime_data",
        "get_param_value",
    ]


async def test_download_diagnostics_is_cached_and_omits_credentials(
    hass, loaded, charger
):
    data = loaded.runtime_data.coordinator.data
    data.telemetry["token"] = "sensitive-token"
    data.telemetry["pin"] = "sensitive-pin"
    data.measurements["sn"] = SERIAL
    count = len(charger.calls)
    diagnostics = await async_get_config_entry_diagnostics(hass, loaded)
    assert len(charger.calls) == count
    assert diagnostics["device"]["model"] == "EW07-C050000A002"
    assert diagnostics["readings"]["telemetry"]["power"] == 3848
    serialized = json.dumps(diagnostics)
    for forbidden in (
        "sensitive-token",
        "sensitive-pin",
        SERIAL,
        "192.0.2.27",
        "admin",
        '"pin"',
        '"token"',
        '"username"',
    ):
        assert forbidden not in serialized


async def test_unload_cancels_a_pending_control_readback(hass, loaded):
    started = asyncio.Event()
    canceled = asyncio.Event()
    never = asyncio.Event()

    async def blocked_read(*args):
        started.set()
        try:
            await never.wait()
        except asyncio.CancelledError:
            canceled.set()
            raise

    with patch.object(loaded.runtime_data.client, "realtime", side_effect=blocked_read):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id(hass, "button", "stop_charging")},
            blocking=True,
        )
        await started.wait()
        assert await hass.config_entries.async_unload(loaded.entry_id)
        assert canceled.is_set()


async def test_automatic_polling_can_be_disabled(hass, charger, entry, freezer):
    hass.config_entries.async_update_entry(entry, pref_disable_polling=True)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    charger.calls.clear()
    freezer.tick(timedelta(seconds=600))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert charger.calls == []
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "refresh")},
        blocking=True,
    )
    assert len(charger.calls) == 6
