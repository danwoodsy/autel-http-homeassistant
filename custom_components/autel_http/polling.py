"""Named polling presets with optional per-state intervals."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .const import (
    CONF_POLLING_PRESET,
    DEFAULT_CHARGING_INTERVAL,
    DEFAULT_DETAILS_INTERVAL,
    DEFAULT_POLLING_PRESET,
    DEFAULT_STATUS_INTERVAL,
    DEFAULT_UNPLUGGED_DETAILS_INTERVAL,
    DEFAULT_UNPLUGGED_INTERVAL,
    DEFAULT_UNPLUGGED_STATUS_INTERVAL,
)


@dataclass(frozen=True)
class PollingSettings:
    unplugged_interval: int = DEFAULT_UNPLUGGED_INTERVAL
    unplugged_status_interval: int = DEFAULT_UNPLUGGED_STATUS_INTERVAL
    unplugged_details_interval: int = DEFAULT_UNPLUGGED_DETAILS_INTERVAL
    status_interval: int = DEFAULT_STATUS_INTERVAL
    charging_interval: int = DEFAULT_CHARGING_INTERVAL
    details_interval: int = DEFAULT_DETAILS_INTERVAL


PRESETS = {
    "high": PollingSettings(10, 60, 150, 10, 5, 60),
    "medium": PollingSettings(),
    # Keep plug-in detection within the user's 10-30 second target.
    "low": PollingSettings(30, 240, 600, 40, 20, 240),
}


def polling_preset(options: Mapping[str, Any]) -> str:
    """Preserve existing numeric options by treating them as Custom."""
    if (preset := options.get(CONF_POLLING_PRESET)) in (*PRESETS, "custom"):
        return preset
    if any(key in options for key in asdict(PRESETS[DEFAULT_POLLING_PRESET])):
        return "custom"
    return DEFAULT_POLLING_PRESET


def polling_settings(options: Mapping[str, Any]) -> PollingSettings:
    preset = polling_preset(options)
    if preset in PRESETS:
        return PRESETS[preset]
    defaults = asdict(PRESETS[DEFAULT_POLLING_PRESET])
    return PollingSettings(
        **{key: int(options.get(key, value)) for key, value in defaults.items()}
    )
