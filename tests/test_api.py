"""Validate captured wire formats, limits, and safe authentication renewal."""

import asyncio
import logging
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.autel_http.api import (
    AutelAuthError,
    AutelClient,
    AutelConnectionError,
    AutelProtocolError,
    UnsupportedCharger,
    normalize_host,
)

from .conftest import HOST, PIN_HASH, SERIAL, TEST_PIN


@pytest.fixture
def client(hass, charger):
    return AutelClient(async_get_clientsession(hass), HOST, "admin", TEST_PIN)


async def test_login_and_discovery(client, charger, aioclient_mock):
    info = await client.discover()
    assert info.serial == SERIAL
    assert info.rated_current == 32
    assert charger.calls[0]["data"]["password"] == PIN_HASH
    assert charger.calls[1]["token"] == "issued-token-1"
    assert aioclient_mock.mock_calls[1][3]["Authorization"] == "issued-token-1"
    assert "Authorization" not in aioclient_mock.mock_calls[0][3]
    await client.request("get_current_network")
    assert charger.login_count == 1


async def test_request_count_expires_and_includes_login_retries_and_failures(
    client, charger
):
    with patch("custom_components.autel_http.api.monotonic", return_value=100):
        await client.discover()
        assert client.requests_last_minute == 2
    charger.overrides["get_current_network"] = [
        {"cmd": "get_current_network", "errcode": "1001", "success": "-1"}
    ]
    with patch("custom_components.autel_http.api.monotonic", return_value=110):
        await client.request("get_current_network")
        assert client.requests_last_minute == 5
    with patch("custom_components.autel_http.api.monotonic", return_value=150):
        await client.set_current(10, 32)
    charger.overrides["debug_ctrl_pile_charge"] = [TimeoutError()]
    with patch("custom_components.autel_http.api.monotonic", return_value=155):
        with pytest.raises(AutelConnectionError):
            await client.set_charging(False)
        assert client.requests_last_minute == 7
    count = len(charger.calls)
    for now, expected in ((159, 7), (160, 5), (170, 2), (215, 0)):
        with patch("custom_components.autel_http.api.monotonic", return_value=now):
            assert client.requests_last_minute == expected
    assert len(charger.calls) == count  # Reading the counter never hits the charger.


async def test_debug_logs_include_timings_without_credentials(client, charger, caplog):
    caplog.set_level(logging.DEBUG, logger="custom_components.autel_http.api")
    await client.discover()
    await client.realtime(1537)
    charger.overrides["debug_ctrl_pile_charge"] = [TimeoutError()]
    with pytest.raises(AutelConnectionError):
        await client.set_charging(False)
    logs = caplog.text
    assert "command=get_realtime_data rtcode=1537" in logs
    assert "HTTP status=200 duration=" in logs
    assert "HTTPS request failed: command=debug_ctrl_pile_charge" in logs
    assert "requests_last_minute=" in logs
    for forbidden in (TEST_PIN, PIN_HASH, charger.token, HOST, SERIAL, "admin"):
        assert forbidden not in logs


async def test_tls_and_timeout_are_explicit(client, charger):
    with patch.object(client._session, "post", wraps=client._session.post) as post:
        await client.discover()
        assert post.call_args.kwargs["ssl"] is False
        assert post.call_args.kwargs["timeout"].total == 15
    verified = AutelClient(
        client._session, HOST, "admin", TEST_PIN, verify_ssl=True, timeout=30
    )
    with patch.object(client._session, "post", wraps=client._session.post) as post:
        await verified.discover()
        assert post.call_args.kwargs["ssl"] is True
        assert post.call_args.kwargs["timeout"].total == 30


async def test_renew_on_explicit_1001_once(client, charger):
    await client.discover()
    rejection = {
        "cmd": "get_current_network",
        "data": "",
        "errcode": "1001",
        "success": "-1",
    }
    charger.overrides["get_current_network"] = [rejection]
    await client.request("get_current_network")
    assert charger.login_count == 2
    assert charger.calls[-1]["token"] == "issued-token-2"
    charger.overrides["get_current_network"] = [rejection, rejection]
    with pytest.raises(AutelAuthError):
        await client.request("get_current_network")
    assert charger.login_count == 3
    assert client._token is None


async def test_auth_rejected_at_login(client, charger):
    charger.overrides["account_login"] = [
        {"cmd": "account_login", "errcode": "1003", "success": "0"}
    ]
    with pytest.raises(AutelAuthError):
        await client.discover()
    assert len(charger.calls) == 1


@pytest.mark.parametrize("fault", [TimeoutError(), aiohttp.ClientConnectionError()])
async def test_never_retry_ambiguous_mutation(client, charger, fault):
    await client.discover()
    charger.overrides["debug_ctrl_pile_charge"] = [fault]
    with pytest.raises(AutelConnectionError):
        await client.set_charging(False)
    assert sum(c["cmd"] == "debug_ctrl_pile_charge" for c in charger.calls) == 1
    assert charger.login_count == 1


async def test_start_stop_and_current_addressing(client, charger):
    await client.discover()
    await client.set_charging(False)
    assert charger.calls[-1]["data"] == {
        "sn": SERIAL,
        "nodeid": 10,
        "gun_no": 1,
        "op": 2,
    }
    await client.set_charging(True)
    assert charger.calls[-1]["data"]["op"] == 1
    await client.set_current(10, 32)
    assert charger.calls[-1]["data"] == {
        "sn": SERIAL,
        "nodeid": 10,
        "code": 6,
        "value": {"connectorId": 0, "maxCurr": 10},
    }
    assert (await client.parameters(5))[0]["connectorId"] == 1
    assert (await client.realtime(2560, 60))["CPState"] == 3


@pytest.mark.parametrize("value", [0, 5, 33, 10.5, float("nan"), float("inf")])
async def test_limits_fail_without_network(client, charger, value):
    await client.discover()
    count = len(charger.calls)
    with pytest.raises(ValueError):
        await client.set_current(value, 32)
    assert len(charger.calls) == count


async def test_ack_required_even_on_success(client, charger):
    await client.discover()
    charger.ack = 1
    with pytest.raises(AutelProtocolError):
        await client.set_charging(False)
    with pytest.raises(AutelProtocolError):
        await client.set_current(10, 32)
    with pytest.raises(AutelProtocolError):
        await client.set_autostart(False)
    assert charger.current["maxCurr"] == 16
    assert charger.permissions["CustomizedPnC"] == 2


@pytest.mark.parametrize(
    "reply",
    [
        [],
        {"cmd": "account_login", "data": {}, "errcode": "0", "success": "1"},
        {"cmd": "account_login", "data": {"token": ""}, "errcode": "0", "success": "1"},
        {"cmd": "", "data": "", "errcode": "-1", "success": "0"},
    ],
)
async def test_bad_login_reply(client, charger, reply):
    charger.overrides["account_login"] = [reply]
    with pytest.raises(AutelProtocolError):
        await client.discover()


async def test_rejects_unsupported_connector_layout(client, charger):
    charger.base["AC"]["connectors"].append({"connector_id": 2, "ratedcur": 32})
    with pytest.raises(UnsupportedCharger):
        await client.discover()


async def test_serializes_concurrent_commands(client, charger):
    await client.discover()
    active = 0
    maximum = 0
    original = client._post

    async def slow_post(payload):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        try:
            return await original(payload)
        finally:
            active -= 1

    with patch.object(client, "_post", side_effect=slow_post):
        await asyncio.gather(
            client.realtime(1537),
            client.realtime(2560, 60),
            client.set_current(10, 32),
            client.set_charging(False),
        )
    assert maximum == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("192.0.2.27", "192.0.2.27"),
        (" https://charger.local/ ", "charger.local"),
        ("charger.local:8443", "charger.local:8443"),
        ("[2001:db8::27]", "[2001:db8::27]"),
    ],
)
def test_address_normalization(value, expected):
    assert normalize_host(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://charger.local",
        "https://user:pass@charger.local",
        "charger.local/localcfg",
        "charger.local?pin=x",
        "",
        "host:99999",
        "host:0",
        "two hosts",
    ],
)
def test_address_validation(value):
    with pytest.raises(ValueError):
        normalize_host(value)
