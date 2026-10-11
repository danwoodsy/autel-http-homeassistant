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

from custom_components.autel_http.api import AutelConnectionError
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


async def test_visible_system_and_signal_diagnostics(hass, loaded):
    registry = er.async_get(hass)
    for key, expected in (("cpu_usage", 65), ("memory_usage", 37), ("flash_usage", 3)):
        reading = state(hass, "sensor", key)
        assert float(reading.state) == expected
        assert reading.attributes["unit_of_measurement"] == "%"
        assert reading.attributes["state_class"] == "measurement"
        registered = registry.async_get(entity_id(hass, "sensor", key))
        assert registered.entity_category is EntityCategory.DIAGNOSTIC
        assert registered.disabled_by is None
    signal = state(hass, "sensor", "network_signal_level")
    assert float(signal.state) == 4
    assert "unit_of_measurement" not in signal.attributes
    assert (
        registry.async_get(signal.entity_id).entity_category
        is EntityCategory.DIAGNOSTIC
    )


@pytest.mark.parametrize(
    ("previous_disabler", "expected_disabler"),
    [
        (er.RegistryEntryDisabler.INTEGRATION, None),
        (er.RegistryEntryDisabler.USER, er.RegistryEntryDisabler.USER),
    ],
)
async def test_existing_signal_visibility(
    hass, entry, charger, previous_disabler, expected_disabler
):
    registry = er.async_get(hass)
    registered = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{SERIAL}_network_signal_level",
        config_entry=entry,
        disabled_by=previous_disabler,
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert registry.async_get(registered.entity_id).disabled_by is expected_disabler
    if expected_disabler is None:
        assert float(hass.states.get(registered.entity_id).state) == 4


async def test_system_failure_isolated_and_recovers_on_detailed_refresh(
    hass, loaded, charger
):
    client = loaded.runtime_data.client
    coordinator = loaded.runtime_data.coordinator
    original = client.realtime

    async def fail_system(code, node=10):
        if code == 1536:
            raise AutelConnectionError("System read timed out")
        return await original(code, node)

    with patch.object(client, "realtime", side_effect=fail_system):
        await coordinator.async_refresh_all()
    assert state(hass, "sensor", "cpu_usage").state == "unavailable"
    assert state(hass, "sensor", "memory_usage").state == "unavailable"
    assert state(hass, "sensor", "flash_usage").state == "unavailable"
    assert state(hass, "sensor", "power").state == "3.848"
    assert float(state(hass, "sensor", "network_signal_level").state) == 4
    charger.system["CpuState"] = 42
    charger.calls.clear()
    await coordinator.async_refresh()
    assert not any(c.get("data", {}).get("rtcode") == 1536 for c in charger.calls)
    assert state(hass, "sensor", "cpu_usage").state == "unavailable"
    await coordinator.async_refresh_all()
    assert float(state(hass, "sensor", "cpu_usage").state) == 42


async def test_missing_system_field_is_unknown(hass, loaded, charger):
    charger.system.pop("MemState")
    await loaded.runtime_data.coordinator.async_refresh_all()
    assert state(hass, "sensor", "memory_usage").state == "unknown"
    assert float(state(hass, "sensor", "cpu_usage").state) == 65


async def test_current_readback_failure_isolated_until_detailed_refresh(
    hass, loaded, charger
):
    coordinator = loaded.runtime_data.coordinator
    charger.overrides["get_param_value"] = [TimeoutError()]
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_id(hass, "number", "current_limit"), "value": 10},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert state(hass, "number", "current_limit").state == "unavailable"
    assert state(hass, "sensor", "power").state == "3.848"
    assert state(hass, "binary_sensor", "charging").state == "on"
    charger.calls.clear()
    await coordinator.async_refresh()
    assert len(charger.calls) == 2
    assert state(hass, "number", "current_limit").state == "unavailable"
    await coordinator.async_refresh_all()
    assert float(state(hass, "number", "current_limit").state) == 10


async def test_external_current_limit_change_uses_detailed_cadence(
    hass, loaded, charger
):
    charger.current["maxCurr"] = 12
    await loaded.runtime_data.coordinator.async_refresh()
    assert float(state(hass, "number", "current_limit").state) == 16
    await loaded.runtime_data.coordinator.async_refresh_all()
    assert float(state(hass, "number", "current_limit").state) == 12


async def test_request_counter_updates_locally_with_polling_disabled(
    hass, charger, entry, freezer
):
    hass.config_entries.async_update_entry(entry, pref_disable_polling=True)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    counter = state(hass, "sensor", "http_requests_per_minute")
    assert int(counter.state) == 9
    assert counter.attributes["unit_of_measurement"] == "requests/min"
    count = len(charger.calls)
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert state(hass, "sensor", "http_requests_per_minute").state == "0"
    assert len(charger.calls) == count
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(counter.entity_id).state == "unavailable"
    assert len(charger.calls) == count


async def test_request_counter_updates_when_charger_readings_do_not_change(
    hass, loaded, charger
):
    assert state(hass, "sensor", "http_requests_per_minute").state == "9"
    await loaded.runtime_data.coordinator.async_refresh()
    assert len(charger.calls) == 11
    assert state(hass, "sensor", "http_requests_per_minute").state == "11"


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
    assert loaded.runtime_data.coordinator.update_interval == timedelta(seconds=60)
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
    assert loaded.runtime_data.coordinator.update_interval == timedelta(seconds=10)
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    charger.calls.clear()
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_id(hass, "number", "current_limit"), "value": 10},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert float(state(hass, "number", "current_limit").state) == 10
    assert [c["cmd"] for c in charger.calls] == [
        "set_param_value",
        "get_realtime_data",
        "get_realtime_data",
        "get_param_value",
    ]
    assert charger.calls[-1]["data"]["list"] == [5]


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
    assert coordinator.update_interval == timedelta(seconds=10)
    assert coordinator.status_interval == 60
    assert len(charger.calls) == 9  # login + identity + seven read-only poll requests
    charger.calls.clear()
    with patch("custom_components.autel_http.coordinator.monotonic", return_value=100):
        coordinator._last_details_attempt = 90
        await coordinator.async_refresh()
    assert len(charger.calls) == 2
    assert [c["cmd"] for c in charger.calls] == [
        "get_realtime_data",
        "get_realtime_data",
    ]
    assert [c["data"]["rtcode"] for c in charger.calls] == [1537, 2560]
    charger.calls.clear()
    with patch("custom_components.autel_http.coordinator.monotonic", return_value=211):
        await coordinator.async_refresh()
    assert len(charger.calls) == 7
    assert charger.calls[3]["data"]["rtcode"] == 2561
    assert charger.calls[6]["data"] == {
        "sn": SERIAL,
        "nodeid": 10,
        "rtcode": 1536,
    }
    charger.calls.clear()
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "refresh")},
        blocking=True,
    )
    assert len(charger.calls) == 7


@pytest.mark.parametrize("charging_interval", [5, 10, 15])
async def test_poll_timer_switches_between_idle_and_charging(
    hass, charger, entry, freezer, charging_interval
):
    charger.telemetry.update(if_work_st=5, power=0)
    charger.controller["CPState"] = 2
    hass.config_entries.async_update_entry(
        entry,
        options={
            "status_interval": 60,
            "charging_interval": charging_interval,
            "details_interval": 300,
            "request_timeout": 20,
        },
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
    charger.telemetry.update(if_work_st=2, power=3848)
    charger.controller["CPState"] = 3
    freezer.tick(timedelta(seconds=16))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(charger.calls) == 2
    assert coordinator.update_interval == timedelta(seconds=charging_interval)
    assert state(hass, "binary_sensor", "charging").state == "on"
    charger.calls.clear()
    freezer.tick(timedelta(seconds=charging_interval - 2))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert charger.calls == []
    charger.telemetry.update(if_work_st=5, power=0)
    charger.controller["CPState"] = 2
    freezer.tick(timedelta(seconds=3))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(charger.calls) == 2
    assert coordinator.update_interval == timedelta(seconds=60)
    assert state(hass, "binary_sensor", "vehicle_connected").state == "on"
    charger.calls.clear()
    freezer.tick(timedelta(seconds=45))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert charger.calls == []


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
    assert int(state(hass, "sensor", "http_requests_per_minute").state) == 10
    assert state(hass, "button", "refresh").state != "unavailable"
    assert loaded.runtime_data.coordinator.update_interval == timedelta(seconds=60)
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "refresh")},
        blocking=True,
    )
    assert state(hass, "sensor", "power").state == "3.848"
    assert loaded.runtime_data.coordinator.update_interval == timedelta(seconds=10)


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
    await loaded.runtime_data.coordinator.async_refresh_all()
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
    ]


async def test_download_diagnostics_is_cached_and_omits_credentials(
    hass, loaded, charger
):
    data = loaded.runtime_data.coordinator.data
    data.telemetry["token"] = "sensitive-token"
    data.telemetry["pin"] = "sensitive-pin"
    data.measurements["sn"] = SERIAL
    data.system["token"] = "sensitive-token"
    data.system["pin"] = "sensitive-pin"
    count = len(charger.calls)
    diagnostics = await async_get_config_entry_diagnostics(hass, loaded)
    assert len(charger.calls) == count
    assert diagnostics["device"]["model"] == "EW07-C050000A002"
    assert diagnostics["readings"]["telemetry"]["power"] == 3848
    assert diagnostics["readings"]["system"]["CpuState"] == 65
    assert diagnostics["readings"]["system"]["OcppState"] == 0
    assert diagnostics["polling"]["status_interval"] == 60
    assert diagnostics["polling"]["charging_interval"] == 10
    assert diagnostics["polling"]["active_interval"] == 10
    assert diagnostics["http"]["requests_last_minute"] == 9
    assert diagnostics["http"]["last_request_duration"] >= 0
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
    assert len(charger.calls) == 7
