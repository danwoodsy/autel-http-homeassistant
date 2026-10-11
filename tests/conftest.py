"""Run the actual Home Assistant runtime against captured, sanitized schemas."""

from copy import deepcopy

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

from custom_components.autel_http.const import DOMAIN

HOST = "192.0.2.27"
URL = f"https://{HOST}/localcfg"
SERIAL = "TEST-CHARGER-001"
TEST_PIN = "1234"
PIN_HASH = "03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4"
CONFIG = {"host": HOST, "username": "admin", "pin": TEST_PIN, "verify_ssl": False}


@pytest.fixture(autouse=True)
def enable_integration(enable_custom_integrations):
    """Allow loading custom_components in the real HA test runtime."""


class FakeCharger:
    """Emulate only the confirmed HTTP commands; no unknown command fallback."""

    def __init__(self):
        self.calls = []
        self.login_count = 0
        self.token = ""
        self.overrides = {}
        self.ack = 0
        self.base = {
            "sn": SERIAL,
            "device_model": "EW07-C050000A002",
            "number_of_phases": 3,
            "AC": {"connectors": [{"connector_id": 1, "ratedcur": 32.0}]},
            "versions": {"bigVersion": "V1.05.38"},
        }
        self.telemetry = {
            "gun_no": 1,
            "if_work_st": 2,
            "power": 3848,
            "meter_current": 16.165000915527344,
            "meter_voltage": 238.19999694824219,
            "energy": 148,
            "haveChargedTime": 152,
            "meter_F_energy": 47570,
            "meter_R_energy": 46090,
        }
        self.controller = {
            "CPState": 3,
            "ConnectCar": 0,
            "EVSEState": 5,
            "WorkState": 1,
            "RelayState1": 1,
            "RelayState2": 1,
        }
        self.measurements = {
            "MeterValue": 4.756999969482422,
            "ChargePower": 3848,
            "CurrentA": 16.165000915527344,
            "CurrentB": 0.0,
            "CurrentC": 0.0,
            "GridNum": 1,
            "RateCurrent": 32,
            "CpDutyCycle": 26,
            "CpVolt": 5.730000019073486,
        }
        self.current = {"connectorId": 1, "maxCurr": 16.0, "offlineCurr": "32"}
        self.permissions = {"CustomizedPnC": 2}

    async def handle(self, method, url, payload):
        self.calls.append(deepcopy(payload))
        command = payload["cmd"]
        if override := self.overrides.get(command):
            outcome = override.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return AiohttpClientMockResponse(method, url, json=outcome)
        if command == "account_login":
            assert payload == {
                "cmd": command,
                "data": {"account": "admin", "password": PIN_HASH},
            }
            self.login_count += 1
            self.token = f"issued-token-{self.login_count}"
            data = {"role": "admin", "token": self.token}
        else:
            assert payload["token"] == self.token
            match command:
                case "get_baseinfo":
                    data = self.base
                case "get_current_network":
                    assert "data" not in payload
                    data = {"networkType": 4, "signalLevel": 4}
                case "get_param_value":
                    args = payload["data"]
                    assert args["sn"] == SERIAL
                    assert args["nodeid"] == 10
                    code = args["list"][0]
                    assert code in (4, 5)
                    value = [self.current] if code == 5 else self.permissions
                    data = {
                        "sn": SERIAL,
                        "nodeid": 10,
                        "list": [{"code": code, "value": value}],
                    }
                case "get_realtime_data":
                    args = payload["data"]
                    assert args["sn"] == SERIAL
                    code = args["rtcode"]
                    assert code in (1537, 2560, 2561)
                    assert args["nodeid"] == (10 if code == 1537 else 60)
                    value = {
                        1537: [self.telemetry],
                        2560: self.controller,
                        2561: self.measurements,
                    }[code]
                    # Captured CCU replies echo node 10, without a code field.
                    data = {"nodeid": 10, "sn": SERIAL, "value": value}
                    if code == 1537:
                        data["code"] = code
                case "debug_ctrl_pile_charge":
                    args = payload["data"]
                    assert args["sn"] == SERIAL
                    assert args["nodeid"] == 10
                    assert args["gun_no"] == 1
                    assert args["op"] in (1, 2)
                    if self.ack == 0:
                        enabled = args["op"] == 1
                        self.telemetry.update(
                            if_work_st=2 if enabled else 5,
                            power=3848 if enabled else 0,
                            meter_current=16.165 if enabled else 0,
                        )
                        self.controller["CPState"] = 3 if enabled else 2
                    data = {"ack": self.ack, "nodeid": 10, "sn": SERIAL}
                case "set_param_value":
                    args = payload["data"]
                    assert args["sn"] == SERIAL
                    assert args["nodeid"] == 10
                    assert args["code"] == 6
                    assert args["value"]["connectorId"] == 0
                    assert 6 <= args["value"]["maxCurr"] <= 32
                    if self.ack == 0:
                        self.current["maxCurr"] = args["value"]["maxCurr"]
                    data = {
                        "ack": self.ack,
                        "nodeid": 10,
                        "sn": SERIAL,
                        "code": 6,
                        "reboot": False,
                    }
                case _:
                    raise AssertionError(f"Unverified command: {command}")
        return AiohttpClientMockResponse(
            method,
            url,
            json=deepcopy(
                {"cmd": command, "data": data, "errcode": "0", "success": "1"}
            ),
        )


@pytest.fixture
def charger(aioclient_mock):
    fake = FakeCharger()
    aioclient_mock.post(URL, side_effect=fake.handle)
    return fake


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL,
        title=f"Autel {SERIAL}",
        data=CONFIG.copy(),
    )
    entry.add_to_hass(hass)
    return entry
