# BirdCast Europa (nombre provisional)

Pronóstico público de la **intensidad de migración nocturna de aves** por ciudad en Europa, con alertas
**«luces fuera»** en las noches de pico. Réplica del [BirdCast](https://birdcast.org) de Cornell sobre los
perfiles verticales de aves de la red europea de radares meteorológicos, publicados en abierto por
[Aloft](https://aloftdata.eu) (licencia CC0).

Proyecto abierto y sin ánimo de lucro. Documento de diseño completo: [`docs/diseno.html`](docs/diseno.html)
o el artefacto «BirdCast Europa» del 2 de septiembre de 2026.

## Por qué

En Estados Unidos, BirdCast predice cada noche cuántas aves migrarán y ciudades enteras apagan luces en los picos,
reduciendo colisiones con edificios. En Europa existen los datos (Aloft, ENRAM, vol2bird) y la ciencia, pero
**no existe ningún servicio público de pronóstico por ciudad ni ningún programa municipal ligado a la migración**.

## Estado (2 septiembre 2026)

- **Fase 0 completada: los radares españoles renovados de AEMET sí ven aves.** En primavera de 2026 Madrid,
  Barcelona y Cáceres muestran tráfico nocturno concentrado hacia el N-NE (61 % al NE en Barcelona), a 8-9 m/s,
  con arranque brusco a primeros de marzo tras un invierno a cero, y correlación noche a noche entre radares de
  0,4-0,5. Limitación: solo hay datos en 6 capas (unos 1.000 m sobre la antena) y hace falta el filtro de insectos
  con viento (fase 2). Informe: `output/fase0.html`.
- Fase 1 (histórico 2016-2026 de España, Portugal y Francia, climatologías y umbrales P70/P90): en marcha.

## Cómo funciona

```
Aloft (VPTS CSV) → limpieza (capas 200-3000 m, sd_vvp ≥ 2 m/s) → MTR por perfil → tabla radar × noche
      → climatología y umbrales por radar → [fase 2] modelo LightGBM con ERA5 / ECMWF Open Data → alertas por ciudad
```

Unidad central: **MTR nocturno** en aves/km/noche (tasa de tráfico de migración integrada desde el crepúsculo
civil hasta el amanecer), la misma que usa BirdCast para sus alertas. «Alto» = noche por encima del percentil 90
histórico local de la temporada; «medio» = entre P70 y P90.

## Uso local

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt

# Fase 0: validación de los radares españoles (descarga ~10 meses de 6 radares)
python -m birdcast_eu.cli fase0

# Fase 1: histórico completo de un país o de radares concretos, y climatologías
python -m birdcast_eu.cli historico --paises es,pt,fr --start-year 2016
python -m birdcast_eu.cli historico estjv ptprt --start-year 2019
python -m birdcast_eu.cli climatologia

# Piezas sueltas
python -m birdcast_eu.cli radars                       # radares del bucket y sus años
python -m birdcast_eu.cli ingest estjv --start 2026-03-01 --end 2026-05-31
python -m birdcast_eu.cli nightly estjv
```

Datos: `data/cache/` (descargas, no versionado), `data/vpts/` (perfiles en parquet, no versionado),
`data/nightly/{radar}.parquet` (tabla nocturna, versionado), `data/umbrales.csv` y `data/climatologia_doy.csv`.

## Aviso metodológico

- Los perfiles de Aloft **no tienen control de calidad** y llegan con 1-2 días de retraso. Sirven para entrenar y
  verificar, no para un mapa en vivo.
- `dens` sale de vol2bird con sección eficaz fija de 11 cm² (paseriformes en banda C). Insectos y lluvia
  contaminan la señal, sobre todo en verano y en el sur; los umbrales son percentiles locales para que la
  calibración distinta de cada radar no importe.
- Los radares españoles nuevos tienen perfil truncado (6 capas): su MTR absoluto no es comparable con otros
  radares, pero sí sus percentiles.

## Créditos y fuentes

Datos: Aloft / ENRAM / BALTRAD (Desmet et al. 2025, *Sci Data*), radares de AEMET, IPMA, Météo-France y demás
servicios OPERA. Método: Dokter et al. 2011, Van Doren & Horton 2018, Horton et al. 2021, Nussbaumer et al. 2021.
Licencia del código: MIT.
