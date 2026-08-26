# Banderas de Playas (Cruz Roja) para Home Assistant

[![hacs][hacs-badge]][hacs-url]
[![validate][validate-badge]][validate-url]
[![release][release-badge]][release-url]
[![license][license-badge]](LICENSE)

Integración personalizada (HACS) que publica el **estado de la bandera** de las playas
españolas vigiladas por Cruz Roja, a partir de la web pública
[Estado de las Playas](https://www.cruzroja.es/appjv/consPlayas/consultaInicio.do).

Cada playa seleccionada genera un sensor cuyo estado es el color de la bandera
(`verde`, `amarilla`, `roja`, `negra` o `sin_bandera`) y que expone el resto de la
ficha como atributos: medusas, horario, cobertura, puestos de socorro, sillas de
proximidad, accesibilidad, observaciones y coordenadas.

## Instalación

### HACS (recomendado)

[![Abrir en HACS][my-hacs-badge]][my-hacs-url]

Si el repositorio aún no está en la tienda por defecto: HACS → menú ⋮ →
*Repositorios personalizados* → añade `https://github.com/ggonmar/banderas-playas-cruzroja`
con categoría **Integración** → instala **Banderas de Playas (Cruz Roja)** → reinicia Home Assistant.

### Manual

Copia `custom_components/cruzroja_playas` en tu carpeta `config/custom_components` y reinicia.


## Configuración

*Ajustes* → *Dispositivos y servicios* → *Añadir integración* → **Banderas de Playas (Cruz Roja)**.

1. Elige la **comunidad autónoma** del desplegable (solo aparecen las que tienen cobertura activa).
2. Escribe una **expresión regular por línea**. Se comparan, sin distinguir mayúsculas ni
   acentos del patrón, contra el texto `PLAYA - MUNICIPIO (PROVINCIA)` del listado.

Ejemplo para la Comunidad Valenciana:

```
gandia
malvarrosa
j.vea
```

crea sensores para las cuatro playas de Gandia, la Malvarrosa y las de Jávea/Xàbia.

Los patrones se pueden editar después en *Configurar*, sin volver a dar de alta la integración.

## Entidades

| | |
|---|---|
| Estado | `verde` · `amarilla` · `roja` · `negra` · `sin_bandera` |
| Atributos | `municipio`, `provincia`, `autonomia`, `medusas`, `horario`, `cobertura_desde`, `cobertura_hasta`, `puestos`, `torres_vigilancia`, `torres_intervencion`, `sillas_proximidad`, `servicio_ayuda_bano`, `atencion`, accesibilidad (`rampas`, `duchas`, `pasarelas`, `sillas_adaptadas`, …), `observaciones`, `latitude`, `longitude` |

Los datos se refrescan cada 15 minutos. Fuera de la temporada de cobertura la playa
desaparece del listado oficial y su sensor pasa a `unavailable`.

### Ejemplo de automatización

```yaml
automation:
  - alias: Aviso de bandera roja
    triggers:
      - trigger: state
        entity_id: sensor.playa_gandia_nord
        to: roja
    actions:
      - action: notify.movil
        data:
          message: "Bandera roja en {{ state_attr(trigger.entity_id, 'nombre') }}"
```

## Desarrollo

`scripts/` contiene utilidades para trabajar sin Home Assistant:

```bash
python scripts/proto_scraper.py 16 gandia   # prototipo independiente, sin dependencias
python scripts/test_parser.py               # valida el parser contra scripts/samples
python scripts/test_live.py 16 gandia       # prueba el cliente async contra la web real
```

Los dos últimos requieren `beautifulsoup4` y `aiohttp`.

## Aviso

Proyecto no oficial, sin relación con Cruz Roja Española. Los datos son propiedad de
Cruz Roja Española y se consultan con la misma frecuencia con la que lo haría una persona.
La bandera mostrada puede no reflejar la situación real de la playa en cada momento:
**haz caso siempre a la señalización y al personal de socorrismo**.

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://hacs.xyz
[validate-badge]: https://github.com/ggonmar/banderas-playas-cruzroja/actions/workflows/validate.yml/badge.svg
[validate-url]: https://github.com/ggonmar/banderas-playas-cruzroja/actions/workflows/validate.yml
[release-badge]: https://img.shields.io/github/v/release/ggonmar/banderas-playas-cruzroja
[release-url]: https://github.com/ggonmar/banderas-playas-cruzroja/releases
[license-badge]: https://img.shields.io/github/license/ggonmar/banderas-playas-cruzroja
[my-hacs-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[my-hacs-url]: https://my.home-assistant.io/redirect/hacs_repository/?owner=ggonmar&repository=banderas-playas-cruzroja&category=integration

