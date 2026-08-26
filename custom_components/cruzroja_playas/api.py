"""Cliente asincrono para la consulta de playas de Cruz Roja Española.

La aplicacion original (Struts) no expone una API publica, pero si varios
endpoints estables que se pueden consumir sin sesion ni JavaScript:

    GET  autonomias.do   -> JSON con las comunidades autonomas con cobertura
    POST listaPlayas.do  -> HTML con las playas de una autonomia/provincia/municipio
    POST fichaPlaya.do   -> HTML con la ficha completa de una playa

Notas importantes descubiertas durante la investigacion:
  * ``fichaPlaya.do`` devuelve 403 si se invoca por GET: hay que usar POST.
  * Todas las respuestas declaran ISO-8859-1, pero solo lo cumplen ``autonomias.do``
    y ``listaPlayas.do``; ``fichaPlaya.do`` responde en UTF-8. Ver :func:`decode_response`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from bs4 import BeautifulSoup, Comment, Tag

from .const import FLAG_BY_LETTER, FLAG_UNKNOWN

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.cruzroja.es/appjv/consPlayas/"
USER_AGENT = "Mozilla/5.0 (compatible; HomeAssistant-cruzroja_playas)"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

#: Peticiones simultaneas de fichas. Se mantiene bajo para no saturar el origen.
MAX_CONCURRENT_FICHAS = 4

# El nombre puede contener " - " (ej. "GANDIA - NORD"): se corta por el ultimo separador.
_LABEL_RE = re.compile(r"^(?P<playa>.*)\s+-\s+(?P<municipio>.*?)\s+\((?P<provincia>[^)]*)\)\s*$")
_LATLNG_RE = re.compile(r"google\.maps\.LatLng\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)")
_FICHA_ID_RE = re.compile(r"irFichaPlaya\((\d+)\)")
_BANDERA_CLASS_RE = re.compile(r"^marcobandera(\w+)$")

_BOOL_VALUES = {"sí": True, "si": True, "no": False}

#: Nombres mas legibles para los campos que llegan con etiquetas largas.
_KEY_ALIASES = {
    "ayuntamiento_municipio": "municipio",
    "numero_de_puestos": "puestos",
    "sillas_de_proximidad": "sillas_proximidad",
    "torres_de_vigilancia": "torres_vigilancia",
    "torres_de_intervencion": "torres_intervencion",
    "servicio_ayuda_bano": "servicio_ayuda_bano",
    "sello_aenor_iso_9001": "aenor_iso_9001",
    "sello_aenor_iso_14001": "aenor_iso_14001",
    "n_de_sillas_adaptadas": "sillas_adaptadas",
    "no_de_sillas_adaptadas": "sillas_adaptadas",
    "atencion_a_discapacitados": "atencion_discapacitados",
    "acceso_para_discapacitados": "acceso_discapacitados",
    "servicios_wc": "servicios_wc",
    "zonas_de_sombra": "zonas_sombra",
}

_DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def decode_response(raw: bytes) -> str:
    """Decodifica una respuesta cuya codificacion declarada no es fiable.

    La cabecera siempre dice ISO-8859-1, pero ``fichaPlaya.do`` responde en UTF-8.
    Se intenta UTF-8 estricto y se cae a ISO-8859-1, que nunca falla.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("iso-8859-1")


class CruzRojaPlayasError(Exception):
    """Error generico al hablar con la web de Cruz Roja."""


@dataclass(slots=True)
class Autonomia:
    """Comunidad autonoma con cobertura activa."""

    codigo: int
    nombre: str


@dataclass(slots=True)
class Playa:
    """Playa devuelta por el listado de busqueda."""

    id: int
    etiqueta: str
    nombre: str
    municipio: str | None = None
    provincia: str | None = None
    bandera: str = FLAG_UNKNOWN
    atributos: dict[str, Any] = field(default_factory=dict)


def _slug(text: str) -> str:
    """Convierte una etiqueta del HTML en una clave snake_case sin acentos."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text.lower())).strip("_")


def _coerce(value: str) -> Any:
    """Normaliza los valores de texto a bool/int cuando procede."""
    stripped = value.strip()
    if stripped.lower() in _BOOL_VALUES:
        return _BOOL_VALUES[stripped.lower()]
    if stripped.isdigit():
        return int(stripped)
    return stripped


def _text(node: Tag) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def _pairs(container: Tag) -> dict[str, Any]:
    """Extrae los pares etiqueta/valor de los ``<ul id="listaFicha">`` de un bloque."""
    data: dict[str, Any] = {}
    for ul in container.find_all("ul", id="listaFicha"):
        labels: list[str] = []
        values: list[str] = []
        for li in ul.find_all("li", recursive=False):
            classes = li.get("class") or []
            if any(c.startswith("fichaPlayaLabel") for c in classes):
                labels.append(_text(li).rstrip(":"))
            elif any(c.startswith("fichaPlayaValue") for c in classes):
                values.append(_text(li))
        for label, value in zip(labels, values):
            if not label:
                continue
            key = _KEY_ALIASES.get(_slug(label), _slug(label))
            data.setdefault(key, _coerce(value))
    return data


def _parse_bandera(container: Tag) -> str:
    """Devuelve el color de bandera a partir del recuadro con la letra (V/A/R/N)."""
    for li in container.find_all("li"):
        for css in li.get("class") or []:
            if _BANDERA_CLASS_RE.match(css):
                return FLAG_BY_LETTER.get(_text(li).upper()[:1], FLAG_UNKNOWN)
    return FLAG_UNKNOWN


def _parse_horario_atencion(soup: BeautifulSoup) -> dict[str, Any]:
    """Horario y dias de atencion a discapacitados (bloque sin pares etiqueta/valor)."""
    ul = soup.find("ul", id="listaFichaHorario")
    if not isinstance(ul, Tag):
        return {}

    data: dict[str, Any] = {}
    items = ul.find_all("li", recursive=False)
    if len(items) > 1:
        horario = _text(items[1])
        if horario and not horario.lower().startswith("no hay datos"):
            data["horario_atencion_discapacitados"] = horario

    tabla = ul.find("table")
    if isinstance(tabla, Tag):
        valores = [_text(td) for td in tabla.find_all("td", class_="value")]
        if len(valores) == len(_DIAS):
            data["dias_atencion_discapacitados"] = [
                dia for dia, val in zip(_DIAS, valores) if _coerce(val) is True
            ]
    return data


def parse_lista_playas(html: str) -> list[Playa]:
    """Parsea el HTML de ``listaPlayas.do``."""
    soup = BeautifulSoup(html, "html.parser")
    playas: list[Playa] = []
    for boton in soup.find_all("input", onclick=_FICHA_ID_RE):
        fila = boton.find_parent("tr")
        if not isinstance(fila, Tag):
            continue
        match = _FICHA_ID_RE.search(boton.get("onclick", ""))
        celdas = fila.find_all("td")
        if not match or len(celdas) < 2:
            continue
        etiqueta = _text(celdas[1])
        partes = _LABEL_RE.match(etiqueta)
        playas.append(
            Playa(
                id=int(match.group(1)),
                etiqueta=etiqueta,
                nombre=partes.group("playa").strip() if partes else etiqueta,
                municipio=partes.group("municipio").strip() if partes else None,
                provincia=partes.group("provincia").strip() if partes else None,
            )
        )
    return playas


def parse_ficha_playa(html: str) -> tuple[str, dict[str, Any]]:
    """Parsea el HTML de ``fichaPlaya.do``: devuelve ``(bandera, atributos)``."""
    soup = BeautifulSoup(html, "html.parser")
    for comentario in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comentario.extract()

    data: dict[str, Any] = {}

    cabecera = soup.find("table", id="infFicha")
    if isinstance(cabecera, Tag):
        # La ficha trae el nombre bien capitalizado; el listado lo da en mayusculas.
        titulos = cabecera.find_all("div", class_="capaFichaNombrePlaya")
        if len(titulos) > 1:
            data["nombre"] = _text(titulos[1])

        # El fieldset de campañas reutiliza las etiquetas Desde/Hasta: se aisla antes.
        campanya = cabecera.find("fieldset")
        if isinstance(campanya, Tag):
            campanya.extract()
            textos = [
                _text(li)
                for li in campanya.find_all("li")
                if any(c.startswith("fichaPlayaValue") for c in (li.get("class") or []))
            ]
            fechas = [t for t in textos if re.fullmatch(r"\d{2}/\d{2}/\d{4}", t)]
            descripcion = [t for t in textos if t not in fechas]
            if descripcion:
                data["campanya"] = " / ".join(descripcion)
            if len(fechas) >= 2:
                data["campanya_desde"], data["campanya_hasta"] = fechas[0], fechas[1]
        data.update(_pairs(cabecera))
        if "hasta" in data:
            data["cobertura_hasta"] = data.pop("hasta")

    bandera = FLAG_UNKNOWN
    # capaFichaDer contiene la leyenda de banderas, que no es informacion de la playa.
    izquierda = soup.find(id="capaFichaIzq")
    if isinstance(izquierda, Tag):
        bandera = _parse_bandera(izquierda)
        data.update(_pairs(izquierda))

    for bloque_id in ("capaFichaIzqDisca", "capaFichaDerDisca"):
        bloque = soup.find(id=bloque_id)
        if isinstance(bloque, Tag):
            data.update(_pairs(bloque))

    data.update(_parse_horario_atencion(soup))

    observaciones = soup.find("li", class_="fichaPlayaObs")
    if isinstance(observaciones, Tag):
        data["observaciones"] = _text(observaciones)

    if coords := _LATLNG_RE.search(html):
        data["latitude"] = float(coords.group(1))
        data["longitude"] = float(coords.group(2))

    return bandera, data


class CruzRojaPlayasClient:
    """Cliente HTTP de la consulta de playas."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _request(self, path: str, data: dict[str, str] | None = None) -> str:
        try:
            async with self._session.request(
                "POST" if data else "GET",
                BASE_URL + path,
                data=data,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
            ) as response:
                response.raise_for_status()
                raw = await response.read()
        except TimeoutError as err:
            raise CruzRojaPlayasError(f"Tiempo de espera agotado en {path}") from err
        except aiohttp.ClientError as err:
            raise CruzRojaPlayasError(f"Error de conexion en {path}: {err}") from err

        return decode_response(raw)

    async def async_get_autonomias(self) -> list[Autonomia]:
        """Comunidades autonomas con cobertura activa."""
        payload = await self._request("autonomias.do")
        try:
            crudo = json.loads(payload)["autonomias"]
        except (ValueError, KeyError, TypeError) as err:
            raise CruzRojaPlayasError("Respuesta inesperada en autonomias.do") from err
        return [Autonomia(codigo=int(a["codigo"]), nombre=a["nombre"]) for a in crudo]

    async def async_get_playas(self, autonomia_id: int) -> list[Playa]:
        """Playas con cobertura activa en una comunidad autonoma."""
        html = await self._request(
            "listaPlayas.do",
            {"autonomia_id": str(autonomia_id), "action": "noadaptadas"},
        )
        return parse_lista_playas(html)

    async def async_fill_ficha(self, playa: Playa) -> None:
        """Completa una playa con los datos de su ficha."""
        html = await self._request(
            "fichaPlaya.do", {"id": str(playa.id), "aplicacion": "consultaPlayas"}
        )
        playa.bandera, playa.atributos = parse_ficha_playa(html)
        # La ficha trae los nombres bien capitalizados; el listado los da en mayusculas.
        for campo in ("nombre", "municipio", "provincia"):
            if valor := playa.atributos.pop(campo, None):
                setattr(playa, campo, valor)

    async def async_fill_fichas(self, playas: list[Playa]) -> None:
        """Completa varias playas limitando la concurrencia."""
        semaforo = asyncio.Semaphore(MAX_CONCURRENT_FICHAS)

        async def _worker(playa: Playa) -> None:
            async with semaforo:
                await self.async_fill_ficha(playa)

        resultados = await asyncio.gather(
            *(_worker(playa) for playa in playas), return_exceptions=True
        )
        for playa, resultado in zip(playas, resultados):
            if isinstance(resultado, Exception):
                _LOGGER.warning("No se pudo leer la ficha de %s: %s", playa.nombre, resultado)
