"""Verified charging-current limit."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AutelConfigEntry
from .api import numeric
from .const import MIN_CURRENT
from .coordinator import AutelCoordinator
from .entity import AutelEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AutelConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([AutelCurrentLimit(entry.runtime_data.coordinator)])


class AutelCurrentLimit(AutelEntity, NumberEntity):
    _attr_translation_key = "current_limit"
    _attr_icon = "mdi:current-ac"
    _attr_native_min_value = MIN_CURRENT
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AutelCoordinator) -> None:
        super().__init__(coordinator, "current_limit")

    @property
    def available(self) -> bool:
        return (
            super().available and "current" in self.coordinator.data.details_available
        )

    @property
    def native_max_value(self) -> float:
        return self.coordinator.max_current

    @property
    def native_value(self) -> float | None:
        return numeric(self.coordinator.data.current.get("maxCurr"))

    async def async_set_native_value(self, value: float) -> None:
        await self.async_control(
            self.coordinator.client.set_current(value, self.native_max_value),
            refresh_current=True,
        )
