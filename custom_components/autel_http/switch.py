"""Configure the charger's persistent Autostart permission."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    async_add_entities([AutelAutostartSwitch(entry.runtime_data.coordinator)])


class AutelAutostartSwitch(AutelEntity, SwitchEntity):
    _attr_translation_key = "autostart"
    _attr_entity_category = EntityCategory.CONFIG
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

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_control(
            self.coordinator.client.set_autostart(True), refresh_permissions=True
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_control(
            self.coordinator.client.set_autostart(False), refresh_permissions=True
        )
