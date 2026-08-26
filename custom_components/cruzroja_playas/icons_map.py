"""Iconos de bandera para el marcador del mapa (entity_picture).

El mapa de Home Assistant dibuja un circulo con las iniciales del nombre para
cualquier entidad con latitud/longitud que no sea ``device_tracker``/``person``.
Si la entidad expone ``entity_picture``, usa esa imagen en su lugar. Se genera
un SVG minimo en memoria (data URI) para no depender de servir archivos estaticos.
"""

from __future__ import annotations

import base64
from functools import lru_cache

from .const import FLAG_UNKNOWN

_COLOR_BY_FLAG = {
    "verde": "#2e7d32",
    "amarilla": "#f9a825",
    "roja": "#c62828",
    "negra": "#212121",
    FLAG_UNKNOWN: "#9e9e9e",
}

# Path del icono "flag" de Material Design Icons.
_FLAG_PATH = "M14.4,6L14,4H5V21H7V14H12.6L13,16H20V6H14.4Z"

_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<rect width="24" height="24" fill="#ffffff"/>'
    '<path fill="{color}" d="{path}"/>'
    "</svg>"
)


@lru_cache(maxsize=None)
def flag_entity_picture(bandera: str) -> str:
    """Data URI del icono de bandera coloreado segun el estado."""
    color = _COLOR_BY_FLAG.get(bandera, _COLOR_BY_FLAG[FLAG_UNKNOWN])
    svg = _SVG_TEMPLATE.format(color=color, path=_FLAG_PATH)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
