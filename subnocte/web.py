"""Public website: one static page per language, generated from the data files in this repository.

There is no server and no database. The daily routine re-runs the forecast, regenerates `index.html`
(Spanish) and `en/index.html` (English) and commits; Pages serves the root of the branch. Everything the
page claims comes from versioned files, so anyone can reproduce it.

The page follows one honesty rule: **the alert level is relative to each city**, not an absolute number of
birds, and that is said right where the alert is shown, not in a footnote.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from .logo import LOGO_SVG, favicon_link

LANGS = ("es", "en")

COLOR = {"low": "#e9edf2", "moderate": "#ffd98e", "high": "#f08c1e", "very high": "#b32d1f"}
TEXT = {"very high": "#fff", "high": "#3a2100"}
WEIGHT = {"low": 0, "moderate": 1, "high": 2, "very high": 3}

# levels and seasons travel through the data in English; the page shows them in its own language
LEVEL_NAME = {"es": {"low": "bajo", "moderate": "moderado", "high": "alto", "very high": "muy alto"},
              "en": {n: n for n in COLOR}}
SEASON_NAME = {"es": {"spring": "primavera", "autumn": "otoño"},
               "en": {"spring": "spring", "autumn": "autumn"}}
COUNTRY = {"es": {"ES": "España", "PT": "Portugal", "FR": "Francia"},
           "en": {"ES": "Spain", "PT": "Portugal", "FR": "France"}}
MONTHS = {"es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
          "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]}
MONTHS_LONG = {"es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                      "septiembre", "octubre", "noviembre", "diciembre"],
               "en": ["January", "February", "March", "April", "May", "June", "July", "August",
                      "September", "October", "November", "December"]}
DAYS = {"es": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"],
        "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}

BASE = "https://asensio94.github.io/sub-nocte/"
REPO = "https://github.com/Asensio94/sub-nocte"

FAVICON = favicon_link("#4a4fb5", "#9a9ef0")
FONTS = ("https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700"
         "&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap")

# Shared look of the sibling projects, inlined so the page stays a single self-contained file.
COMMON_CSS = (Path(__file__).with_name("common.css")).read_text(encoding="utf-8")

CSS = """
:root{--accent:#4a4fb5;--accent-dark:#9a9ef0;--cell-gap:var(--paper)}
.site-header,.method,.site-footer,.wrap{max-width:1000px}
.wrap{margin:0 auto;padding:0 16px}
.site-header{position:relative}
.site-header .verse{margin:-6px 0 0;font-style:italic;color:var(--muted);font-size:15px}
.lang{position:absolute;top:16px;right:16px;font:600 13px/1 var(--font-title);text-transform:uppercase;letter-spacing:.08em}
.lang a,.lang span{display:inline-block;padding:5px 9px 4px;border:1.5px solid var(--line);text-decoration:none}
.lang span{border-color:var(--accent);color:var(--accent)}
.beta-note{background:var(--paper);border:1px solid var(--line);border-left:4px solid var(--accent);padding:12px 16px;margin:8px 0 22px;font-size:15px}
h2{margin:38px 0 6px;font:700 28px/1 var(--font-title);text-transform:uppercase;letter-spacing:.03em}
h2+p.sub{margin:0 0 16px}
p.sub{color:var(--muted);font-size:15px}
h3{margin:26px 0 8px;font:600 18px/1.2 var(--font-title);text-transform:uppercase;letter-spacing:.06em}
table{border-collapse:collapse;width:100%;font-size:14.5px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:right}
th{color:var(--muted);font:600 13px/1.25 var(--font-title);text-transform:uppercase;letter-spacing:.05em;text-align:right}
td{font-variant-numeric:tabular-nums}
td:first-child,th:first-child{text-align:left}
.scroll,.cal{overflow-x:auto;margin:8px 0 6px}
.cal table{width:auto;min-width:100%}
.cal td.n{text-align:center;font:12px/1.3 var(--font-data);white-space:nowrap;border:2px solid var(--cell-gap)}
.cal th{text-align:center}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin:6px 0 0}
.legend span i{display:inline-block;width:13px;height:13px;vertical-align:-2px;margin-right:5px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:16px 0}
.cards div{background:var(--paper);border:1px solid var(--line);box-shadow:var(--shadow);padding:14px 16px}
.cards b{display:block;font:600 17px/1.2 var(--font-title);text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px}
.cards p{margin:0;font-size:15px;color:var(--muted)}
ul{padding-left:20px}li{margin:5px 0}
.pill{display:inline-block;border:1px solid var(--line);padding:1px 7px;font:600 11.5px/1.4 var(--font-title);text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.method{padding-top:8px}
.method ol.steps{list-style:none;counter-reset:step;padding:0;margin:18px 0 0}
.method ol.steps>li{counter-increment:step;position:relative;padding:0 0 0 52px;margin:0 0 22px;max-width:none}
.method ol.steps>li::before{content:counter(step);position:absolute;left:0;top:-2px;width:36px;height:36px;display:grid;place-items:center;border:2px solid var(--accent);color:var(--accent);font:700 20px/1 var(--font-data)}
.method ol.steps h3{margin:4px 0 6px}
.method ol.steps p{margin:0 0 8px}
.method .gap{background:var(--paper);border:1px solid var(--line);box-shadow:var(--shadow);padding:16px;margin:18px 0}
.method .gap h3{margin-top:0}
.method figure{margin:12px 0 10px}
.method figcaption{color:var(--muted);font-size:14px;max-width:72ch}
.beam text{font:12px var(--font-data);fill:var(--muted)}
.beam .lbl{font:600 12px var(--font-title);letter-spacing:.06em;text-transform:uppercase;fill:var(--ink)}
.formula{font:14.5px/1.5 var(--font-data);background:var(--paper);border:1px solid var(--line);padding:8px 12px;display:inline-block;max-width:100%;overflow-x:auto}
.data-note{font-size:14.5px}
@media (max-width:640px){.lang{position:static;justify-self:start}h2{font-size:23px}.method ol.steps>li{padding-left:44px}}
"""

# The whole prose of the page, in both languages. It is kept complete and literal for each language instead
# of being assembled from pieces: it is longer, but it reads and gets corrected as a text, which is what it is.
COPY: dict[str, dict[str, str]] = {
    "es": {
        "title": "Sub Nocte · migración nocturna de aves en Europa",
        "description": "Previsión por ciudad de la intensidad de migración nocturna de aves en Europa, "
                       "con avisos de luces fuera, sobre los perfiles de radar abiertos de Aloft.",
        "other_lang": "English",
        "claim": "Cada noche de primavera y de otoño, millones de aves cruzan Europa en la oscuridad. Unas "
                 "pocas noches concentran la mitad del paso. Esta página intenta decir <b>cuáles</b>, ciudad "
                 "por ciudad, para que se puedan apagar las luces justo esas noches.",
        "beta": "<b>Versión técnica, no un servicio en producción.</b> El modelo está validado (ver más "
                "abajo) pero ninguna de estas ciudades tiene un radar cerca con el que comprobar la previsión "
                "al día siguiente. Úsese como indicación, no como dato cerrado.",
        "h_forecast": "Próximas noches",
        "sub_forecast": "Actualizado el {date}. {nights} noches, {cities} ciudades.",
        "relative": "<b>El nivel es relativo a cada ciudad</b>, no una cantidad absoluta de aves: «muy alto» "
                    "significa que esa noche entra en el 10 % más intenso del historial <i>de esa misma "
                    "ciudad</i>. Así el aviso quiere decir lo mismo en Sevilla y en Bilbao, aunque por "
                    "Sevilla pase mucha más ave.",
        "peak": "En pleno pico de la migración es normal que varias ciudades salgan altas a la vez: el "
                "percentil se mide contra las noches de esas mismas fechas en años anteriores.",
        "no_forecast": "Previsión no disponible todavía.",
        "h_switch_off": "Noches para apagar",
        "very_high_in": "<b>muy alto</b> en {cities}",
        "high_in_one": "alto en 1 ciudad más",
        "high_in_many": "alto en {n} ciudades más",
        "no_alert": "Ninguna ciudad supera su percentil 75 en este periodo: no hay motivo para un aviso.",
        "h_todo": "Qué hacer una noche de aviso",
        "sub_todo": "Lo que reduce las colisiones y la desorientación, por orden de eficacia y de facilidad.",
        "cards": [
            ("Apagar la iluminación ornamental",
             "Fachadas, monumentos, cañones de luz al cielo y rótulos no esenciales, de la puesta de sol al "
             "amanecer."),
            ("Apagar plantas y oficinas vacías",
             "Las plantas altas iluminadas de edificios acristalados son las que más atraen y las que más "
             "matan."),
            ("Bajar persianas y cortinas",
             "Si la luz interior tiene que quedarse encendida, que no salga por la ventana."),
            ("Apuntar la luz al suelo",
             "Luminarias con el flujo por debajo de la horizontal y temperatura de color cálida (≤ 2.700 K); "
             "el azul desorienta más."),
        ],
        "h_ranking": "Dónde coinciden más aves y más luz",
        "sub_ranking": "Ranking de exposición en {season}: el brillo artificial del cielo de cada ciudad "
                       "multiplicado por la densidad de aves prevista en sus diez noches más intensas, "
                       "normalizado a 100 en la ciudad más expuesta del conjunto. Sigue el método de Horton y "
                       "col. (2019).",
        "col_city": "ciudad",
        "col_sky": "cielo vs natural",
        "col_birds": "aves/km² en noches punta",
        "col_exposure": "exposición",
        "note_ranking": "La columna «cielo vs natural» dice cuántas veces más brillante es el cielo de esa "
                        "ciudad que uno sin luz artificial. Aviso: entre la ciudad más y la menos iluminada "
                        "hay un factor 3-4, mientras que en aves apenas hay un factor 2, así que el orden lo "
                        "marca sobre todo la luz.",
        "h_method": "Cómo se calcula",
        "sub_method": "De un eco de radar a un aviso de luces fuera, en nueve pasos y sin acrónimos.",
        "method": [
            ("Un radar meteorológico también ve aves",
             "<p>Un radar meteorológico es una antena que gira y lanza pulsos de microondas. Cuando un pulso "
             "choca con algo —gotas de lluvia, un ave, un insecto— una parte vuelve. El radar mide cuánta "
             "energía vuelve, que dice cuánto «material» hay, y cuánto ha tardado, que dice a qué distancia "
             "está. Para mirar a distintas alturas repite la vuelta con el haz cada vez más inclinado, de "
             "medio grado a más de diez. Cada 5-15 minutos tiene un volumen completo del aire que le rodea.</p>"
             "<p>Mide además el <b>efecto Doppler</b>: el pequeño cambio de frecuencia del eco cuando lo que "
             "refleja se acerca o se aleja, como la sirena de una ambulancia que cambia de tono al pasar. De "
             "ahí saldrá la velocidad de las aves.</p>"),
            ("El aire, cortado en rodajas de 200 metros",
             "<p>Un programa abierto, vol2bird (Dokter y col. 2011), toma cada volumen, se queda con el "
             "anillo entre 5 y 35 km del radar y lo corta en rodajas horizontales de 200 m de grosor. Para "
             "cada rodaja calcula:</p><ul>"
             "<li><b>Densidad</b>: el eco total dividido por el eco de un ave tipo, un pájaro pequeño de "
             "11 cm² de «superficie de radar». Sale en aves por kilómetro cúbico.</li>"
             "<li><b>Velocidad y dirección</b>: si las aves van hacia el nordeste, por ese lado del radar se "
             "alejan y por el lado contrario se acercan. Ajustando ese patrón en toda la vuelta sale hacia "
             "dónde y a qué velocidad se mueve el conjunto.</li>"
             "<li><b>Desorden</b>: cuánto se apartan las velocidades medidas de ese movimiento común. Lluvia "
             "e insectos van con el viento y dan un patrón limpio; las aves vuelan cada una con su rumbo y "
             "dan uno más revuelto. Una rodaja con menos de 2 m/s de desorden cuenta como cero aves.</li></ul>"),
            ("De AEMET a esta página",
             "<p>Los radares españoles son de AEMET; los portugueses, del IPMA; los franceses, de "
             "Météo-France. Cada servicio envía sus volúmenes a <b>OPERA</b>, la red que reúne los radares "
             "meteorológicos de casi toda Europa. <b>Aloft</b>, un archivo científico europeo, pasa vol2bird "
             "sobre esos volúmenes y publica los perfiles en abierto (CC0), con uno o dos días de retraso y "
             "sin control de calidad. Sub Nocte los descarga de ahí: un fichero por radar y día, con una fila "
             "por rodaja y por perfil.</p>"),
            ("Una noche, una cifra",
             "<p>Se suman las rodajas entre 200 y 3.000 m, cada una con su densidad por 0,2 km de grosor. "
             "El resultado es cuántas aves hay en la columna de aire sobre un kilómetro cuadrado de suelo. "
             "Después se promedian todos los perfiles de la noche, desde que el sol baja de 6° bajo el "
             "horizonte hasta que vuelve a subir de ahí. Esa es la cifra central de la página: el <b>VID "
             "nocturno</b>, en aves/km².</p>"
             "<p class='formula'>VID = Σ densidad × 0,2 km &nbsp;→&nbsp; media de la noche</p>"
             "<p>BirdCast usa otra unidad: cuántas aves cruzan una línea imaginaria de 1 km a lo largo de "
             "la noche (MTR). Es la densidad multiplicada por la velocidad, así que necesita la velocidad. "
             "Aquí se calcula solo cuando al menos la mitad de la densidad de la noche la tiene medida; si "
             "no, queda vacía, nunca a cero.</p>"),
            ("Qué es una noche fuerte, en cada sitio",
             "<p>Con el histórico de cada radar desde 2016 se calcula, para cada día del año, cómo es una "
             "noche normal y dónde caen los percentiles 70 y 90. Comprobación de coherencia: el 10 % de "
             "noches más intensas concentra el 50-55 % del paso de la temporada en España, Portugal y "
             "Francia, el mismo valor que se midió en Estados Unidos (54 %).</p>"),
            ("La meteorología explica buena parte de esa cifra",
             "<p>Con once años de noches de 55 radares de España, Portugal y Francia se entrenan dos "
             "modelos: uno estima cuánta ave habrá y otro decide si la noche va a ser de paso fuerte. Las "
             "variables son el viento a la altura a la que vuelan (750, 1.500 y 3.000 metros), descompuesto "
             "en lo que empuja hacia el rumbo migratorio y lo que desvía; la temperatura y su cambio en 24 "
             "horas; la humedad, la nubosidad, la lluvia y la presión; y el día del año.</p>"),
            ("La validación quita radares enteros",
             "<p>No se quitan noches al azar. Es la única prueba honesta para una ciudad sin radar: se "
             "entrena sin ese radar y se le pide predecirlo a ciegas. Así el modelo captura un <b>34 % de "
             "las noches de paso fuerte</b> frente al 10 % que daría el azar, con un 66 % de falsas alarmas. "
             "Acierta tres veces más que tirar una moneda, y se equivoca a menudo.</p>"),
            ("El aviso se calibra ciudad a ciudad y fecha a fecha",
             "<p>Se corre el modelo sobre la meteorología de 2021 a hoy en el punto exacto de la ciudad, y "
             "los niveles se cortan por los percentiles de las noches de esas mismas fechas, con una ventana "
             "de tres semanas a cada lado: moderado por encima de la mediana, alto por encima del percentil "
             "75, muy alto por encima del 90. Así el aviso no necesita radar en la ciudad, significa lo "
             "mismo en todas y sigue significando algo en pleno pico de paso.</p>"),
            ("Cada previsión se comprueba después",
             "<p>La previsión de cada día queda guardada en el historial del repositorio con su fecha. Cada "
             "lunes se recuperan las ya pasadas, se descarga lo que midieron después los radares y se "
             "publica el resultado en el informe de verificación.</p>"),
        ],
        "h_gaps": "Dos huecos en los datos",
        "sub_gaps": "Revisando los ficheros rodaja a rodaja aparecen dos carencias que no figuran en la "
                    "documentación del archivo. Están medidas, no supuestas, y explican buena parte de por "
                    "qué las ciudades españolas son el caso difícil.",
        "gap_height_h": "En España el radar solo mira el primer kilómetro",
        "gap_height": "<p>En los radares renovados de AEMET solo hay eco hasta unos 900-1.000 m por encima "
                      "de la antena: cinco o seis rodajas. Por encima, el fichero no trae ni un punto de "
                      "medida, ni de aves ni de nada. Con el mismo programa, Oporto llega a 3,7 km sobre la "
                      "antena y Nantes a 4,7 km.</p>",
        "gap_height_why": "<p>La explicación más probable es geométrica. A 35 km del radar, un haz inclinado "
                          "1,5° pasa a algo más de 900 m sobre la antena, y unos 100 m más por la curvatura "
                          "de la Tierra. Las capas altas solo las ven los haces más inclinados. Si a la red "
                          "europea llegan solo las vueltas más bajas, el techo sale justo ahí. Es una "
                          "hipótesis pendiente de confirmar con AEMET.</p>"
                          "<p><b>Consecuencia:</b> las aves que vuelan por encima no se cuentan. Por eso aquí "
                          "nunca se compara la cifra de un radar español con la de otro país: los niveles "
                          "son percentiles de cada radar.</p>",
        "beam_caption": "Lo que ve el radar, con la altura exagerada. Las líneas son haces a distintas "
                        "inclinaciones; la banda clara, el anillo de 5 a 35 km que usa vol2bird.",
        "beam_labels": ("lo que llega de España", "lo que llega de Oporto o Nantes", "distancia al radar"),
        "gap_speed_h": "La velocidad falta a menudo, y en Francia casi siempre",
        "gap_speed": "<p>La velocidad sale del Doppler. Esta es la parte de las rodajas con aves que la "
                     "trae:</p>",
        "gap_speed_why": "<p>En Francia el archivo la tenía completa en 2019 y la pierde a partir de 2021. "
                         "El programa que la calcula es el mismo, así que lo más probable es que cambiara "
                         "la forma en que el dato Doppler llega a la red europea. En los radares españoles "
                         "renovados está en algo menos de la mitad de las rodajas con aves en primavera, y "
                         "casi nunca en invierno, cuando apenas hay aves. Los radares antiguos de AEMET la "
                         "daban siempre.</p>"
                         "<p><b>Consecuencia:</b> sin velocidad no hay tasa de paso (MTR) ni filtro de "
                         "desorden para separar insectos. Por eso la cifra central es el VID, que solo "
                         "necesita la densidad. Pendiente de consultar con Aloft si el dato Doppler está en "
                         "los ficheros de origen y si se puede reprocesar 2021-2026.</p>",
        "col_radar": "radar",
        "col_layers": "capas con eco (sobre el mar)",
        "col_antenna": "antena",
        "col_reach": "alcance sobre la antena",
        "col_period": "periodo",
        "col_with_speed": "capas con aves que traen velocidad",
        "evidence_note": "Medido sobre los perfiles de Aloft en octubre de 2026.",
        "fig_cities": "ciudades",
        "fig_nights": "noches previstas",
        "fig_radars": "radares en el histórico",
        "fig_hit": "noches fuertes captadas",
        "h_reports": "Informes técnicos",
        "sub_reports": "Cada fase con sus figuras, sus tablas y sus limitaciones.",
        "reports": {
            "phase0.html": "Fase 0 — ¿ven aves los radares españoles renovados?",
            "phase1.html": "Fase 1 — histórico 2016-2026 y climatologías por radar",
            "phase2.html": "Fase 2 — el modelo meteorológico y su validación",
            "phase3.html": "Fase 3 — previsión por ciudad",
            "ranking.html": "Ranking de exposición a la luz artificial",
            "scorecard.html": "Verificación — ¿acertaron las previsiones ya publicadas?",
            "design.html": "Documento de diseño del proyecto",
        },
        "note_reports": "Los informes técnicos están en inglés.",
        "h_not": "Lo que esto no es",
        "not_this": [
            "No es un recuento de aves sobre tu tejado: es la densidad media en toda la columna de aire, la "
            "mayor parte de ella entre 200 y 3.000 metros de altura.",
            "No distingue especies. Un radar meteorológico no sabe si el eco es un zorzal o un mosquitero.",
            "En otoño y en el sur, parte de la señal puede ser insecto. Hace falta la velocidad de vuelo para "
            "separarlos, y el archivo europeo no la trae en Francia desde 2021 ni en cerca de la mitad de "
            "las capas con aves de los radares españoles renovados (ver «Dos huecos en los datos»).",
            "El pronóstico se degrada con los días: la primera noche es fiable, la séptima mucho menos.",
            "Las cuatro ciudades españolas con radar nuevo son el caso difícil del modelo (mide bien el orden "
            "de las noches, pero el perfil llega truncado a seis capas). No conviene tomar decisiones firmes "
            "ahí hasta la temporada de 2027.",
        ],
        "h_data": "Datos, método y crédito",
        "data": "Perfiles verticales de aves: <a href='https://aloftdata.eu'>Aloft</a> (Desmet y col. 2025), "
                 "red europea de radares meteorológicos, licencia CC0. Meteorología: "
                 "<a href='https://open-meteo.com'>Open-Meteo</a> (CC BY 4.0). Luz artificial: Falchi y col. "
                 "(2016), <i>The new world atlas of artificial night sky brightness</i>, Science Advances "
                 "2(6):e1600377, y GFZ Data Services doi:10.5880/GFZ.1.4.2016.001 — los ficheros originales "
                 "no se redistribuyen aquí, solo resultados derivados. Método: Van Doren y Horton (2018) para "
                 "el modelo, Horton y col. (2019) para la exposición a la luz, Horton y col. (2021) para la "
                 "concentración del paso en pocas noches.",
        "cornell": "Sub Nocte sigue el planteamiento de <a href='https://birdcast.org'>BirdCast</a>, el "
                   "servicio de la Universidad de Cornell para Estados Unidos, y no tiene ninguna relación "
                   "con él.",
        "footer": "Proyecto abierto y sin ánimo de lucro. Todo el código y los datos derivados están en "
               f"<a href='{REPO}'>github.com/Asensio94/sub-nocte</a> (licencia MIT); la página se regenera "
               "desde esos mismos ficheros, así que cualquiera puede reproducir lo que dice.",
        "generated": "Generado el {date}.",
    },
    "en": {
        "title": "Sub Nocte · nocturnal bird migration in Europe",
        "description": "City-level forecast of nocturnal bird migration intensity in Europe, with lights-out "
                       "alerts, built on the open radar profiles published by Aloft.",
        "other_lang": "Español",
        "claim": "Every spring and autumn night, millions of birds cross Europe in the dark. A handful of "
                 "nights carry half of the passage. This page tries to say <b>which ones</b>, city by city, "
                 "so that the lights can go out on exactly those nights.",
        "beta": "<b>Technical preview, not a production service.</b> The model is validated (see below), but "
                "none of these cities has a radar close enough to check the forecast the next morning. Treat "
                "it as an indication, not a settled figure.",
        "h_forecast": "The nights ahead",
        "sub_forecast": "Updated on {date}. {nights} nights, {cities} cities.",
        "relative": "<b>The level is relative to each city</b>, not an absolute number of birds: “very high” "
                    "means the night falls in the most intense 10 % of the record <i>for that same city</i>. "
                    "That way the alert means the same thing in Seville and in Bilbao, even though far more "
                    "birds pass over Seville.",
        "peak": "At the peak of the passage it is normal for several cities to come out high at once: the "
                "percentile is measured against the nights of those same dates in earlier years.",
        "no_forecast": "Forecast not available yet.",
        "h_switch_off": "Nights to switch off",
        "very_high_in": "<b>very high</b> in {cities}",
        "high_in_one": "high in 1 more city",
        "high_in_many": "high in {n} more cities",
        "no_alert": "No city exceeds its 75th percentile in this period: there is no reason for an alert.",
        "h_todo": "What to do on an alert night",
        "sub_todo": "What actually reduces collisions and disorientation, ordered by effect and by ease.",
        "cards": [
            ("Switch off decorative lighting",
             "Façades, monuments, skybeams and non-essential signs, from sunset to dawn."),
            ("Switch off empty floors and offices",
             "Lit upper floors of glass buildings are the ones that attract most birds and kill most of "
             "them."),
            ("Draw blinds and curtains",
             "If the indoor lights have to stay on, keep the light from spilling out of the window."),
            ("Aim the light at the ground",
             "Luminaires with all their output below the horizontal and a warm colour temperature "
             "(≤ 2,700 K); blue light is more disorienting."),
        ],
        "h_ranking": "Where birds and light overlap most",
        "sub_ranking": "Exposure ranking for {season}: the artificial brightness of each city's sky "
                       "multiplied by the bird density forecast on its ten most intense nights, normalised "
                       "to 100 at the most exposed city in the set. It follows the method of Horton et al. "
                       "(2019).",
        "col_city": "city",
        "col_sky": "sky vs natural",
        "col_birds": "birds/km² on peak nights",
        "col_exposure": "exposure",
        "note_ranking": "The “sky vs natural” column says how many times brighter that city's sky is than a "
                        "sky with no artificial light. A caveat: between the most and the least lit city "
                        "there is a factor of 3-4, while in birds there is barely a factor of 2, so the "
                        "ordering is driven mostly by light.",
        "h_method": "How it is computed",
        "sub_method": "From a radar echo to a lights-out alert, in nine steps and without acronyms.",
        "method": [
            ("A weather radar sees birds too",
             "<p>A weather radar is an antenna that turns and sends out microwave pulses. When a pulse hits "
             "something — raindrops, a bird, an insect — part of it comes back. The radar measures how much "
             "energy returns, which says how much “material” there is, and how long it took, which says how "
             "far away it is. To look at different heights it repeats the turn with the beam tilted more "
             "and more, from half a degree to over ten. Every 5-15 minutes it has a full volume of the air "
             "around it.</p>"
             "<p>It also measures the <b>Doppler effect</b>: the small change in frequency of the echo when "
             "what reflects it moves towards or away from the antenna, like an ambulance siren changing "
             "pitch as it passes. That is where the birds' speed will come from.</p>"),
            ("The air, cut into 200-metre slices",
             "<p>An open program, vol2bird (Dokter et al. 2011), takes each volume, keeps the ring between 5 "
             "and 35 km from the radar and cuts it into horizontal slices 200 m thick. For each slice it "
             "computes:</p><ul>"
             "<li><b>Density</b>: the total echo divided by the echo of a typical bird, a small songbird "
             "with 11 cm² of “radar surface”. It comes out in birds per cubic kilometre.</li>"
             "<li><b>Speed and direction</b>: if the birds head north-east, on that side of the radar they "
             "move away and on the opposite side they come closer. Fitting that pattern all the way round "
             "gives where the whole lot is going and how fast.</li>"
             "<li><b>Disorder</b>: how far the measured speeds stray from that common movement. Rain and "
             "insects drift with the wind and give a clean pattern; birds each fly their own heading and "
             "give a messier one. A slice with less than 2 m/s of disorder counts as zero birds.</li></ul>"),
            ("From the weather service to this page",
             "<p>The Spanish radars belong to AEMET, the Portuguese ones to IPMA and the French ones to "
             "Météo-France. Each service sends its volumes to <b>OPERA</b>, the network that pools the "
             "weather radars of almost all of Europe. <b>Aloft</b>, a European scientific archive, runs "
             "vol2bird on those volumes and publishes the profiles openly (CC0), one or two days late and "
             "without quality control. Sub Nocte downloads them from there: one file per radar and day, "
             "with one row per slice and per profile.</p>"),
            ("One night, one figure",
             "<p>The slices between 200 and 3,000 m are added up, each one as its density times 0.2 km of "
             "thickness. The result is how many birds there are in the air column over one square "
             "kilometre of ground. Then all the profiles of the night are averaged, from when the sun "
             "drops 6° below the horizon until it climbs back past it. That is the page's central figure: "
             "the <b>nightly VID</b>, in birds/km².</p>"
             "<p class='formula'>VID = Σ density × 0.2 km &nbsp;→&nbsp; mean over the night</p>"
             "<p>BirdCast uses another unit: how many birds cross an imaginary 1 km line during the night "
             "(MTR). It is density times speed, so it needs the speed. Here it is computed only when at "
             "least half of the night's density has a measured speed; otherwise it is left empty, never "
             "set to zero.</p>"),
            ("What a heavy night is, place by place",
             "<p>From each radar's record since 2016 we work out, for every day of the year, what a normal "
             "night looks like and where the 70th and 90th percentiles fall. Sanity check: the most "
             "intense 10 % of nights carry 50-55 % of the season's passage in Spain, Portugal and France, "
             "the same share measured in the United States (54 %).</p>"),
            ("Weather explains a good part of that figure",
             "<p>Using eleven years of nights from 55 radars in Spain, Portugal and France we train two "
             "models: one estimates how many birds there will be and the other decides whether the night "
             "will carry heavy passage. The variables are the wind at the heights where they fly (750, "
             "1,500 and 3,000 metres), split into the part pushing along the migratory heading and the "
             "part pushing sideways; temperature and its 24-hour change; humidity, cloud cover, rain and "
             "pressure; and the day of the year.</p>"),
            ("Validation leaves whole radars out",
             "<p>Not random nights. It is the only honest test for a city without a radar: the model is "
             "trained without that radar and then asked to predict it blind. Done that way it captures "
             "<b>34 % of the heavy-passage nights</b> against the 10 % that chance would give, with 66 % "
             "false alarms. Three times better than a coin flip, and wrong fairly often.</p>"),
            ("The alert is calibrated city by city and date by date",
             "<p>The model is run over the weather from 2021 to today at the city's exact location, and the "
             "levels are cut at the percentiles of the nights around the same date, in a window of three "
             "weeks either side: moderate above the median, high above the 75th percentile, very high above "
             "the 90th. That is why the alert needs no radar in the city, means the same thing everywhere "
             "and still means something at the peak of the passage.</p>"),
            ("Every forecast is checked afterwards",
             "<p>Each day's forecast stays in the repository history with its date. Every Monday the past "
             "ones are retrieved, what the radars measured afterwards is downloaded, and the result is "
             "published in the verification report.</p>"),
        ],
        "h_gaps": "Two gaps in the data",
        "sub_gaps": "Going through the files slice by slice turns up two shortcomings that are not in the "
                    "archive's documentation. They are measured, not assumed, and they explain a good part "
                    "of why the Spanish cities are the hard case.",
        "gap_height_h": "In Spain the radar only looks at the first kilometre",
        "gap_height": "<p>On AEMET's renewed radars there is echo only up to about 900-1,000 m above the "
                      "antenna: five or six slices. Above that the file carries not a single measurement, "
                      "of birds or of anything else. With the same program, Porto reaches 3.7 km above the "
                      "antenna and Nantes 4.7 km.</p>",
        "gap_height_why": "<p>The most likely explanation is geometric. At 35 km from the radar, a beam "
                          "tilted 1.5° passes a little over 900 m above the antenna, plus about 100 m more "
                          "because of the Earth's curvature. Only the steeper beams see the higher layers. "
                          "If only the lowest turns reach the European network, the ceiling lands right "
                          "there. It is a hypothesis still to be confirmed with AEMET.</p>"
                          "<p><b>Consequence:</b> birds flying higher are not counted. That is why a Spanish "
                          "radar's figure is never compared with another country's here: the levels are "
                          "each radar's own percentiles.</p>",
        "beam_caption": "What the radar sees, with height exaggerated. The lines are beams at different "
                        "tilts; the light band is the 5-35 km ring vol2bird uses.",
        "beam_labels": ("what arrives from Spain", "what arrives from Porto or Nantes", "distance from the radar"),
        "gap_speed_h": "Speed is often missing, and in France almost always",
        "gap_speed": "<p>Speed comes from the Doppler. This is the share of slices with birds that carry "
                     "it:</p>",
        "gap_speed_why": "<p>In France the archive had it complete in 2019 and loses it from 2021 on. The "
                         "program that computes it is the same, so the most likely cause is a change in "
                         "how the Doppler data reaches the European network. On the renewed Spanish radars "
                         "it is there in a bit under half of the slices with birds in spring, and almost "
                         "never in winter, when there are hardly any birds. AEMET's old radars always gave "
                         "it.</p>"
                         "<p><b>Consequence:</b> without speed there is no traffic rate (MTR) and no "
                         "disorder filter to set insects apart. That is why the central figure is the VID, "
                         "which needs only density. Still to ask Aloft whether the Doppler data is in the "
                         "source files and whether 2021-2026 can be reprocessed.</p>",
        "col_radar": "radar",
        "col_layers": "layers with echo (above sea level)",
        "col_antenna": "antenna",
        "col_reach": "reach above the antenna",
        "col_period": "period",
        "col_with_speed": "bird layers carrying speed",
        "evidence_note": "Measured on the Aloft profiles in October 2026.",
        "fig_cities": "cities",
        "fig_nights": "nights ahead",
        "fig_radars": "radars in the record",
        "fig_hit": "heavy nights caught",
        "h_reports": "Technical reports",
        "sub_reports": "Each phase with its figures, its tables and its limitations.",
        "reports": {
            "phase0.html": "Phase 0 — do the renewed Spanish radars see birds?",
            "phase1.html": "Phase 1 — 2016-2026 archive and per-radar climatologies",
            "phase2.html": "Phase 2 — the weather model and its validation",
            "phase3.html": "Phase 3 — city-level forecast",
            "ranking.html": "Artificial light exposure ranking",
            "scorecard.html": "Verification — did the published forecasts hold up?",
            "design.html": "Project design document",
        },
        "note_reports": "The technical reports are in English.",
        "h_not": "What this is not",
        "not_this": [
            "It is not a count of the birds over your roof: it is the mean density across the whole air "
            "column, most of it between 200 and 3,000 metres up.",
            "It does not tell species apart. A weather radar cannot know whether the echo is a thrush or a "
            "warbler.",
            "In autumn and in the south, part of the signal may be insects. Separating them needs flight "
            "speed, and the European archive lacks it in France since 2021 and in about half of the bird "
            "layers of the renewed Spanish radars (see “Two gaps in the data”).",
            "The forecast decays with lead time: the first night is reliable, the seventh much less so.",
            "The four Spanish cities with a renewed radar are the model's hard case (it ranks their nights "
            "reasonably well, but the profile arrives truncated to six layers). Firm decisions there are "
            "better left until the 2027 season.",
        ],
        "h_data": "Data, method and credit",
        "data": "Bird vertical profiles: <a href='https://aloftdata.eu'>Aloft</a> (Desmet et al. 2025), "
                 "European weather radar network, CC0. Weather: <a href='https://open-meteo.com'>Open-Meteo"
                 "</a> (CC BY 4.0). Artificial light: Falchi et al. (2016), <i>The new world atlas of "
                 "artificial night sky brightness</i>, Science Advances 2(6):e1600377, and GFZ Data Services "
                 "doi:10.5880/GFZ.1.4.2016.001 — the original files are not redistributed here, only derived "
                 "results. Method: Van Doren & Horton (2018) for the model, Horton et al. (2019) for light "
                 "exposure, Horton et al. (2021) for the concentration of passage into few nights.",
        "cornell": "Sub Nocte follows the approach of <a href='https://birdcast.org'>BirdCast</a>, Cornell "
                   "University's service for the United States, and has no affiliation with it.",
        "footer": "Open, non-profit project. All the code and derived data live at "
               f"<a href='{REPO}'>github.com/Asensio94/sub-nocte</a> (MIT licence); the page is regenerated "
               "from those same files, so anyone can reproduce what it says.",
        "generated": "Generated on {date}.",
    },
}


# Evidence behind «two gaps in the data», measured on the raw Aloft VPTS files in October 2026
# (n_dbz_all = 0 above the top layer; share of layers with dens > 0 that carry ff). Kept literal per language
# because the number formats differ.
HEIGHT_EVIDENCE = {
    "es": [("Renovados de AEMET (estjv, esgld, essft)", "600-1.600 m", "≈ 660-717 m", "≈ 0,9-1 km"),
           ("Renovado de AEMET (esahr)", "1.200-2.000 m", "1.159 m", "≈ 0,9-1 km"),
           ("Antiguos de AEMET, 2019 (esmad, esbar)", "600-1.200 m", "≈ 660-717 m", "≈ 0,5 km"),
           ("Oporto (ptprt)", "1.000-4.800 m", "1.097 m", "≈ 3,7 km"),
           ("Nantes (frtre)", "0-4.800 m", "81 m", "≈ 4,7 km")],
    "en": [("AEMET renewed (estjv, esgld, essft)", "600-1,600 m", "≈ 660-717 m", "≈ 0.9-1 km"),
           ("AEMET renewed (esahr)", "1,200-2,000 m", "1,159 m", "≈ 0.9-1 km"),
           ("AEMET old network, 2019 (esmad, esbar)", "600-1,200 m", "≈ 660-717 m", "≈ 0.5 km"),
           ("Porto (ptprt)", "1,000-4,800 m", "1,097 m", "≈ 3.7 km"),
           ("Nantes (frtre)", "0-4,800 m", "81 m", "≈ 4.7 km")],
}
SPEED_EVIDENCE = {
    "es": [("estjv (renovado)", "noviembre 2025", 28), ("estjv (renovado)", "enero 2026, invierno", 3),
           ("estjv (renovado)", "abril 2026", 54), ("estjv (renovado)", "agosto 2026", 49),
           ("esgld (renovado)", "abril 2026", 52), ("essft (renovado)", "abril 2026", 40),
           ("esahr (renovado)", "abril 2026", 42), ("esmad, esbar (antiguos)", "2019", 100),
           ("Oporto (ptprt)", "abril 2026", 33), ("Nantes (frtre)", "2019", 100),
           ("Nantes (frtre)", "2021", 14), ("Nantes (frtre)", "2024", 0), ("Dijon (frbla)", "2024", 0)],
    "en": [("estjv (renewed)", "November 2025", 28), ("estjv (renewed)", "January 2026, winter", 3),
           ("estjv (renewed)", "April 2026", 54), ("estjv (renewed)", "August 2026", 49),
           ("esgld (renewed)", "April 2026", 52), ("essft (renewed)", "April 2026", 40),
           ("esahr (renewed)", "April 2026", 42), ("esmad, esbar (old network)", "2019", 100),
           ("Porto (ptprt)", "April 2026", 33), ("Nantes (frtre)", "2019", 100),
           ("Nantes (frtre)", "2021", 14), ("Nantes (frtre)", "2024", 0), ("Dijon (frbla)", "2024", 0)],
}

PRINCIPLE = {"es": "Datos públicos, reglas a la vista y cada cifra enlazada a su fuente. Indicios, no veredictos.",
             "en": "Public data, rules in plain sight and every figure linked to its source. Leads, not verdicts."}
SIBLINGS = [("observatorio-alegaciones", "Observatorio de alegaciones"), ("vigia-incendios", "Vigía de incendios"),
            ("centinela-natura", "Centinela Natura"), ("vigilancia-humedales", "Vigilancia de humedales"),
            ("sub-nocte", "Sub Nocte"), ("riesgo-tendidos-aves", "Riesgo de tendidos para aves"),
            ("grafo-promotores", "Grafo de promotores"), ("cartera-cotizadas", "Cartera de las cotizadas"),
            ("cuaderno-campo", "Cuaderno de campo")]
NIGHTLY_DIR = Path(__file__).resolve().parents[1] / "data" / "nightly"


def _num(x: float, lang: str, nd: int = 0) -> str:
    s = f"{x:,.{nd}f}"
    return s.replace(",", "·").replace(".", ",").replace("·", ".") if lang == "es" else s


def figures(fc: pd.DataFrame | None, lang: str) -> str:
    """Key figures under the title: what the page covers right now."""
    c = COPY[lang]
    items = []
    if fc is not None and not fc.empty:
        items += [(fc["city"].nunique(), c["fig_cities"]), (fc["night"].nunique(), c["fig_nights"])]
    n_radars = len(list(NIGHTLY_DIR.glob("*.parquet"))) if NIGHTLY_DIR.exists() else 0
    if n_radars:
        items.append((n_radars, c["fig_radars"]))
    cells = [f"<div><b>{_num(v, lang)}</b><span>{label}</span></div>" for v, label in items]
    cells.append(f"<div><b>34 %</b><span>{c['fig_hit']}</span></div>")
    return f"<div class='figures'>{''.join(cells)}</div>"


def beam_svg(lang: str) -> str:
    """Side view of a radar: beam heights over distance (4/3 Earth radius) and the vol2bird ring.

    Heights are drawn 12 times taller than distances so the first kilometre can be seen at all.
    """
    import math
    c = COPY[lang]
    x0, ground, kx, ky = 64, 222, 11.5, 46          # px per km horizontally and vertically
    x = lambda d: x0 + d * kx
    y = lambda h: ground - h * ky
    h = lambda d, e: d * math.tan(math.radians(e)) + d * d / (2 * 8500)
    out = [f"<svg class='beam' viewBox='0 0 640 262' role='img' aria-label='{c['beam_caption']}'>",
           f"<rect x='{x(5)}' y='{y(4.2)}' width='{30 * kx}' height='{4.2 * ky}' fill='var(--accent)' opacity='.06'/>",
           f"<rect x='{x(5)}' y='{y(1.0)}' width='{30 * kx}' height='{1.0 * ky}' fill='var(--accent)' opacity='.22'/>"]
    out += [f"<line x1='{x(5)}' x2='{x(35)}' y1='{y(k * .2):.1f}' y2='{y(k * .2):.1f}' stroke='var(--line)'/>"
            for k in range(1, 21)]
    for e, sent in ((0.5, True), (1.5, True), (3.0, False), (5.0, False), (7.0, False)):
        d_end = 46
        while h(d_end, e) > 4.3:
            d_end -= 0.5
        pts = " ".join(f"{x(d):.1f},{y(h(d, e)):.1f}" for d in [i * 0.5 for i in range(int(d_end * 2) + 1)])
        style = "stroke='var(--accent)' stroke-width='2'" if sent else "stroke='var(--muted)' stroke-dasharray='4 3'"
        out.append(f"<polyline points='{pts}' fill='none' {style}/>")
        out.append(f"<text x='{x(d_end) + 4:.1f}' y='{y(h(d_end, e)) + 4:.1f}'>{_num(e, lang, 0 if e == int(e) else 1)}°</text>")
    out += [f"<line x1='{x0 - 20}' x2='{x(46)}' y1='{ground}' y2='{ground}' stroke='var(--ink)'/>",
            f"<path d='M{x0 - 8},{ground} L{x0},{ground - 14} L{x0 + 8},{ground} Z' fill='var(--ink)'/>"]
    for d in (0, 5, 15, 25, 35, 45):
        out.append(f"<text x='{x(d)}' y='{ground + 16}' text-anchor='middle'>{d}</text>")
    for hk in (1, 2, 3, 4):
        out.append(f"<text x='{x0 - 26}' y='{y(hk) + 4}' text-anchor='end'>{hk} km</text>"
                   f"<line x1='{x0 - 22}' x2='{x0 - 18}' y1='{y(hk)}' y2='{y(hk)}' stroke='var(--muted)'/>")
    spain, others, dist = c["beam_labels"]
    out += [f"<text class='lbl' x='{x(20)}' y='{y(0.5) + 4}' text-anchor='middle'>{spain}</text>",
            f"<text class='lbl' x='{x(20)}' y='{y(3.3)}' text-anchor='middle'>{others}</text>",
            f"<text x='{x(25)}' y='{ground + 34}' text-anchor='middle'>{dist} (km)</text>", "</svg>"]
    return "".join(out)


def method_section(lang: str) -> str:
    """«How it is computed»: numbered steps from the radar echo to the alert, then the two data gaps."""
    c = COPY[lang]
    p = [f"<section class='method' id='metodo'><h2>{c['h_method']}</h2><p class='sub'>{c['sub_method']}</p>",
         "<ol class='steps'>"]
    p += [f"<li><h3>{title}</h3>{body}</li>" for title, body in c["method"]]
    p += ["</ol>", f"<h2>{c['h_gaps']}</h2><p class='sub'>{c['sub_gaps']}</p>",
          f"<div class='gap'><h3>{c['gap_height_h']}</h3>{c['gap_height']}",
          f"<figure>{beam_svg(lang)}<figcaption>{c['beam_caption']}</figcaption></figure>",
          f"<div class='scroll'><table class='params'><tr><th>{c['col_radar']}</th><th>{c['col_layers']}</th>"
          f"<th>{c['col_antenna']}</th><th>{c['col_reach']}</th></tr>"]
    p += [f"<tr><td>{r}</td><td>{a}</td><td>{b}</td><td><b>{d}</b></td></tr>"
          for r, a, b, d in HEIGHT_EVIDENCE[lang]]
    p += ["</table></div>", c["gap_height_why"], "</div>",
          f"<div class='gap'><h3>{c['gap_speed_h']}</h3>{c['gap_speed']}",
          f"<div class='scroll'><table class='params'><tr><th>{c['col_radar']}</th><th>{c['col_period']}</th>"
          f"<th class='num'>{c['col_with_speed']}</th></tr>"]
    p += [f"<tr><td>{r}</td><td>{per}</td><td class='num'>{v} %</td></tr>" for r, per, v in SPEED_EVIDENCE[lang]]
    p += ["</table></div>", c["gap_speed_why"], f"<p class='note'>{c['evidence_note']}</p></div>", "</section>"]
    return "\n".join(p)


def site_footer(lang: str, today: dt.date) -> str:
    c = COPY[lang]
    nav = "Proyectos hermanos" if lang == "es" else "Sibling projects"
    current = " aria-current='page'"
    items = "".join(f"<li{current if slug == 'sub-nocte' else ''}>"
                    f"<a href='https://asensio94.github.io/{slug}/'>{name}</a></li>" for slug, name in SIBLINGS)
    return (f"<footer class='site-footer'><p class='principle'>{PRINCIPLE[lang]}</p>"
            f"<p>{c['footer']}</p><p>{c['generated'].format(date=_date(today, lang))}</p>"
            f"<nav aria-label='{nav}'><ul class='siblings'>{items}</ul></nav></footer>")


def _date(d: dt.date, lang: str) -> str:
    month = MONTHS_LONG[lang][d.month - 1]
    return f"{d.day} de {month} de {d.year}" if lang == "es" else f"{d.day} {month} {d.year}"


def _night(d: pd.Timestamp, lang: str) -> str:
    return f"{DAYS[lang][d.weekday()]} {d.day} {MONTHS[lang][d.month - 1]}"


def _cell(level: str, lang: str) -> str:
    return (f"<td class='n' style='background:{COLOR.get(level, '#f6f6f6')};"
            f"color:{TEXT.get(level, '#3a3f45')}'>{LEVEL_NAME[lang].get(level, level)}</td>")


def calendar(fc: pd.DataFrame, lang: str) -> str:
    """City × night table with the alert level, cities with the strongest alerts on top."""
    c = COPY[lang]
    fc = fc.assign(w=fc["level"].map(WEIGHT).fillna(0))
    order = fc.groupby("city")["w"].max().sort_values(ascending=False).index
    nights = sorted(fc["night"].unique())
    head = "".join(f"<th>{DAYS[lang][pd.Timestamp(n).weekday()]}<br>{pd.Timestamp(n).day} "
                   f"{MONTHS[lang][pd.Timestamp(n).month - 1]}</th>" for n in nights)
    rows = []
    for city in order:
        g = fc[fc["city"] == city].set_index("night")
        country = COUNTRY[lang].get(g["country"].iat[0], g["country"].iat[0])
        cells = "".join(_cell(g.loc[n, "level"], lang) if n in g.index else "<td class='n'></td>"
                        for n in nights)
        rows.append(f"<tr><td><b>{city}</b> <span class='pill'>{country}</span></td>{cells}</tr>")
    legend = "".join(f"<span><i style='background:{COLOR[n]}'></i>{LEVEL_NAME[lang][n]}</span>"
                     for n in ("low", "moderate", "high", "very high"))
    return (f"<div class='cal'><table><tr><th>{c['col_city']}</th>{head}</tr>{''.join(rows)}</table></div>"
            f"<div class='legend'>{legend}</div>")


def nights_to_switch_off(alerts: pd.DataFrame, lang: str) -> list[str]:
    """One line per night: which cities are at "very high" and how many more at "high"."""
    c = COPY[lang]
    p = [f"<h3>{c['h_switch_off']}</h3><ul>"]
    for night, g in alerts.groupby("night"):
        very = sorted(g[g["level"] == "very high"]["city"])
        others = len(g) - len(very)
        parts = []
        if very:
            parts.append(c["very_high_in"].format(cities=", ".join(very)))
        if others:
            parts.append(c["high_in_one"] if others == 1 else c["high_in_many"].format(n=others))
        p.append(f"<li><b>{_night(pd.Timestamp(night), lang)}</b>: " + "; ".join(parts) + ".</li>")
    p.append("</ul>")
    return p


def ranking_table(rk: pd.DataFrame, season: str, lang: str, n: int = 12) -> str:
    c = COPY[lang]
    g = rk[rk["season"] == season].nlargest(n, "exposure_peaks")
    rows = "".join(
        f"<tr><td>{i}. <b>{r.city}</b> <span class='pill'>{COUNTRY[lang].get(r.country, r.country)}</span></td>"
        f"<td>{r.times_natural:.0f}×</td><td>{r.vid_peaks:.0f}</td><td>{r.exposure_peaks:.0f}</td></tr>"
        for i, r in enumerate(g.itertuples(index=False), 1))
    return (f"<table><tr><th>{c['col_city']}</th><th>{c['col_sky']}</th><th>{c['col_birds']}</th>"
            f"<th>{c['col_exposure']}</th></tr>{rows}</table>")


def _page(fc: pd.DataFrame | None, rk: pd.DataFrame | None, links: list[str], lang: str,
          prefix: str, today: dt.date) -> str:
    """Assemble the complete HTML of one of the two pages. `prefix` fixes the relative paths."""
    c = COPY[lang]
    other = "en" if lang == "es" else "es"
    other_path = f"{prefix}en/" if lang == "es" else prefix
    p = [f"<!doctype html><html lang='{lang}'><meta charset='utf-8'>",
         "<meta name='viewport' content='width=device-width,initial-scale=1'>",
         f"<title>{c['title']}</title>",
         FAVICON,
         f"<meta name='description' content='{c['description']}'>",
         f"<link rel='alternate' hreflang='es' href='{BASE}'>",
         f"<link rel='alternate' hreflang='en' href='{BASE}en/'>",
         f"<link rel='alternate' hreflang='x-default' href='{BASE}'>",
         f"<link rel='preconnect' href='https://fonts.googleapis.com'>",
         f"<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>",
         f"<link rel='stylesheet' href='{FONTS}'>",
         f"<style>{COMMON_CSS}{CSS}</style>",
         "<header class='site-header'>",
         f"<div class='lang'><span>{'Español' if lang == 'es' else 'English'}</span> "
         f"<a href='{other_path}' hreflang='{other}'>{c['other_lang']}</a></div>",
         f"<h1>{LOGO_SVG}Sub <span>Nocte</span></h1>",
         "<p class='verse'>ibant obscuri sola sub nocte per umbram — Virgil, <i>Aeneid</i> VI</p>",
         f"<p class='lede'>{c['claim']}</p>",
         figures(fc, lang),
         "</header>",
         "<main class='wrap'>",
         f"<div class='beta-note'>{c['beta']}</div>"]

    if fc is not None and not fc.empty:
        nights = sorted(fc["night"].unique())
        p += [f"<h2>{c['h_forecast']}</h2><p class='sub'>"
              + c["sub_forecast"].format(date=_date(today, lang), nights=len(nights),
                                         cities=fc["city"].nunique()) + "</p>",
              f"<p>{c['relative']}</p>", f"<p class='sub'>{c['peak']}</p>",
              calendar(fc, lang)]
        alerts = fc[fc["level"].isin(["high", "very high"])]
        p += nights_to_switch_off(alerts, lang) if not alerts.empty else [f"<p>{c['no_alert']}</p>"]
    else:
        p.append(f"<h2>{c['h_forecast']}</h2><p class='sub'>{c['no_forecast']}</p>")

    p += [f"<h2>{c['h_todo']}</h2><p class='sub'>{c['sub_todo']}</p><div class='cards'>"]
    p += [f"<div><b>{t}</b><p>{d}</p></div>" for t, d in c["cards"]]
    p.append("</div>")

    if rk is not None and not rk.empty:
        seasons = set(rk["season"])
        season = "autumn" if today.month >= 7 else "spring"
        season = season if season in seasons else rk["season"].iat[0]
        p += [f"<h2>{c['h_ranking']}</h2><p class='sub'>"
              + c["sub_ranking"].format(season=SEASON_NAME[lang].get(season, season)) + "</p>",
              ranking_table(rk, season, lang),
              f"<p class='sub'>{c['note_ranking']}</p>"]

    p += ["</main>", method_section(lang), "<div class='wrap'>"]

    if links:
        p += [f"<h2>{c['h_reports']}</h2><p class='sub'>{c['sub_reports']}</p><ul>"]
        p += [f"<li><a href='{prefix}{e}'>{c['reports'].get(e.rsplit('/', 1)[-1], e)}</a></li>"
              for e in links]
        p.append(f"</ul><p class='sub'>{c['note_reports']}</p>")

    p += [f"<h2>{c['h_not']}</h2><ul>"] + [f"<li>{x}</li>" for x in c["not_this"]] + ["</ul>"]
    p += [f"<h2>{c['h_data']}</h2><p class='data-note'>{c['data']}</p><p class='data-note'>{c['cornell']}</p>",
          "</div>", site_footer(lang, today), "</html>"]
    return "\n".join(p)


def build(fc: pd.DataFrame | None, rk: pd.DataFrame | None, reports: list[Path], out_dir: Path,
          log=print) -> list[Path]:
    """Write `index.html` (Spanish) and `en/index.html` (English) into `out_dir`.

    Pages serves the repository root, so the reports are linked where they already are (`output/`) instead
    of being duplicated; the English page lives one level down and its paths carry `../`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    links = [f.relative_to(out_dir).as_posix() for f in reports if f.exists()]
    (out_dir / ".nojekyll").touch()  # let Pages serve the files as they are, without running Jekyll
    today = dt.datetime.now(dt.timezone.utc).date()
    if fc is not None and not fc.empty:
        # the download starts the day before so 24 h trends can be computed: that night is already gone
        fc = fc[pd.to_datetime(fc["night"]).dt.date >= today]

    written = []
    for lang in LANGS:
        dest = out_dir / "index.html" if lang == "es" else out_dir / "en" / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        prefix = "" if lang == "es" else "../"
        dest.write_text(_page(fc, rk, links, lang, prefix, today), encoding="utf-8", newline="\n")
        log(f"{dest} ({dest.stat().st_size / 1000:.0f} kB)")
        written.append(dest)
    log(f"{len(links)} reports linked")
    return written
