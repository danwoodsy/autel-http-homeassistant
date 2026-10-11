"""Charging measurements with verified units and conservative energy metadata."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from . import AutelConfigEntry
from .api import numeric
from .const import CHARGER_STATES, WIFI_SIGNAL_QUALITY
from .coordinator import AutelCoordinator
from .entity import AutelEntity


@dataclass(frozen=True, kw_only=True)
class AutelSensorDescription(SensorEntityDescription):
    group: str = "telemetry"
    field: str = ""
    scale: float = 1


SENSORS = (
    AutelSensorDescription(
        key="status",
        translation_key="status",
        field="if_work_st",
        device_class=SensorDeviceClass.ENUM,
        options=list(CHARGER_STATES.values()),
    ),
    AutelSensorDescription(
        key="power",
        translation_key="power",
        field="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    AutelSensorDescription(
        key="current",
        translation_key="current",
        field="meter_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    AutelSensorDescription(
        key="voltage",
        translation_key="voltage",
        field="meter_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    AutelSensorDescription(
        key="session_energy",
        translation_key="session_energy",
        field="energy",
        scale=0.001,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        # Reset behavior across sessions/reboots is not yet characterized.
    ),
    AutelSensorDescription(
        key="session_duration",
        translation_key="session_duration",
        field="haveChargedTime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
    AutelSensorDescription(
        key="meter_energy",
        translation_key="meter_energy",
        group="measurements",
        field="MeterValue",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
    ),
    AutelSensorDescription(
        key="pilot_duty_cycle",
        translation_key="pilot_duty_cycle",
        group="measurements",
        field="CpDutyCycle",
        native_unit_of_measurement="%",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    AutelSensorDescription(
        key="pilot_voltage",
        translation_key="pilot_voltage",
        group="measurements",
        field="CpVolt",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    AutelSensorDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        group="system",
        field="CpuState",
        icon="mdi:cpu-64-bit",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AutelSensorDescription(
        key="memory_usage",
        translation_key="memory_usage",
        group="system",
        field="MemState",
        icon="mdi:memory",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AutelSensorDescription(
        key="flash_usage",
        translation_key="flash_usage",
        group="system",
        field="FlashState",
        icon="mdi:harddisk",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AutelSensorDescription(
        key="wifi_signal_quality",
        translation_key="wifi_signal_quality",
        group="network",
        field="signalLevel",
        icon="mdi:wifi",
        device_class=SensorDeviceClass.ENUM,
        options=list(WIFI_SIGNAL_QUALITY.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
) + tuple(
    AutelSensorDescription(
        key=f"phase_{phase.lower()}_current",
        translation_key=f"phase_{phase.lower()}_current",
        group="measurements",
        field=f"Current{phase}",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    )
    for phase in ("A", "B", "C")
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AutelConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    # The signal quality entity now includes the raw level as an attribute.
    # Remove the superseded entity while retaining the quality entity's ID
    # and any user customization.
    registry = er.async_get(hass)
    info = entry.runtime_data.client.info
    assert info is not None
    entity_id = registry.async_get_entity_id(
        "sensor", entry.domain, f"{info.serial}_network_signal_level"
    )
    if entity_id is not None:
        registered = registry.async_get(entity_id)
        if registered and registered.config_entry_id == entry.entry_id:
            registry.async_remove(entity_id)
    async_add_entities(
        [
            AutelSensor(entry.runtime_data.coordinator, description)
            for description in SENSORS
        ]
        + [AutelRequestRate(entry.runtime_data.coordinator)]
    )


class AutelSensor(AutelEntity, SensorEntity):
    entity_description: AutelSensorDescription

    def __init__(
        self, coordinator: AutelCoordinator, description: AutelSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        group = self.entity_description.group
        return super().available and (
            group == "telemetry" or group in self.coordinator.data.details_available
        )

    @property
    def native_value(self) -> float | str | None:
        description = self.entity_description
        record = getattr(self.coordinator.data, description.group)
        value = numeric(record.get(description.field))
        if description.key == "status":
            return CHARGER_STATES.get(value)
        if description.key == "wifi_signal_quality":
            if numeric(record.get("networkType")) != 4:
                return None
            return WIFI_SIGNAL_QUALITY.get(value)
        return value * description.scale if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, int | None] | None:
        if self.entity_description.key != "wifi_signal_quality":
            return None
        level = numeric(self.coordinator.data.network.get("signalLevel"))
        return {"signal_level": int(level) if level in WIFI_SIGNAL_QUALITY else None}


class AutelRequestRate(AutelEntity, SensorEntity):
    """Publish a local rolling count, including when charger polling is disabled."""

    _attr_translation_key = "http_requests_per_minute"
    _attr_icon = "mdi:web"
    _attr_native_unit_of_measurement = "requests/min"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AutelCoordinator) -> None:
        super().__init__(coordinator, "http_requests_per_minute")

    @property
    def available(self) -> bool:
        # A local counter remains useful when HTTP requests fail.
        return True

    @property
    def native_value(self) -> int:
        return self.coordinator.client.requests_last_minute

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._publish_count, timedelta(seconds=60)
            )
        )

    @callback
    def _publish_count(self, _: datetime) -> None:
        # This updates the cached HA state without making any HTTP request.
        self.async_write_ha_state()
