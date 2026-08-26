"""Sensores de bandera de playa."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, FLAG_STATES
from .coordinator import CruzRojaPlayasConfigEntry, CruzRojaPlayasCoordinator
from .icons_map import flag_entity_picture


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CruzRojaPlayasConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea un sensor por playa y da de alta las que aparezcan mas adelante."""
    coordinator = entry.runtime_data
    conocidas: set[int] = set()

    @callback
    def _anadir_nuevas() -> None:
        nuevas = set(coordinator.data or {}) - conocidas
        if not nuevas:
            return
        conocidas.update(nuevas)
        async_add_entities(BanderaPlayaSensor(coordinator, playa_id) for playa_id in nuevas)

    entry.async_on_unload(coordinator.async_add_listener(_anadir_nuevas))
    _anadir_nuevas()


class BanderaPlayaSensor(CoordinatorEntity[CruzRojaPlayasCoordinator], SensorEntity):
    """Estado de la bandera de una playa."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_attribution = ATTRIBUTION
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = FLAG_STATES
    _attr_translation_key = "bandera"

    def __init__(self, coordinator: CruzRojaPlayasCoordinator, playa_id: int) -> None:
        super().__init__(coordinator)
        self._playa_id = playa_id
        self._attr_unique_id = f"{DOMAIN}_{playa_id}"

        playa = coordinator.data[playa_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(playa_id))},
            name=f"Playa {playa.nombre}",
            manufacturer="Cruz Roja Española",
            model=coordinator.autonomia_nombre,
            suggested_area=playa.municipio,
            configuration_url="https://www.cruzroja.es/appjv/consPlayas/consultaInicio.do",
        )

    @property
    def available(self) -> bool:
        """La playa desaparece del listado fuera de la temporada de cobertura."""
        return super().available and self._playa_id in (self.coordinator.data or {})

    @property
    def native_value(self) -> str | None:
        if (playa := (self.coordinator.data or {}).get(self._playa_id)) is None:
            return None
        return playa.bandera

    @property
    def entity_picture(self) -> str | None:
        """Icono de bandera para que el mapa lo muestre en vez de las iniciales."""
        if (playa := (self.coordinator.data or {}).get(self._playa_id)) is None:
            return None
        return flag_entity_picture(playa.bandera)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if (playa := (self.coordinator.data or {}).get(self._playa_id)) is None:
            return {}
        return {
            "playa_id": playa.id,
            "nombre": playa.nombre,
            "municipio": playa.municipio,
            "provincia": playa.provincia,
            "autonomia": self.coordinator.autonomia_nombre,
            **playa.atributos,
        }
