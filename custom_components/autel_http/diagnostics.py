"""Download useful cached diagnostics without exposing login credentials."""

from homeassistant.const import CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant

from . import AutelConfigEntry

# Keep an allowlist: unexpected firmware fields must never leak credentials.
FIELDS = {
    "telemetry": (
        "gun_no",
        "if_work_st",
        "power",
        "meter_current",
        "meter_voltage",
        "energy",
        "haveChargedTime",
        "meter_F_energy",
        "meter_R_energy",
    ),
    "controller": (
        "CPState",
        "EVSEState",
        "ConnectCar",
        "WorkState",
        "LockState",
        "RelayState1",
        "RelayState2",
        "PPState",
    ),
    "current": ("connectorId", "maxCurr", "offlineCurr"),
    "measurements": (
        "ChargePower",
        "CurrentA",
        "CurrentB",
        "CurrentC",
        "InputVoltA",
        "InputVoltB",
        "InputVoltC",
        "OutputVoltA",
        "OutputVoltB",
        "OutputVoltC",
        "CpDutyCycle",
        "CpVolt",
        "CpNVolt",
        "GridNum",
        "MeterValue",
        "RateCurrent",
    ),
    "permissions": ("CustomizedPnC",),
    "network": ("networkType", "signalLevel"),
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AutelConfigEntry
) -> dict:
    coordinator = entry.runtime_data.coordinator
    info = entry.runtime_data.client.info
    assert info is not None
    data = coordinator.data
    return {
        "device": {
            "model": info.model,
            "firmware": info.firmware,
            "rated_current": info.rated_current,
        },
        "connection": {"verify_ssl": entry.data.get(CONF_VERIFY_SSL, False)},
        "polling": {
            "status_interval": coordinator.update_interval.total_seconds(),
            "details_interval": coordinator.details_interval,
            "last_update_success": coordinator.last_update_success,
            "available_detail_groups": sorted(data.details_available),
        },
        "readings": {
            group: {key: record[key] for key in fields if key in record}
            for group, fields in FIELDS.items()
            if (record := getattr(data, group))
        },
    }
