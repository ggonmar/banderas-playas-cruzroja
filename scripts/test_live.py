"""Prueba en vivo del cliente async de la integracion, sin Home Assistant.

    python scripts/test_live.py 16 gandia
    python scripts/test_live.py "comunidad valenciana" "gandia" "malvarrosa"
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import sys

import aiohttp
from test_parser import _cargar_api  # noqa: E402


async def main(argv: list[str]) -> int:
    api = _cargar_api()

    async with aiohttp.ClientSession() as session:
        client = api.CruzRojaPlayasClient(session)
        autonomias = await client.async_get_autonomias()

        if not argv:
            print("Uso: python scripts/test_live.py <autonomia> [regex ...]\n")
            for a in autonomias:
                print(f"  {a.codigo:>3}  {a.nombre}")
            return 0

        arg = argv[0]
        elegida = next(
            (a for a in autonomias if str(a.codigo) == arg or arg.lower() in a.nombre.lower()),
            None,
        )
        if elegida is None:
            print(f"Autonomia '{arg}' no encontrada.")
            return 1

        playas = await client.async_get_playas(elegida.codigo)
        print(f"== {elegida.nombre}: {len(playas)} playas con cobertura ==")

        patrones = [re.compile(p, re.IGNORECASE) for p in argv[1:]]
        if not patrones:
            for p in playas:
                print(f"  [{p.id:>4}] {p.etiqueta}")
            return 0

        seleccion = [p for p in playas if any(rx.search(p.etiqueta) for rx in patrones)]
        await client.async_fill_fichas(seleccion)
        print(f"{len(seleccion)} coincidencias\n")
        for playa in seleccion:
            print(f"--- sensor.{playa.nombre.lower().replace(' ', '_')} = {playa.bandera}")
            print(json.dumps(dataclasses.asdict(playa), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
