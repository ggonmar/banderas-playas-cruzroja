"""Constantes de la integracion Banderas de Playas (Cruz Roja)."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "cruzroja_playas"

CONF_AUTONOMIA_ID: Final = "autonomia_id"
CONF_AUTONOMIA_NOMBRE: Final = "autonomia_nombre"
CONF_PATRONES: Final = "patrones"

DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=15)

ATTRIBUTION: Final = "Datos facilitados por Cruz Roja Española"

FLAG_UNKNOWN: Final = "sin_bandera"

#: Estados posibles del sensor, derivados de la letra que publica Cruz Roja.
FLAG_STATES: Final = ["verde", "amarilla", "roja", "negra", FLAG_UNKNOWN]

FLAG_BY_LETTER: Final = {
    "V": "verde",
    "A": "amarilla",
    "R": "roja",
    "N": "negra",
}
