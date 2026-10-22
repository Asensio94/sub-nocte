# Sub Nocte

> *ibant obscuri sola sub nocte per umbram* — Virgilio, Eneida VI

Pronóstico público de la **intensidad de migración nocturna de aves** por ciudad en Europa, con alertas
**«luces fuera»** en las noches de pico. Sigue el método del [BirdCast](https://birdcast.org) de Cornell,
aplicado a los perfiles verticales de aves de la red europea de radares meteorológicos, publicados en abierto
por [Aloft](https://aloftdata.eu) (licencia CC0). Proyecto independiente, sin relación con Cornell.

**Web: [asensio94.github.io/sub-nocte](https://asensio94.github.io/sub-nocte/)** — previsión de las próximas
siete noches por ciudad, actualizada cada mañana, y una sección «Cómo se calcula» que explica paso a paso, del
eco del radar al aviso, cómo sale cada cifra.

Proyecto abierto y sin ánimo de lucro. Documento de diseño completo: [`docs/design.html`](docs/design.html).

**Por qué.** En Estados Unidos, BirdCast predice cada noche cuántas aves migrarán y ciudades enteras apagan luces
en los picos, reduciendo colisiones con edificios. En Europa existen los datos (Aloft, el archivo
abierto de perfiles de aves calculados con vol2bird, el programa que separa los ecos de aves de los de lluvia e
insectos, sobre los radares meteorológicos de la red europea OPERA; ENRAM, la red científica que lo puso en marcha)
y la ciencia, pero **no existe ningún servicio público de pronóstico por ciudad ni ningún programa municipal ligado a
la migración**.

> **Estado: activo.** Se actualiza solo y sigue en desarrollo.

## Cómo funciona

```
Aloft (VPTS CSV) → limpieza (capas 200-3000 m, sd_vvp ≥ 2 m/s) → densidad y tasa de paso por perfil
      → tabla radar × noche → climatología y umbrales locales por radar y temporada
      → meteorología por noche (Open-Meteo: superficie 2016-hoy, altura de vuelo 2021-hoy)
      → dos modelos LightGBM (intensidad y alerta) → alertas por ciudad
```

1. **Del radar al perfil.** Cada servicio meteorológico (AEMET, IPMA, Météo-France…) envía sus volúmenes de radar
   a la red europea OPERA; Aloft pasa sobre ellos vol2bird, que corta el aire en capas de 200 m entre 5 y 35 km
   del radar y da en cada una la densidad de aves, su velocidad y dirección (del Doppler) y la dispersión de
   velocidades `sd_vvp`. Sub Nocte descarga esos perfiles (un fichero por radar y día).
2. **De los perfiles a la noche.** Unidad central: **VID nocturno** en aves/km² (densidad de aves integrada en la
   columna, promediada entre el crepúsculo civil y el amanecer). Se eligió frente al MTR (aves/km/noche, la unidad
   de BirdCast) porque el MTR necesita la velocidad de vuelo, que falta en gran parte del archivo europeo (ver
   «Límites»).
3. **Climatología local.** «Alto» = noche por encima del percentil 90 histórico local de la temporada; «medio» =
   entre P70 y P90 (`data/thresholds.csv`).
4. **Modelo meteorológico** (fase 2): uno de intensidad (regresión sobre la raíz cúbica del VID) y otro de alerta
   (clasificación de la noche por encima del percentil 90 local), con viento a la altura de vuelo, temperatura,
   humedad, nubosidad, lluvia, presión y día del año.
5. **Previsión por ciudad** (fase 3). El modelo de la fase 2 reentrenado **sin climatología local** (la
   configuración validada dejando radares enteros fuera, la única honesta para una ciudad sin radar) se alimenta
   del pronóstico de Open-Meteo en las coordenadas de cada ciudad. La ventana nocturna se calcula con la elevación
   del sol, porque sin radar no hay perfiles que la marquen. Los niveles de aviso se cortan por los percentiles de
   las predicciones de **esa misma ciudad y esas mismas fechas** sobre el archivo 2021-hoy, con una ventana de
   tres semanas a cada lado (moderado > mediana, alto > P75, muy alto > P90), así que «muy alto» significa lo
   mismo en Sevilla que en Bilbao y sigue significando algo en pleno pico de paso. Informes: `output/phase3.html`
   (previsión) y `output/ranking.html` (exposición).
6. **Ranking de exposición.** Multiplica el brillo artificial del cielo de cada ciudad (Atlas de Falchi 2016,
   media en un disco de 10 km) por la densidad de aves prevista, al estilo de Horton et al. (2019).
7. **Web pública y rutina diaria.** `index.html` se genera desde los mismos ficheros del repositorio
   (`python -m subnocte.cli web`) y GitHub Pages sirve la raíz de la rama, sin despliegue aparte. La rutina
   `.github/workflows/forecast.yml` corre cada mañana a las 05:20 UTC, vuelve a pedir el pronóstico, recalcula los
   niveles, regenera la página y hace commit. La web dice en el propio sitio del aviso que el nivel es **relativo a
   cada ciudad** y no una cifra absoluta de aves, y lleva un aviso de versión técnica: ninguna de estas ciudades
   tiene radar cerca con el que comprobar la previsión al día siguiente.

## Contraste / validación

Estado a 3 de septiembre de 2026, por fases:

- **Fase 0 completada: los radares españoles renovados de AEMET sí ven aves.** En primavera de 2026 Madrid,
  Barcelona y Cáceres muestran tráfico nocturno concentrado hacia el N-NE (61 % al NE en Barcelona), a 8-9 m/s,
  con arranque brusco a primeros de marzo tras un invierno a cero, y correlación noche a noche entre radares de
  0,4-0,5. Limitación: solo hay datos en 6 capas (unos 1.000 m sobre la antena) y hace falta el filtro de insectos
  con viento (fase 2). Informe: `output/phase0.html`.
- **Fase 1 completada: histórico 2016-2026 de España, Portugal y Francia.** 105.684 noches en 56 radares
  (`data/nightly/`), climatologías por día del año y umbrales P70/P90 por radar y temporada (`data/thresholds.csv`),
  y 25 de 29 ciudades candidatas con un radar utilizable entre 5 y 100 km (`data/cities.csv`). Las series
  francesas de 10-11 años son la base para entrenar el modelo. Informe: `output/phase1.html`.
- Comprobación de coherencia: el 10 % de noches más intensas concentra el 50-55 % del paso estacional en
  España, Portugal y Francia, el mismo valor que Horton et al. (2021) midieron en Estados Unidos (54 %).
- **Fase 2 completada: la meteorología anticipa las noches de paso fuerte, pero con calidad muy desigual según
  el radar.** 31.217 noches de 55 radares (2021-2026, los años con viento en la capa de vuelo), 37 variables.
  Informe: `output/phase2.html`.
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
    y 45 %) y Oporto (0,80 y 40 %); Portugal continental se queda en 0,75 y 33 %.
  - **Los cuatro radares españoles renovados son el caso difícil**: área bajo la curva 0,55-0,66 y 8-21 % de
    acierto. Baten al azar pero no sirven todavía para un aviso fiable; el perfil truncado a 6 capas y la
    contaminación de insectos son los sospechosos (ver «Límites»).
  - El viento a la altura a la que vuelan las aves (925, 850 y 700 hectopascales) mejora el área bajo la curva en
    0,023 de media y en 37 de los 49 radares frente a usar solo superficie: aporta, poco y de forma consistente.
- **Fase 3 en marcha:** previsión operativa por ciudad y ranking de exposición a la luz (ver «Cómo funciona»).
- **Verificación pública y continua.** El workflow diario hace commit de la previsión vigente, así que el
  historial del repositorio es un archivo de previsiones con su fecha de emisión. `scorecard` recupera cada una,
  descarga lo que midieron después los radares y publica el resultado en `output/scorecard.html`; lo rehace el
  workflow `.github/workflows/scorecard.yml` todos los lunes. La primera tanda (11 noches de septiembre de 2026)
  dio: orden de las noches acertado de forma débil pero consistente, tamaño infravalorado unas tres veces, y un
  aviso que en pleno pico se disparaba demasiado, que es lo que llevó a los umbrales móviles.

No hay ningún análisis publicado sobre los radares españoles renovados; esta validación es propia.

## Límites

### Dos huecos en el archivo europeo (medidos en octubre de 2026 sobre los perfiles de Aloft)

- **Techo de altura en España.** En los radares renovados de AEMET (estjv, esgld, essft, esahr) solo hay eco hasta
  unos 0,9-1 km sobre la antena (5-6 capas); por encima, `n_dbz_all` = 0, es decir, ningún dato de radar. Los
  antiguos de 2019 (esmad, esbar) llegaban a unos 0,5 km. Con el mismo programa, Oporto (ptprt) llega a 3,7 km
  sobre la antena y Nantes (frtre) a 4,7 km. Hipótesis: a la red europea solo llegan las elevaciones más bajas
  (hasta ~1,5°, que a 35 km del radar pasa a ~1 km de altura). Pendiente de confirmar con AEMET.
- **Velocidad ausente.** Lo que falta no es la densidad sino el ajuste Doppler (`ff`, `dd` y `sd_vvp` faltan
  juntos), lo que apunta a volúmenes sin Doppler o a vol2bird ejecutado sin él. Proporción de capas con aves que
  traen velocidad:

  | Radar y periodo | Con velocidad |
  |---|---:|
  | estjv, noviembre 2025 | 28 % |
  | estjv, enero 2026 (invierno, pocas aves) | 3 % |
  | estjv, abril 2026 | 54 % |
  | estjv, agosto 2026 | 49 % |
  | esgld, abril 2026 | 52 % |
  | essft, abril 2026 | 40 % |
  | esahr, abril 2026 | 42 % |
  | esmad / esbar, 2019 (red antigua) | 100 % |
  | ptprt, abril 2026 | 33 % |
  | frtre, 2019 | 100 % |
  | frtre, 2021 | 14 % |
  | frtre, 2024 | 0 % |
  | frbla, 2024 | 0 % |

  En Francia se pierde a partir de 2021 (0 % en 2023-2026); en los radares españoles renovados está en algo menos
  de la mitad de las capas con aves en primavera y verano, y casi nunca en invierno. Aun así, muchas noches no
  llegan al 50 % de la densidad con velocidad que exige el MTR (`ff_frac`, ver abajo). **Pendiente preguntar a
  Aloft** si el Doppler está en los volúmenes de origen y si se puede reprocesar 2021-2026.

### Recreación de la noche

Los mapas en vivo de [BirdCast](https://birdcast.info/migration-tools/live-migration-maps/) enseñan la noche
mientras ocurre, a partir de los volúmenes NEXRAD. En Europa los perfiles abiertos de Aloft llegan con unos dos
días de retraso, así que `flows` hace lo mismo a toro pasado. Para la Península y Francia (unos 40 radares)
genera un mapa animado de la noche, cada 20 minutos, con dos capas:

- **Densidad de aves en vuelo:** repartida alrededor de cada radar y difuminada donde ningún radar ve.
- **Flecha de vuelo medio:** sobre cada radar, indica hacia dónde iban las aves y a qué velocidad.

El informe va en `output/flows.html` y el resumen por radar en `data/flows/AAAAMMDD.csv`. Entre radares el mapa
es un suavizado, no una medida. El siguiente paso es usar el modelo meteorológico como fondo e interpolar solo la
desviación que miden los radares (*regression kriging*).

## Parques eólicos

En Países Bajos, desde mayo de 2023, los parques eólicos marinos se frenan las noches de gran paso migratorio con
una previsión de la Universidad de Ámsterdam basada en meteorología y radares de aves. En España y Portugal no existe nada parecido. `wind` aplica la previsión de la
fase 3, que funciona en cualquier punto aunque no haya radar, a los aerogeneradores en lugar de a las ciudades.

- **Zonas.** Los aerogeneradores mapeados en OpenStreetMap se agrupan en celdas de 0,5°. Una celda con al menos 10
  aerogeneradores es una zona eólica. Su punto de previsión es el centroide de esos aerogeneradores y sus umbrales
  son los percentiles propios de la zona alrededor de la misma fecha, igual que en las ciudades. Se guardan en
  `data/wind/zones.csv`, sin titulares ni nombres de parque.
- **Coste de parar.** El viento previsto a 100 m durante las horas de noche pasa por una curva de potencia genérica
  (arranque a 3 m/s, nominal a 12 m/s, corte a 25 m/s) y da la fracción de potencia que produciría la zona. Por
  debajo del 25 % parar es *barato*; desde el 50 % es *caro*.
- **Sugerencia.** Las dos mitades se cruzan en una tabla fija:
  - con alerta muy alta (P90), parar si es barato, parar en las horas punta si el coste es moderado y vigilar si
    es caro;
  - con alerta alta (P75), vigilar;
  - con cualquier alerta inferior, funcionar.

  Sobre las temporadas 2021–2026 (reanálisis ERA5, 151 zonas) esto supone unas 7,5 noches por temporada y zona
  y un 3,1 % de la producción nocturna, para el 8,8 % de la migración que predice el modelo. Parar todas las
  noches de paso muy alto habría supuesto un 12,8 %. Sale tan barato porque las noches de mucho paso suelen ser
  noches de poco viento.
- **Contraste con radar** (`wind-check`). Las 55 zonas con un radar a menos de 75 km se comparan con lo que
  midió ese radar cada noche, dentro de su propio registro desde 2021. Una noche «fuerte» es el cuarto superior
  de ese registro, así que por azar lo es el 24 %. En las noches de alerta muy alta lo fue el 63 %, en las que
  la regla dice parar el 67 % y en las de alerta baja el 12 %. Fuera quedan las zonas sin radar cerca y el
  registro anterior a 2021, medido en otra escala por varios radares.

  Sirve para ordenar noches, no es una orden de operación.

Límites que hay que tener presentes:
- La densidad prevista es la de toda la columna que ven los radares (de ~200 m a 3 km), no la de la altura del
  rotor.
- La mortalidad documentada en parques eólicos españoles es sobre todo de planeadoras diurnas (buitres) y de
  murciélagos, y esta previsión no cubre ninguno de los dos grupos.
- Los radares renovados de AEMET validan peor (AUC 0,55–0,66).

**Archivo meteorológico.** Los umbrales de cada zona necesitan cinco temporadas de meteorología en su punto. Open-Meteo
cuenta cada punto como una petición aparte y su cupo gratuito no da para 150 zonas, así que el archivo sale de
ERA5 (Copernicus): se descarga una caja por mes que cubre todas las zonas y se lee en el punto de cada una, con las
mismas columnas y unidades que Open-Meteo. ERA5 es un reanálisis y el modelo se entrenó con previsiones
archivadas, así que `wind-compare` comprueba en las zonas que tienen las dos fuentes que dan las mismas noches
intensas. Hace falta una cuenta gratuita en el Climate Data Store, aceptar la licencia de los dos conjuntos ERA5
(niveles únicos y de presión) y el token en `~/.cdsapirc`.

El siguiente paso es usar la cota de cada zona (`ground_m`, en muchos casos 800–1500 m s.n.m.) para leer la
densidad de la banda de altura que los radares sí ven a esa cota.

## Rutas

`rutas.html` (y `en/routes.html`) es un mapa animado de **por dónde vuelan** las aves de noche sobre la península
y Francia, con los parques eólicos encima. Tiene tres vistas: las próximas noches, el histórico de otoño y el de
primavera.

- **De dónde sale la dirección.** vol2bird da, por cada capa de 200 m, la velocidad de las aves sobre el suelo
  (u, v). `routes-archive` vuelve a leer los ficheros mensuales de Aloft de los meses de paso que publican ese
  vector y guarda por radar y noche el **vector de tráfico**: Σ densidad × velocidad × grosor × tiempo, es decir,
  cuántas aves cruzaron cada km de frente y hacia dónde. El resultado está en `data/routes/flight_nights.parquet`.
- **De noches a ruta** (`routes`). Por estación y temporada se suman los vectores. La dirección de la suma es la
  ruta y su constancia (0–1) indica si las noches coinciden. Se descartan las noches con poco vector, las de menos
  de dos horas de radar y las de más de 25 m/s sobre el suelo, que suelen ser lluvia o ecos arrastrados. Para la
  dirección, ninguna noche pesa más que el percentil 95 de su estación.
- **En el mapa**, las líneas son un suavizado gaussiano entre radares (130 km) que se apaga a 320 km del radar más
  cercano: donde no hay radar, no hay línea. El color muestra el paso previsto por el modelo de Sub Nocte en cada
  zona eólica y ciudad: la previsión de la noche o la media de la temporada. Al pulsar un parque se ven su
  sugerencia de la noche, la ruta que pasa por encima, su puesto por paso medio y cómo acierta el modelo con el
  radar más cercano.
- **Huecos.** Los radares españoles renovados y los franceses desde 2021 apenas publican vector, así que la ruta
  española se apoya en 2018-2020, la francesa en 2016-2022 y la portuguesa en 2019-2026. La dirección no depende
  de la calibración de cada radar; la cantidad sí.

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
- El atlas de luz mide brillo visto desde el suelo, no radiancia emitida hacia arriba, es de 2015 y **su licencia
  prohíbe redistribuir los ficheros**; para la versión pública conviene la radiancia VIIRS, de dominio público
  (pide un registro gratuito en el Earth Observation Group).

## Pendiente

- Ampliar a los radares alemanes, holandeses, belgas y checos, que tienen histórico largo en el mismo archivo y son
  lo que más margen de mejora tiene.
- Avisos por Telegram.
- Cambiar la capa de luz a VIIRS.
- Consultar a AEMET por el techo de altura y a Aloft por la velocidad ausente (ver «Límites»).
- Conseguir datos con pocas horas de retraso: propuesta a SEO/BirdLife y AEMET ([español](docs/proposal/proposal_es.md))
  y a Aloft y OPERA ([English](docs/proposal/proposal_en.md)).

## Uso

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt

# Fase 0: validación de los radares españoles (descarga ~10 meses de 6 radares)
python -m subnocte.cli phase0

# Fase 1: histórico completo de un país o de radares concretos, y climatologías
python -m subnocte.cli history --countries es,pt,fr --start-year 2016
python -m subnocte.cli history estjv ptprt --start-year 2019
python -m subnocte.cli climatology
python -m subnocte.cli cities

# Fase 2: meteorología por radar y modelo de pronóstico
python -m subnocte.cli weather --start-year 2016          # superficie y 100 m (reanálisis ERA5)
python -m subnocte.cli weather-levels --start-year 2021  # viento a 925/850/700 hPa (altura de vuelo),
                                                           # solo dentro de las ventanas migratorias
python -m subnocte.cli phase2                            # conjunto, validación, modelos e informe
python -m subnocte.cli phase2 --cache --no-levels       # reutiliza el conjunto; solo meteorología de superficie

# Fase 3: previsión por ciudad
python -m subnocte.cli phase3-archive                    # archivo meteorológico en el punto de cada ciudad
python -m subnocte.cli phase3-train                   # modelos operativos, sin climatología local
python -m subnocte.cli phase3-thresholds                   # percentiles propios de cada ciudad
python -m subnocte.cli phase3 --days 7                   # previsión de las próximas noches e informe
python -m subnocte.cli ranking                          # exposición a la luz artificial (necesita el atlas)
python -m subnocte.cli scorecard                        # verifica las previsiones ya publicadas
python -m subnocte.cli web                              # regenera index.html, la web pública

# Parques eólicos: previsión nocturna por zona eólica y coste de parar
python -m subnocte.cli wind-zones                        # aerogeneradores de OSM, cota del terreno y zonas
python -m subnocte.cli wind-era5                         # archivo ERA5 de todas las zonas (necesita ~/.cdsapirc)
python -m subnocte.cli wind-archive                      # o el de Open-Meteo, zona a zona (cupo gratuito)
python -m subnocte.cli wind-compare                      # ¿dan las dos fuentes las mismas noches?
python -m subnocte.cli wind-thresholds --source era5     # percentiles propios de cada zona
python -m subnocte.cli wind --days 7                     # previsión, coste de parar e informe
# Rutas: dirección de vuelo medida por los radares y mapa con los parques
python -m subnocte.cli routes-archive                    # vectores de tráfico por noche (una vez; reanudable)
python -m subnocte.cli routes                            # climatología de rutas y rutas.html
# Recreación de una noche: dónde estaban las aves, cada 20 minutos
python -m subnocte.cli flows                             # la última noche completa (unos 3 días atrás)
python -m subnocte.cli flows --night 2026-09-24

# Piezas sueltas
python -m subnocte.cli radars                       # radares del bucket y sus años
python -m subnocte.cli ingest estjv --start 2026-03-01 --end 2026-05-31
python -m subnocte.cli nightly estjv
```

Informes (en inglés): `output/phase0.html` (validación de radares), `output/phase1.html` (climatologías y umbrales),
`output/phase2.html` (modelo meteorológico y validación), `output/phase3.html` (previsión por ciudad), `output/wind.html` (parques eólicos), `rutas.html` (mapa de rutas, en español e inglés),
`output/ranking.html` (exposición a la luz) y `output/scorecard.html` (verificación de lo ya publicado). Todos son autocontenidos: las figuras van incrustadas dentro del
propio HTML, así que se pueden enviar o abrir desde cualquier carpeta.

El atlas de luz no se versiona y no se descarga automáticamente. Para el ranking hay que bajarlo a mano una vez:

```bash
curl -sSL -o data/lights/World_Atlas_2015.zip https://datapub.gfz-potsdam.de/download/10.5880.GFZ.1.4.2016.001/World_Atlas_2015.zip
```

## Datos que se guardan

| Fichero | Contenido |
|---|---|
| `data/cache/` | descargas (no versionado) |
| `data/vpts/` | perfiles en parquet (no versionado) |
| `data/nightly/{radar}.parquet` | tabla nocturna por radar (versionado) |
| `data/thresholds.csv` | umbrales P70/P90 por radar y temporada |
| `data/climatology_doy.csv` | climatología por día del año |
| `data/cities.csv` | ciudad → radar útil más cercano, entre 5 y 100 km, con nivel de confianza |
| `data/routes/flight_nights.parquet` | vector de tráfico por radar y noche de paso (versionado) |
| `data/routes/climatology.csv` | dirección, constancia, velocidad y altitud por estación y temporada |
| `signals.json` | previsión de la primera noche por venir en cada ciudad española, para [Estado de las IBA](https://asensio94.github.io/estado-iba/) según su [contrato](https://github.com/Asensio94/estado-iba/blob/main/CONTRATO.md); lo escribe `cli web` |

## Fuentes y licencias

Datos: Aloft / ENRAM / BALTRAD (Desmet et al. 2025, *Sci Data*), radares de AEMET, IPMA, Météo-France y demás
servicios OPERA. Método: Dokter et al. 2011, Van Doren & Horton 2018, Horton et al. 2021, Nussbaumer et al. 2021.
Aerogeneradores: © colaboradores de OpenStreetMap (ODbL), vía Overpass; cota del terreno: Copernicus DEM vía
Open-Meteo. Archivo meteorológico de las zonas eólicas: ERA5 (Hersbach et al. 2020), Copernicus Climate Change
Service.
Licencia del código: MIT.

---

Forma parte de un conjunto de proyectos hermanos:
[Observatorio de alegaciones](https://asensio94.github.io/observatorio-alegaciones/) ·
[Vigía de incendios](https://asensio94.github.io/vigia-incendios/) ·
[Centinela Natura](https://asensio94.github.io/centinela-natura/) ·
[Vigilancia de humedales](https://asensio94.github.io/vigilancia-humedales/) ·
[Riesgo de tendidos para aves](https://asensio94.github.io/riesgo-tendidos-aves/) ·
[Grafo de promotores](https://asensio94.github.io/grafo-promotores/) ·
[Cartera de las cotizadas](https://asensio94.github.io/cartera-cotizadas/) ·
[Cuaderno de campo](https://asensio94.github.io/cuaderno-campo/) ·
[Caudal ecológico](https://asensio94.github.io/caudal-ecologico/).
