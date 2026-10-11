"""Charging start/stop and manual refresh buttons."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AutelConfigEntry
from .coordinator import AutelCoordinator
from .entity import AutelEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AutelConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            AutelChargeButton(coordinator, True),
            AutelChargeButton(coordinator, False),
            AutelRefreshButton(coordinator),
        ]
    )


class AutelChargeButton(AutelEntity, ButtonEntity):
    """Send an explicit start or stop; status sensors report the outcome."""

    def __init__(self, coordinator: AutelCoordinator, enabled: bool) -> None:
        key = "start_charging" if enabled else "stop_charging"
        super().__init__(coordinator, key)
        self._enabled = enabled
        self._attr_translation_key = key
        self._attr_icon = "mdi:play" if enabled else "mdi:stop"

    @property
    def available(self) -> bool:
        if not super().available or self.coordinator.vehicle_connected is not True:
            return False
        return not self._enabled or self.coordinator.charging is False

    async def async_press(self) -> None:
        if not self.available:
            raise ServiceValidationError(
                "This charging control is unavailable for the current vehicle state"
            )
        await self.async_control(self.coordinator.client.set_charging(self._enabled))


class AutelRefreshButton(AutelEntity, ButtonEntity):
    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: AutelCoordinator) -> None:
        super().__init__(coordinator, "refresh")

    @property
    def available(self) -> bool:
        # A failed poll must not disable the user's way to request recovery.
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_refresh_all()
