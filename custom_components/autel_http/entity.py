"""Shared identity and control error handling."""

from collections.abc import Awaitable

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AutelAuthError, AutelError
from .const import DOMAIN
from .coordinator import AutelCoordinator


class AutelEntity(CoordinatorEntity[AutelCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: AutelCoordinator, key: str) -> None:
        super().__init__(coordinator)
        info = coordinator.client.info
        assert info is not None
        self._attr_unique_id = f"{info.serial}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, info.serial)},
            name=f"Autel {info.serial}",
            manufacturer="Autel",
            model=info.model,
            serial_number=info.serial,
            sw_version=info.firmware,
            configuration_url=coordinator.client.origin,
        )

    async def async_control(self, action: Awaitable[None]) -> None:
        try:
            await action
        except AutelAuthError as err:
            entry = self.coordinator.config_entry
            if entry:
                entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Charger login failed; reauthenticate") from err
        except AutelError as err:
            raise HomeAssistantError(
                "Charger control failed; refresh status before trying again"
            ) from err
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        # ACK is acceptance, not proof that the vehicle draws power. Always read
        # actual status back; never claim success through optimistic state.
        # Return after the fast control ACK. Slow telemetry runs in the
        # background, with the task canceled automatically on entry unload.
        entry = self.coordinator.config_entry
        assert entry is not None
        entry.async_create_background_task(
            self.hass,
            self.coordinator.async_request_refresh(),
            "Refresh Autel status after control",
        )
