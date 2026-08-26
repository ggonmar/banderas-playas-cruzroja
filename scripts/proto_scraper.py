"""Prototipo de scraper de banderas de playas de Cruz Roja Espanola.

Endpoints descubiertos (app Struts, base https://www.cruzroja.es/appjv/consPlayas/):
  GET  autonomias.do                      -> {"autonomias":[{"codigo":16,"nombre":"Comunidad Valenciana"},...]}
  GET  resultsautocomplete.do?field=provincia|municipio&input=&idautonomia=&idprovincia=
  POST listaPlayas.do    (autonomia_id, provincia_id, municipio_id, playa, action=noadaptadas)
  POST fichaPlaya.do     (id, aplicacion=consultaPlayas)
No requiere cookie de sesion. GET en fichaPlaya.do devuelve 403: hay que usar POST.
Respuestas en ISO-8859-1.
"""

from __future__ import annotations

import html as html_mod
import json
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://www.cruzroja.es/appjv/consPlayas/"
UA = "Mozilla/5.0 (compatible; HA-CruzRojaBanderas/0.1)"

FLAG_BY_LETTER = {"V": "verde", "A": "amarilla", "R": "roja", "N": "negra"}


def _request(path: str, data: dict | None = None) -> str:
    body = urllib.parse.urlencode(data, encoding="utf-8").encode() if data else None
    req = urllib.request.Request(BASE + path, data=body, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    # La cabecera siempre declara ISO-8859-1, pero fichaPlaya.do responde en UTF-8.
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("iso-8859-1")


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html_mod.unescape(text)).strip()


def autonomias() -> list[dict]:
    return json.loads(_request("autonomias.do"))["autonomias"]


LIST_ROW = re.compile(
    r"<td>\s*\d+\.\s*</td>\s*<td>(?P<label>[^<]+)</td>.*?irFichaPlaya\((?P<id>\d+)\)",
    re.S,
)
LABEL = re.compile(r"^(?P<playa>.*?)\s+-\s+(?P<municipio>.*?)\s+\((?P<provincia>[^)]*)\)\s*$")


def lista_playas(autonomia_id="", provincia_id="", municipio_id="", playa="") -> list[dict]:
    html = _request(
        "listaPlayas.do",
        {
            "autonomia_id": autonomia_id,
            "provincia_id": provincia_id,
            "municipio_id": municipio_id,
            "playa": playa,
            "action": "noadaptadas",
        },
    )
    out = []
    for m in LIST_ROW.finditer(html):
        label = _clean(m.group("label"))
        parts = LABEL.match(label)
        out.append(
            {
                "id": int(m.group("id")),
                "label": label,
                "nombre": parts.group("playa") if parts else label,
                "municipio": parts.group("municipio") if parts else None,
                "provincia": parts.group("provincia") if parts else None,
            }
        )
    return out


# --- parseo de la ficha ------------------------------------------------------
UL_ITEMS = re.compile(r"<ul id=\"listaFicha\">(.*?)</ul>", re.S)
LI = re.compile(r"<li[^>]*class=\"(?P<cls>[^\"]*)\"[^>]*>(?P<body>.*?)</li>", re.S)
FLAG_IMG = re.compile(r"ico_band_(\w+)\.gif\"[^>]*alt=\"([^\"]*)\"")
LATLNG = re.compile(r"google\.maps\.LatLng\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)")
NOMBRE = re.compile(r"capaFichaNombrePlaya\"[^>]*>Playa:</div>.*?capaFichaNombrePlaya\"[^>]*>(.*?)</div>", re.S)
OBS = re.compile(r"class=\"fichaPlayaObs\">(.*?)</li>", re.S)


def ficha_playa(id_playa: int) -> dict:
    html = _request("fichaPlaya.do", {"id": str(id_playa), "aplicacion": "consultaPlayas"})
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    # el bloque de leyenda de banderas se descarta: no es dato de la playa
    body = html.split("INDICATIVOS DE LAS BANDERAS")[0]

    data: dict = {"id": id_playa}
    n = NOMBRE.search(html)
    if n:
        data["nombre"] = _clean(n.group(1))

    for block in UL_ITEMS.findall(body):
        items = [(m.group("cls"), m.group("body")) for m in LI.finditer(block)]
        labels = [_clean(b).rstrip(":") for c, b in items if "fichaPlayaLabel" in c]
        values = [_clean(b) for c, b in items if "fichaPlayaValue" in c]
        for lab, val in zip(labels, values):
            if lab:
                data.setdefault(lab, val)

    f = FLAG_IMG.search(body)
    if f:
        data["bandera_icono"] = f.group(1)
        data["bandera"] = _clean(f.group(2))
    letra = re.search(r"class=\"marcobandera(\w+)\">(\w)</li>", body)
    if letra:
        data["bandera_letra"] = letra.group(2)
        data["bandera_color"] = letra.group(1)

    ll = LATLNG.search(html)
    if ll:
        data["latitud"], data["longitud"] = float(ll.group(1)), float(ll.group(2))

    o = OBS.search(html)
    if o:
        data["observaciones"] = _clean(o.group(1))
    return data


def main(argv: list[str]) -> int:
    ccaa = autonomias()
    if not argv:
        print("Uso: python proto_scraper.py <autonomia> [regex ...]\n")
        print("Autonomias disponibles:")
        for a in ccaa:
            print(f"  {a['codigo']:>3}  {a['nombre']}")
        return 0

    arg = argv[0]
    match = next(
        (a for a in ccaa if str(a["codigo"]) == arg or arg.lower() in a["nombre"].lower()),
        None,
    )
    if match is None:
        print(f"Autonomia '{arg}' no encontrada. Lanza el script sin argumentos para ver la lista.")
        return 1

    playas = lista_playas(autonomia_id=str(match["codigo"]))
    print(f"== {match['nombre']} ({match['codigo']}): {len(playas)} playas con cobertura ==")

    patrones = [re.compile(p, re.I) for p in argv[1:]]
    if not patrones:
        for p in playas:
            print(f"  [{p['id']:>4}] {p['label']}")
        print("\nAnade uno o mas regex para ver la ficha completa de las coincidencias.")
        return 0

    sel = [p for p in playas if any(rx.search(p["label"]) for rx in patrones)]
    print(f"{len(sel)} coinciden con {[rx.pattern for rx in patrones]}\n")
    for p in sel:
        print(json.dumps(ficha_playa(p["id"]), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
