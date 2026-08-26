"""Flujo de configuracion de la integracion."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import Autonomia, CruzRojaPlayasClient, CruzRojaPlayasError
from .const import CONF_AUTONOMIA_ID, CONF_AUTONOMIA_NOMBRE, CONF_PATRONES, DOMAIN
from .coordinator import CruzRojaPlayasConfigEntry, compilar_patrones

PATRONES_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True)
)


def _parse_patrones(raw: str) -> list[str]:
    """Un patron por linea; se ignoran las lineas en blanco."""
    return [linea.strip() for linea in raw.splitlines() if linea.strip()]


class CruzRojaPlayasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Alta de una autonomia con su lista de patrones."""

    VERSION = 1

    def __init__(self) -> None:
        self._autonomias: list[Autonomia] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        client = CruzRojaPlayasClient(async_get_clientsession(self.hass))
        if not self._autonomias:
            try:
                self._autonomias = await client.async_get_autonomias()
            except CruzRojaPlayasError:
                return self.async_abort(reason="cannot_connect")

        errors: dict[str, str] = {}
        if user_input is not None:
            autonomia_id = int(user_input[CONF_AUTONOMIA_ID])
            patrones = _parse_patrones(user_input[CONF_PATRONES])
            try:
                compilados = compilar_patrones(patrones)
            except re.error:
                errors[CONF_PATRONES] = "invalid_regex"
            else:
                try:
                    playas = await client.async_get_playas(autonomia_id)
                except CruzRojaPlayasError:
                    errors["base"] = "cannot_connect"
                else:
                    coincidencias = [
                        p
                        for p in playas
                        if any(rx.search(p.etiqueta) for rx in compilados)
                    ]
                    if not coincidencias:
                        errors[CONF_PATRONES] = "no_matches"
                    else:
                        nombre = next(
                            a.nombre
                            for a in self._autonomias
                            if a.codigo == autonomia_id
                        )
                        await self.async_set_unique_id(f"{autonomia_id}:{'|'.join(patrones)}")
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"{nombre} ({len(coincidencias)} playas)",
                            data={
                                CONF_AUTONOMIA_ID: autonomia_id,
                                CONF_AUTONOMIA_NOMBRE: nombre,
                            },
                            options={CONF_PATRONES: patrones},
                        )

        schema = vol.Schema(
                {
                        vol.Required(CONF_AUTONOMIA_ID, default=(user_input or {}).get(CONF_AUTONOMIA_ID)): SelectSelector(
                                SelectSelectorConfig(
                                        options=[
                                                SelectOptionDict(value=str(a.codigo), label=a.nombre)
                                                for a in self._autonomias
                                        ],
                                        mode=SelectSelectorMode.DROPDOWN,
                                )
                        ),
                        vol.Required(
                                CONF_PATRONES, default=(user_input or {}).get(CONF_PATRONES, "")
                        ): PATRONES_SELECTOR,
                }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    def async_get_options_flow(entry: CruzRojaPlayasConfigEntry) -> OptionsFlow:
        return CruzRojaPlayasOptionsFlow()


class CruzRojaPlayasOptionsFlow(OptionsFlow):
    """Permite editar los patrones sin volver a dar de alta la autonomia."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            patrones = _parse_patrones(user_input[CONF_PATRONES])
            try:
                compilados = compilar_patrones(patrones)
            except re.error:
                errors[CONF_PATRONES] = "invalid_regex"
            else:
                client = CruzRojaPlayasClient(async_get_clientsession(self.hass))
                autonomia_id = int(self.config_entry.data[CONF_AUTONOMIA_ID])
                try:
                    playas = await client.async_get_playas(autonomia_id)
                except CruzRojaPlayasError:
                    errors["base"] = "cannot_connect"
                else:
                    hay_coincidencias = any(
                        rx.search(p.etiqueta) for p in playas for rx in compilados
                    )
                    if not hay_coincidencias:
                        errors[CONF_PATRONES] = "no_matches"
                    else:
                        return self.async_create_entry(data={CONF_PATRONES: patrones})

        actuales = (user_input or {}).get(
            CONF_PATRONES, "\n".join(self.config_entry.options.get(CONF_PATRONES, []))
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_PATRONES, default=actuales): PATRONES_SELECTOR,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
