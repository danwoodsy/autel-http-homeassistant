"""Conservative, serialized polling of the charger's small HTTP server."""

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AutelAuthError, AutelClient, AutelError, AutelProtocolError, numeric
from .const import DOMAIN, MAX_CURRENT, MIN_CURRENT
from .polling import PollingSettings

_LOGGER = logging.getLogger(__name__)


def connector_record(value: Any, key: str) -> dict:
    """Select connector 1 explicitly, rather than the first list item."""
    if isinstance(value, list):
        for record in value:
            if isinstance(record, dict) and record.get(key) == 1:
                return record
    raise AutelProtocolError("Missing connector 1 data")


def object_record(value: Any) -> dict:
    if not isinstance(value, dict):
        raise AutelProtocolError("Expected a realtime object")
    return value


@dataclass
class ChargerData:
    """Verified normal telemetry plus independently available detail groups."""

    telemetry: dict
    controller: dict
    current: dict
    measurements: dict = field(default_factory=dict)
    permissions: dict = field(default_factory=dict)
    network: dict = field(default_factory=dict)
    system: dict = field(default_factory=dict)
    details_available: set[str] = field(default_factory=set)
    http_requests_per_minute: int = 0


class AutelCoordinator(DataUpdateCoordinator[ChargerData]):
    """Never overlap refreshes, and poll optional groups less frequently."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: AutelClient,
        polling: PollingSettings,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=polling.unplugged_interval),
            always_update=False,
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=1, immediate=True
            ),
        )
        self.client = client
        self.polling = polling
        self.status_interval = polling.status_interval
        self.charging_interval = polling.charging_interval
        self.details_interval = polling.details_interval
        self._last_details_attempt: float | None = None
        self._last_telemetry_update: float | None = None
        self._force_details = False
        self._force_status = False
        self._force_current = False
        self._force_permissions = False

    async def _async_setup(self) -> None:
        try:
            await self.client.discover()
        except AutelAuthError as err:
            raise ConfigEntryAuthFailed("Charger login failed") from err
        except AutelError as err:
            raise UpdateFailed("Could not discover the charger") from err

    @property
    def max_current(self) -> float:
        assert self.client.info is not None
        maximum = min(self.client.info.rated_current, MAX_CURRENT)
        if self.data:
            offline = numeric(self.data.current.get("offlineCurr"))
            if offline is not None and offline >= MIN_CURRENT:
                maximum = min(maximum, offline)
        return float(int(maximum))

    async def async_refresh_all(self) -> None:
        self._force_details = True
        self._force_status = True
        await self.async_request_refresh()

    async def async_refresh_after_control(
        self, *, refresh_current: bool = False, refresh_permissions: bool = False
    ) -> None:
        """Read actual status and any changed setting after a fast control ACK."""
        self._force_status = True
        if refresh_current:
            self._force_current = True
        if refresh_permissions:
            self._force_permissions = True
        await self.async_request_refresh()

    async def _async_update_data(self) -> ChargerData:
        try:
            controller = object_record(await self.client.realtime(2560, 60))
            connected = self.connection_state(controller)
            connection_changed = (
                self.data is not None
                and connected != self.connection_state(self.data.controller)
            )
            now = monotonic()
            telemetry_due = (
                self._force_status
                or self.data is None
                or connected is not False
                or connection_changed
                or self._last_telemetry_update is None
                or now - self._last_telemetry_update
                >= self.polling.unplugged_status_interval
            )
            if telemetry_due:
                telemetry = connector_record(await self.client.realtime(1537), "gun_no")
                self._last_telemetry_update = monotonic()
                self._force_status = False
            else:
                telemetry = self.data.telemetry
            result = ChargerData(
                telemetry, controller, self.data.current if self.data else {}
            )
            if self.data:
                result.measurements = self.data.measurements
                result.permissions = self.data.permissions
                result.network = self.data.network
                result.system = self.data.system
                result.details_available = self.data.details_available.copy()
            now = monotonic()
            details_interval = (
                self.polling.unplugged_details_interval
                if connected is False
                else self.details_interval
            )
            details_due = (
                self._force_details
                or self._last_details_attempt is None
                or now - self._last_details_attempt >= details_interval
            )
            if details_due:
                self._force_details = False
                self._last_details_attempt = now
            if details_due or self._force_current:
                self._force_current = False
                try:
                    current = connector_record(
                        await self.client.parameters(5), "connectorId"
                    )
                    if numeric(current.get("maxCurr")) is None:
                        raise AutelProtocolError("Missing current limit")
                    result.current = current
                    result.details_available.add("current")
                except AutelAuthError:
                    raise
                except AutelError:
                    # A valid current ceiling is required at first setup.
                    if self.data is None:
                        raise
                    result.details_available.discard("current")
                    _LOGGER.debug("Current limit refresh failed")
            groups = ()
            if details_due:
                groups = ("measurements", "permissions", "network", "system")
            elif self._force_permissions:
                groups = ("permissions",)
            self._force_permissions = False
            # Each optional group fails independently. Cached detail values
            # become unavailable after a failed attempt, not stale readings.
            for group in groups:
                try:
                    match group:
                        case "measurements":
                            value = await self.client.realtime(2561, 60)
                        case "permissions":
                            value = await self.client.parameters(4)
                        case "network":
                            value = await self.client.request("get_current_network")
                        case "system":
                            value = await self.client.realtime(1536)
                    setattr(result, group, object_record(value))
                    result.details_available.add(group)
                except AutelAuthError:
                    raise
                except AutelError:
                    result.details_available.discard(group)
                    _LOGGER.debug("Optional %s refresh failed", group)
            self.update_interval = timedelta(
                seconds=(
                    self.polling.unplugged_interval
                    if connected is False
                    else self.charging_interval
                    if connected is True and numeric(telemetry.get("if_work_st")) == 2
                    else self.status_interval
                )
            )
            # Include the local count in change detection so unchanged charger
            # readings still publish a changed request rate after a refresh.
            result.http_requests_per_minute = self.client.requests_last_minute
            _LOGGER.debug(
                "Refresh complete: status=%s CPState=%s power=%sW current=%sA "
                "current_limit=%sA details=%s telemetry_refreshed=%s next_interval=%ss",
                numeric(telemetry.get("if_work_st")),
                numeric(controller.get("CPState")),
                numeric(telemetry.get("power")),
                numeric(telemetry.get("meter_current")),
                numeric(result.current.get("maxCurr")),
                sorted(result.details_available),
                telemetry_due,
                self.update_interval.total_seconds(),
            )
            return result
        except AutelAuthError as err:
            raise ConfigEntryAuthFailed("Charger authentication failed") from err
        except AutelError as err:
            # An unreachable charger should not be retried at the charging rate.
            self.update_interval = timedelta(seconds=max(60, self.status_interval))
            _LOGGER.debug(
                "Status refresh failed (%s); next interval=%ss",
                type(err).__name__,
                self.update_interval.total_seconds(),
            )
            raise UpdateFailed("Could not refresh the charger") from err

    @staticmethod
    def connection_state(controller: dict) -> bool | None:
        # CP 1 (~12 V) = no car; CP 2 (~9 V) = connected; CP 3 (~6 V) = ready.
        # ConnectCar is inverted on the observed firmware, so don't use it.
        state = numeric(controller.get("CPState"))
        if state == 1:
            return False
        if state in (2, 3):
            return True
        return None

    @property
    def vehicle_connected(self) -> bool | None:
        return self.connection_state(self.data.controller)

    @property
    def charging(self) -> bool | None:
        state = numeric(self.data.telemetry.get("if_work_st"))
        if state not in range(9):
            return None
        return state == 2

    @property
    def telemetry_age_seconds(self) -> float | None:
        if self._last_telemetry_update is None:
            return None
        return round(max(0, monotonic() - self._last_telemetry_update), 1)
