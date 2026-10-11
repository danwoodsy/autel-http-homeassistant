"""Vehicle connection and the observed Autostart permission."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AutelConfigEntry
from .api import numeric
from .coordinator import AutelCoordinator
from .entity import AutelEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AutelConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [
            AutelVehicleConnected(entry.runtime_data.coordinator),
            AutelCharging(entry.runtime_data.coordinator),
            AutelAutostart(entry.runtime_data.coordinator),
        ]
    )


class AutelCharging(AutelEntity, BinarySensorEntity):
    _attr_translation_key = "charging"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: AutelCoordinator) -> None:
        super().__init__(coordinator, "charging")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.charging


class AutelVehicleConnected(AutelEntity, BinarySensorEntity):
    _attr_translation_key = "vehicle_connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: AutelCoordinator) -> None:
        super().__init__(coordinator, "vehicle_connected")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.vehicle_connected


class AutelAutostart(AutelEntity, BinarySensorEntity):
    _attr_translation_key = "autostart"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:play-circle-outline"

    def __init__(self, coordinator: AutelCoordinator) -> None:
        super().__init__(coordinator, "autostart")

    @property
    def available(self) -> bool:
        return (
            super().available
            and "permissions" in self.coordinator.data.details_available
        )

    @property
    def is_on(self) -> bool | None:
        state = numeric(self.coordinator.data.permissions.get("CustomizedPnC"))
        return {0: False, 2: True}.get(state)
