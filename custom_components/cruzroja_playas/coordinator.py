"""Coordinador de actualizacion para las banderas de playas."""

from __future__ import annotations

import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CruzRojaPlayasClient, CruzRojaPlayasError, Playa
from .const import (
    CONF_AUTONOMIA_ID,
    CONF_AUTONOMIA_NOMBRE,
    CONF_PATRONES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type CruzRojaPlayasConfigEntry = ConfigEntry[CruzRojaPlayasCoordinator]


#: Comodin de "todas las playas". No es un regex valido por si solo (nada que
#: repetir con *), asi que se traduce a ".*" antes de compilar.
_COMODIN_TODAS = "*"


def compilar_patrones(patrones: list[str]) -> list[re.Pattern[str]]:
    """Compila los patrones del usuario (lanza ``re.error`` si alguno es invalido)."""
    return [
        re.compile(".*" if p.strip() == _COMODIN_TODAS else p, re.IGNORECASE)
        for p in patrones
        if p.strip()
    ]


class CruzRojaPlayasCoordinator(DataUpdateCoordinator[dict[int, Playa]]):
    """Descarga el listado de la autonomia y las fichas de las playas que casan."""

    config_entry: CruzRojaPlayasConfigEntry

    def __init__(self, hass: HomeAssistant, entry: CruzRojaPlayasConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = CruzRojaPlayasClient(async_get_clientsession(hass))
        self.autonomia_id: int = int(entry.data[CONF_AUTONOMIA_ID])
        self.autonomia_nombre: str = entry.data[CONF_AUTONOMIA_NOMBRE]
        self._patrones = compilar_patrones(
            entry.options.get(CONF_PATRONES, entry.data.get(CONF_PATRONES, []))
        )

    async def _async_update_data(self) -> dict[int, Playa]:
        try:
            playas = await self.client.async_get_playas(self.autonomia_id)
        except CruzRojaPlayasError as err:
            raise UpdateFailed(str(err)) from err

        seleccionadas = [
            playa
            for playa in playas
            if any(patron.search(playa.etiqueta) for patron in self._patrones)
        ]
        await self.client.async_fill_fichas(seleccionadas)
        return {playa.id: playa for playa in seleccionadas}
