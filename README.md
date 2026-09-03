# Sub Nocte

> *ibant obscuri sola sub nocte per umbram* — Virgilio, Eneida VI

Pronóstico público de la **intensidad de migración nocturna de aves** por ciudad en Europa, con alertas
**«luces fuera»** en las noches de pico. Sigue el método del [BirdCast](https://birdcast.org) de Cornell,
aplicado a los perfiles verticales de aves de la red europea de radares meteorológicos, publicados en abierto
por [Aloft](https://aloftdata.eu) (licencia CC0). Proyecto independiente, sin relación con Cornell.

Proyecto abierto y sin ánimo de lucro. Documento de diseño completo: [`docs/diseno.html`](docs/diseno.html).

## Por qué

En Estados Unidos, BirdCast predice cada noche cuántas aves migrarán y ciudades enteras apagan luces en los picos,
reduciendo colisiones con edificios. En Europa existen los datos (Aloft, ENRAM, vol2bird) y la ciencia, pero
**no existe ningún servicio público de pronóstico por ciudad ni ningún programa municipal ligado a la migración**.

## Estado (3 septiembre 2026)

- **Fase 0 completada: los radares españoles renovados de AEMET sí ven aves.** En primavera de 2026 Madrid,
  Barcelona y Cáceres muestran tráfico nocturno concentrado hacia el N-NE (61 % al NE en Barcelona), a 8-9 m/s,
  con arranque brusco a primeros de marzo tras un invierno a cero, y correlación noche a noche entre radares de
  0,4-0,5. Limitación: solo hay datos en 6 capas (unos 1.000 m sobre la antena) y hace falta el filtro de insectos
  con viento (fase 2). Informe: `output/fase0.html`.
- **Fase 1 completada: histórico 2016-2026 de España, Portugal y Francia.** 105.684 noches en 56 radares
  (`data/nightly/`), climatologías por día del año y umbrales P70/P90 por radar y temporada (`data/umbrales.csv`),
  y 25 de 29 ciudades candidatas con un radar utilizable entre 5 y 100 km (`data/ciudades.csv`). Las series
  francesas de 10-11 años son la base para entrenar el modelo. Informe: `output/fase1.html`.
- **Hallazgo que cambia el diseño: la velocidad falta en gran parte del archivo.** vol2bird deja de publicar el
  ajuste de viento en Francia desde 2021 (0 % de perfiles con velocidad en 2023-2026) y casi siempre en España;
  Portugal la conserva. Sin velocidad no hay MTR, así que la métrica operativa pasa a ser el **VID nocturno**
  (aves/km², densidad integrada), que sí forma una serie homogénea en todos los radares y años. El MTR se
  mantiene como métrica secundaria donde existe. La velocidad falta junto con la dirección y `sd_vvp`, lo que
  apunta a volúmenes sin Doppler o a vol2bird ejecutado sin él: **pendiente preguntar a Aloft** si es recuperable.
  No hay ningún análisis publicado sobre los radares españoles renovados; esta validación es propia.
- Comprobación de coherencia: el 10 % de noches más intensas concentra el 50-55 % del paso estacional en
  España, Portugal y Francia, el mismo valor que Horton et al. (2021) midieron en Estados Unidos (54 %).
- **Fase 2 completada: la meteorología anticipa las noches de paso fuerte, pero con calidad muy desigual según
  el radar.** 31.217 noches de 55 radares (2021-2026, los años con viento en la capa de vuelo), 37 variables.
  Dos modelos: uno de intensidad (regresión sobre la raíz cúbica del VID) y otro de alerta (clasificación de la
  noche por encima del percentil 90 local). Informe: `output/fase2.html`.
  - *Ciudad con radar propio y con histórico* (validación dejando fuera un año entero): correlación de rangos
    0,70 y área bajo la curva 0,74; el R² pasa de 0,19-0,41 con solo la climatología a 0,36-0,59 con el modelo.
  - *Ciudad sin radar* (validación dejando fuera el radar completo, sin darle su climatología): correlación 0,51,
    área bajo la curva 0,77 y **34 % de las noches de paso fuerte capturadas frente al 10 % del azar**, con 66 %
    de falsas alarmas emitiendo tantas alertas como noches de paso fuerte hay.
  - Por país: Portugal 0,82 de área bajo la curva y 49 % de acierto, Francia 0,79 y 36 %, España 0,74 y 27 %.
    Los mejores resultados absolutos son los tres radares de las **Azores** (Flores 0,97 y 79 % de acierto,
    Terceira 0,89 y 59 %, São Miguel 0,85 y 57 %): islas oceánicas donde el paso es muy episódico y depende casi
    solo del tiempo, y además con pocas noches, así que hay que leerlos con cautela. En el continente los mejores
    son franceses (frtre, junto a Nantes, 0,88 y 56 %; frbla, junto a Dijon, 0,88 y 45 %; frbou, Bourges, 0,87
    y 45 %) y Oporto (0,80 y 40 %);
    Portugal continental se queda en 0,75 y 33 %.
  - **Los cuatro radares españoles renovados son el caso difícil**: área bajo la curva 0,55-0,66 y 8-21 % de
    acierto. Baten al azar pero no sirven todavía para un aviso fiable; el perfil truncado a 6 capas y la
    contaminación de insectos son los sospechosos.
  - El viento a la altura a la que vuelan las aves (925, 850 y 700 hectopascales) mejora el área bajo la curva en
    0,023 de media y en 37 de los 49 radares frente a usar solo superficie: aporta, poco y de forma consistente.
- **Fase 3 en marcha: previsión operativa por ciudad y ranking de exposición a la luz.** El modelo de la fase 2
  reentrenado **sin climatología local** (la configuración validada dejando radares enteros fuera, la única
  honesta para una ciudad sin radar) se alimenta del pronóstico de Open-Meteo en las coordenadas de cada ciudad.
  La ventana nocturna se calcula con la elevación del sol, porque sin radar no hay perfiles que la marquen.
  Los niveles de aviso se cortan por los percentiles de las predicciones de **esa misma ciudad** sobre el archivo
  2021-hoy (moderado > mediana, alto > P75, muy alto > P90), así que «muy alto» significa lo mismo en Sevilla que
  en Bilbao. Informes: `output/fase3.html` (previsión) y `output/ranking.html` (exposición).
- El **ranking de exposición** multiplica el brillo artificial del cielo de cada ciudad (Atlas de Falchi 2016,
  media en un disco de 10 km) por la densidad de aves prevista, al estilo de Horton et al. (2019). Aviso: el
  atlas mide brillo visto desde el suelo, no radiancia emitida hacia arriba, es de 2015 y **su licencia prohíbe
  redistribuir los ficheros**; para la versión pública conviene la radiancia VIIRS, de dominio público (pide un
  registro gratuito en el Earth Observation Group).
- Siguiente: rutina diaria automática y web pública; ampliar a los radares alemanes, holandeses, belgas y checos,
  que tienen histórico largo en el mismo archivo y son lo que más margen de mejora tiene.

## Cómo funciona

```
Aloft (VPTS CSV) → limpieza (capas 200-3000 m, sd_vvp ≥ 2 m/s) → densidad y tasa de paso por perfil
      → tabla radar × noche → climatología y umbrales locales por radar y temporada
      → meteorología por noche (Open-Meteo: superficie 2016-hoy, altura de vuelo 2021-hoy)
      → dos modelos LightGBM (intensidad y alerta) → alertas por ciudad
```

Unidad central: **VID nocturno** en aves/km² (densidad de aves integrada en la columna, promediada entre el
crepúsculo civil y el amanecer). Se eligió frente al MTR (aves/km/noche, la unidad de BirdCast) porque el MTR
necesita la velocidad de vuelo, que falta en gran parte del archivo europeo. «Alto» = noche por encima del
percentil 90 histórico local de la temporada; «medio» = entre P70 y P90.

## Uso local

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt

# Fase 0: validación de los radares españoles (descarga ~10 meses de 6 radares)
python -m subnocte.cli fase0

# Fase 1: histórico completo de un país o de radares concretos, y climatologías
python -m subnocte.cli historico --paises es,pt,fr --start-year 2016
python -m subnocte.cli historico estjv ptprt --start-year 2019
python -m subnocte.cli climatologia
python -m subnocte.cli ciudades

# Fase 2: meteorología por radar y modelo de pronóstico
python -m subnocte.cli meteo --start-year 2016          # superficie y 100 m (reanálisis ERA5)
python -m subnocte.cli meteo-niveles --start-year 2021  # viento a 925/850/700 hPa (altura de vuelo),
                                                           # solo dentro de las ventanas migratorias
python -m subnocte.cli fase2                            # conjunto, validación, modelos e informe
python -m subnocte.cli fase2 --cache --no-niveles       # reutiliza el conjunto; solo meteorología de superficie

# Fase 3: previsión por ciudad
python -m subnocte.cli fase3-archivo                    # archivo meteorológico en el punto de cada ciudad
python -m subnocte.cli fase3-entrenar                   # modelos operativos, sin climatología local
python -m subnocte.cli fase3-umbrales                   # percentiles propios de cada ciudad
python -m subnocte.cli fase3 --dias 7                   # previsión de las próximas noches e informe
python -m subnocte.cli ranking                          # exposición a la luz artificial (necesita el atlas)

# Piezas sueltas
python -m subnocte.cli radars                       # radares del bucket y sus años
python -m subnocte.cli ingest estjv --start 2026-03-01 --end 2026-05-31
python -m subnocte.cli nightly estjv
```

Informes: `output/fase0.html` (validación de radares), `output/fase1.html` (climatologías y umbrales),
`output/fase2.html` (modelo meteorológico y validación), `output/fase3.html` (previsión por ciudad) y
`output/ranking.html` (exposición a la luz). Todos son autocontenidos: las figuras van incrustadas dentro del
propio HTML, así que se pueden enviar o abrir desde cualquier carpeta.

El atlas de luz no se versiona y no se descarga automáticamente. Para el ranking hay que bajarlo a mano una vez:

```bash
curl -sSL -o data/luces/World_Atlas_2015.zip https://datapub.gfz-potsdam.de/download/10.5880.GFZ.1.4.2016.001/World_Atlas_2015.zip
```

Datos: `data/cache/` (descargas, no versionado), `data/vpts/` (perfiles en parquet, no versionado),
`data/nightly/{radar}.parquet` (tabla nocturna, versionado), `data/umbrales.csv`, `data/climatologia_doy.csv` y
`data/ciudades.csv` (ciudad → radar útil más cercano, entre 5 y 100 km, con nivel de confianza).

## Aviso metodológico

- Los perfiles de Aloft **no tienen control de calidad** y llegan con 1-2 días de retraso. Sirven para entrenar y
  verificar, no para un mapa en vivo.
- `dens` sale de vol2bird con sección eficaz fija de 11 cm² (paseriformes en banda C). Insectos y lluvia
  contaminan la señal, sobre todo en verano y en el sur; los umbrales son percentiles locales para que la
  calibración distinta de cada radar no importe.
- Los radares españoles nuevos tienen perfil truncado (6 capas): su MTR absoluto no es comparable con otros
  radares, pero sí sus percentiles.
- La velocidad ausente **no** se trata como cero: las capas sin ajuste de viento no suman al MTR y las noches con
  menos del 50 % de la densidad con velocidad medida dejan el MTR como dato ausente (`ff_frac` en la tabla
  nocturna). Tratarla como cero hundía el MTR y concentraba falsamente el paso en el 10 % de noches (share_top10
  de 0,8-1,0 frente al 0,54 esperado).
- La red renovada de AEMET ocupa los mismos emplazamientos que la antigua (esbad/essft, esmad/estjv, esbar/esgld,
  esalm/esnjr comparten coordenadas), así que sus series son del mismo lugar aunque no de la misma calibración.

## Créditos y fuentes

Datos: Aloft / ENRAM / BALTRAD (Desmet et al. 2025, *Sci Data*), radares de AEMET, IPMA, Météo-France y demás
servicios OPERA. Método: Dokter et al. 2011, Van Doren & Horton 2018, Horton et al. 2021, Nussbaumer et al. 2021.
Licencia del código: MIT.
