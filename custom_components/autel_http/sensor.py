"""Charging measurements with verified units and conservative energy metadata."""

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AutelConfigEntry
from .api import numeric
from .const import CHARGER_STATES
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
        key="network_signal_level",
        translation_key="network_signal_level",
        group="network",
        field="signalLevel",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
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
    async_add_entities(
        AutelSensor(entry.runtime_data.coordinator, description)
        for description in SENSORS
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
        return value * description.scale if value is not None else None
