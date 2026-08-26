"""Valida el parser de la integracion contra las muestras HTML de scripts/samples.

    python scripts/test_parser.py

Carga api.py de forma aislada para no arrastrar la dependencia de homeassistant.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import types

RAIZ = pathlib.Path(__file__).resolve().parents[1]
COMPONENTE = RAIZ / "custom_components" / "cruzroja_playas"
SAMPLES = pathlib.Path(__file__).parent / "samples"
PAQUETE = "_cruzroja_playas_standalone"


def _cargar_api() -> types.ModuleType:
    paquete = types.ModuleType(PAQUETE)
    paquete.__path__ = [str(COMPONENTE)]
    sys.modules[PAQUETE] = paquete
    for nombre in ("const", "api"):
        spec = importlib.util.spec_from_file_location(
            f"{PAQUETE}.{nombre}", COMPONENTE / f"{nombre}.py"
        )
        assert spec and spec.loader
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = modulo
        spec.loader.exec_module(modulo)
    return sys.modules[f"{PAQUETE}.api"]


def main() -> int:
    api = _cargar_api()

    lista = api.parse_lista_playas(
        api.decode_response((SAMPLES / "lista.html").read_bytes())
    )
    print(f"lista.html -> {len(lista)} playas")
    for playa in lista[:5]:
        print(f"  [{playa.id:>4}] {playa.nombre} | {playa.municipio} | {playa.provincia}")
    assert lista, "no se ha parseado ninguna playa del listado"
    assert all(p.municipio and p.provincia for p in lista), "etiquetas mal separadas"

    bandera, atributos = api.parse_ficha_playa(
        api.decode_response((SAMPLES / "ficha.html").read_bytes())
    )
    print(f"\nficha.html -> bandera={bandera}")
    print(json.dumps(atributos, ensure_ascii=False, indent=1))
    assert bandera != "sin_bandera", "no se ha detectado la bandera"
    assert "latitude" in atributos, "no se han detectado las coordenadas"
    assert atributos.get("cobertura_desde"), "falta la fecha de cobertura"
    assert atributos.get("cobertura_hasta"), "falta el fin de cobertura"
    assert atributos.get("sillas_adaptadas") == 2, "clave de sillas adaptadas mal normalizada"
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
