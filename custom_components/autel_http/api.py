"""Serialized client for the reverse-engineered /localcfg HTTPS interface."""

import asyncio
import hashlib
import math
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from .const import MAX_CURRENT, MIN_CURRENT


class AutelError(Exception):
    """A charger request failed."""


class AutelConnectionError(AutelError):
    """The charger could not be reached."""


class AutelAuthError(AutelError):
    """The charger rejected the credentials."""


class AutelProtocolError(AutelError):
    """The charger returned an invalid or unsuccessful response."""


class UnsupportedCharger(AutelError):
    """The charger does not match the verified single-connector AC interface."""


def normalize_host(host: str) -> str:
    """Accept an IP, hostname or HTTPS origin without credentials or paths."""
    host = host.strip()
    parsed = urlsplit(host if "://" in host else f"https://{host}")
    try:
        port = parsed.port
    except ValueError as err:
        raise ValueError("Invalid port") from err
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or any(char.isspace() for char in parsed.netloc)
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError("Enter a charger IP address or HTTPS hostname")
    hostname = parsed.hostname
    if ":" in hostname:
        hostname = f"[{hostname}]"
    return f"{hostname}:{port}" if port is not None else hostname


def numeric(value: Any) -> float | None:
    """Read a finite numeric device value, including quoted numbers."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


@dataclass(frozen=True)
class ChargerInfo:
    """Identity and limits discovered from the charger."""

    serial: str
    model: str
    firmware: str | None
    rated_current: float
    connector_id: int = 1


class AutelClient:
    """Use the issued token, with one renewal on explicit error 1001.

    All requests share a lock. A mutation is never retried on a transport
    failure: its outcome may already have taken effect on the charger.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        pin: str,
        *,
        verify_ssl: bool = False,
        timeout: int = 15,
    ) -> None:
        self._session = session
        self.host = normalize_host(host)
        self._username = username
        self._password_hash = hashlib.sha256(pin.encode("utf-8")).hexdigest()
        self._verify_ssl = verify_ssl
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._token: str | None = None
        self._lock = asyncio.Lock()
        self.info: ChargerInfo | None = None

    @property
    def origin(self) -> str:
        return f"https://{self.host}"

    def clear_token(self) -> None:
        self._token = None

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Accept": "application/json", "X-Language": "en-US"}
        if self._token and payload["cmd"] != "account_login":
            headers["Authorization"] = self._token
        try:
            async with self._session.post(
                f"{self.origin}/localcfg",
                json=payload,
                headers=headers,
                ssl=self._verify_ssl,
                timeout=self._timeout,
            ) as response:
                if response.status in (401, 403):
                    raise AutelAuthError("HTTPS authentication rejected")
                response.raise_for_status()
                reply = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise AutelConnectionError("HTTPS request failed") from err
        except (ValueError, UnicodeError) as err:
            raise AutelProtocolError("Invalid JSON response") from err
        if not isinstance(reply, dict):
            raise AutelProtocolError("Invalid response envelope")
        return reply

    @staticmethod
    def _validate(reply: dict[str, Any], command: str) -> Any:
        if str(reply.get("errcode")) in {"1001", "1003", "1004"}:
            raise AutelAuthError("Charger authentication rejected")
        if (
            str(reply.get("success")) != "1"
            or str(reply.get("errcode")) != "0"
            or reply.get("cmd") != command
        ):
            raise AutelProtocolError(f"Charger rejected {command}")
        return reply.get("data")

    async def _login(self) -> None:
        self._token = None
        command = "account_login"
        reply = await self._post(
            {
                "cmd": command,
                "data": {"account": self._username, "password": self._password_hash},
            }
        )
        data = self._validate(reply, command)
        if not isinstance(data, dict) or not isinstance(data.get("token"), str):
            raise AutelProtocolError("Login did not return a token")
        if not data["token"]:
            raise AutelProtocolError("Login returned an empty token")
        self._token = data["token"]

    async def request(self, command: str, data: dict | None = None) -> Any:
        """Send one command; retry only a JSON authentication rejection."""
        async with self._lock:
            if self._token is None:
                await self._login()
            payload: dict[str, Any] = {"cmd": command, "token": self._token}
            if data is not None:
                payload["data"] = data
            reply = await self._post(payload)
            if str(reply.get("errcode")) == "1001":
                await self._login()
                payload["token"] = self._token
                reply = await self._post(payload)
            try:
                return self._validate(reply, command)
            except AutelAuthError:
                self.clear_token()
                raise

    async def discover(self) -> ChargerInfo:
        data = await self.request("get_baseinfo")
        if not isinstance(data, dict) or not isinstance(data.get("sn"), str):
            raise AutelProtocolError("Missing charger identity")
        if not data["sn"]:
            raise AutelProtocolError("Empty charger identity")
        ac_info = data.get("AC")
        connectors = ac_info.get("connectors", []) if isinstance(ac_info, dict) else []
        if (
            not isinstance(connectors, list)
            or len(connectors) != 1
            or not isinstance(connectors[0], dict)
            or connectors[0].get("connector_id") != 1
        ):
            raise UnsupportedCharger("Only a single AC connector is supported")
        rated = numeric(connectors[0].get("ratedcur"))
        if rated is None or rated < MIN_CURRENT:
            raise UnsupportedCharger("Invalid rated connector current")
        versions = data.get("versions", {})
        if not isinstance(versions, dict):
            raise AutelProtocolError("Invalid firmware information")
        self.info = ChargerInfo(
            serial=data["sn"],
            model=str(data.get("device_model", "MaxiCharger")),
            firmware=versions.get("bigVersion"),
            rated_current=min(rated, MAX_CURRENT),
        )
        return self.info

    def _address(self, node: int = 10) -> dict[str, Any]:
        if self.info is None:
            raise AutelProtocolError("Charger identity has not been discovered")
        return {"sn": self.info.serial, "nodeid": node}

    async def realtime(self, code: int, node: int = 10) -> dict | list:
        data = await self.request(
            "get_realtime_data", {**self._address(node), "rtcode": code}
        )
        if not isinstance(data, dict) or not isinstance(
            data.get("value"), (dict, list)
        ):
            raise AutelProtocolError("Missing realtime data")
        # CCU requests use node 60; verified replies echo node 10 and omit code.
        return data["value"]

    async def parameters(self, code: int) -> dict | list:
        data = await self.request(
            "get_param_value", {**self._address(), "list": [code]}
        )
        if isinstance(data, dict) and isinstance(data.get("list"), list):
            for entry in data["list"]:
                if isinstance(entry, dict) and entry.get("code") == code:
                    if isinstance(entry.get("value"), (dict, list)):
                        return entry["value"]
        raise AutelProtocolError("Missing parameter data")

    @staticmethod
    def _check_ack(data: Any) -> None:
        if not isinstance(data, dict) or str(data.get("ack")) != "0":
            raise AutelProtocolError("Charger did not acknowledge the control")

    async def set_charging(self, enabled: bool) -> None:
        data = await self.request(
            "debug_ctrl_pile_charge",
            {**self._address(), "gun_no": 1, "op": 1 if enabled else 2},
        )
        self._check_ack(data)

    async def set_current(self, amps: float, maximum: float) -> None:
        if (
            numeric(amps) is None
            or not MIN_CURRENT <= amps <= min(maximum, MAX_CURRENT)
            or not float(amps).is_integer()
        ):
            raise ValueError("Current must be a whole number within charger limits")
        data = await self.request(
            "set_param_value",
            {
                **self._address(),
                "code": 6,
                # Readback connector 1; this firmware's verified write uses 0.
                "value": {"connectorId": 0, "maxCurr": int(amps)},
            },
        )
        self._check_ack(data)
