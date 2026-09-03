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

IDIOMAS = ("es", "en")

COLOR = {"bajo": "#e9edf2", "moderado": "#ffd98e", "alto": "#f08c1e", "muy alto": "#b32d1f"}
TEXTO = {"muy alto": "#fff", "alto": "#3a2100"}
PESO = {"bajo": 0, "moderado": 1, "alto": 2, "muy alto": 3}

# los niveles viajan en los datos en español; en la página se muestran en el idioma de la página
NIVEL = {"es": {n: n for n in COLOR},
         "en": {"bajo": "low", "moderado": "moderate", "alto": "high", "muy alto": "very high"}}
TEMPORADA = {"es": {"primavera": "primavera", "otoño": "otoño"},
             "en": {"primavera": "spring", "otoño": "autumn"}}
PAIS = {"es": {"ES": "España", "PT": "Portugal", "FR": "Francia"},
        "en": {"ES": "Spain", "PT": "Portugal", "FR": "France"}}
MESES = {"es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
         "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]}
MESES_LARGO = {"es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                      "septiembre", "octubre", "noviembre", "diciembre"],
               "en": ["January", "February", "March", "April", "May", "June", "July", "August",
                      "September", "October", "November", "December"]}
DIAS = {"es": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"],
        "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}

BASE = "https://asensio94.github.io/sub-nocte/"
REPO = "https://github.com/Asensio94/sub-nocte"

CSS = """
:root{--tinta:#1b1f24;--suave:#5b646e;--linea:#dde3ea;--fondo:#fff;--caja:#f7f9fb;--acento:#1d4e6f}
*{box-sizing:border-box}
body{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;color:var(--tinta);background:var(--fondo)}
.env{max-width:900px;margin:0 auto;padding:0 20px}
header{background:linear-gradient(180deg,#0d1b26,#16303f);color:#eaf1f6;padding:44px 0 34px;position:relative}
header h1{margin:0;font-size:44px;letter-spacing:-.5px;font-weight:600}
header .verso{margin:6px 0 0;font-style:italic;color:#9fb6c6;font-size:15px}
header p.claim{margin:16px 0 0;font-size:18px;color:#cddbe5;max-width:640px}
.idioma{position:absolute;top:16px;right:20px;font-size:13px}
.idioma a,.idioma span{padding:3px 9px;border-radius:999px;text-decoration:none}
.idioma a{color:#cddbe5;border:1px solid #35566b}
.idioma span{background:#eaf1f6;color:#12222d;border:1px solid #eaf1f6}
.aviso-beta{background:#fff6e0;border:1px solid #f0d79a;border-radius:8px;padding:12px 16px;margin:22px 0;font-size:14.5px}
h2{margin:38px 0 6px;font-size:24px;letter-spacing:-.2px}
h2+p.sub{margin:0 0 16px;color:var(--suave);font-size:15px}
h3{margin:26px 0 8px;font-size:18px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border-bottom:1px solid var(--linea);padding:6px 8px;text-align:right}
th{color:var(--suave);font-weight:600;text-align:right}
td:first-child,th:first-child{text-align:left}
.cal{overflow-x:auto;margin:8px 0 6px}
.cal table{width:auto;min-width:100%}
.cal td.n{text-align:center;font-size:12px;white-space:nowrap;border:2px solid #fff;border-radius:4px}
.cal th{font-size:12px;text-align:center;line-height:1.25}
.leyenda{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--suave);margin:6px 0 0}
.leyenda span i{display:inline-block;width:13px;height:13px;border-radius:3px;vertical-align:-2px;margin-right:5px}
.tarjetas{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:16px 0}
.tarjetas div{background:var(--caja);border:1px solid var(--linea);border-radius:8px;padding:14px 16px}
.tarjetas b{display:block;font-size:15px;margin-bottom:4px}
.tarjetas p{margin:0;font-size:14px;color:var(--suave)}
ul{padding-left:20px}li{margin:5px 0}
a{color:var(--acento)}
footer{margin:56px 0 0;padding:26px 0 40px;border-top:1px solid var(--linea);color:var(--suave);font-size:13.5px}
.pill{display:inline-block;background:var(--caja);border:1px solid var(--linea);border-radius:999px;padding:2px 10px;font-size:13px;color:var(--suave)}
@media (max-width:620px){header h1{font-size:34px}h2{font-size:21px}.idioma{position:static;margin-bottom:14px}}
"""

# Toda la prosa de la página, en los dos idiomas. Se guarda entera y literal en cada idioma en vez de
# ensamblarla por trozos: es más largo pero se lee y se corrige como un texto, que es lo que es.
COPY: dict[str, dict[str, str]] = {
    "es": {
        "titulo": "Sub Nocte · migración nocturna de aves en Europa",
        "descripcion": "Previsión por ciudad de la intensidad de migración nocturna de aves en Europa, "
                       "con avisos de luces fuera, sobre los perfiles de radar abiertos de Aloft.",
        "otro_idioma": "English",
        "claim": "Cada noche de primavera y de otoño, millones de aves cruzan Europa en la oscuridad. Unas "
                 "pocas noches concentran la mitad del paso. Esta página intenta decir <b>cuáles</b>, ciudad "
                 "por ciudad, para que se puedan apagar las luces justo esas noches.",
        "beta": "<b>Versión técnica, no un servicio en producción.</b> El modelo está validado (ver más "
                "abajo) pero ninguna de estas ciudades tiene un radar cerca con el que comprobar la previsión "
                "al día siguiente. Úsese como indicación, no como dato cerrado.",
        "h_prevision": "Próximas noches",
        "sub_prevision": "Actualizado el {fecha}. {noches} noches, {ciudades} ciudades.",
        "relativo": "<b>El nivel es relativo a cada ciudad</b>, no una cantidad absoluta de aves: «muy alto» "
                    "significa que esa noche entra en el 10 % más intenso del historial <i>de esa misma "
                    "ciudad</i>. Así el aviso quiere decir lo mismo en Sevilla y en Bilbao, aunque por "
                    "Sevilla pase mucha más ave.",
        "pico": "En pleno pico de la temporada es normal que muchas ciudades salgan altas a la vez: el "
                "percentil se mide sobre la temporada entera, que incluye sus semanas flojas.",
        "sin_prevision": "Previsión no disponible todavía.",
        "h_apagar": "Noches para apagar",
        "muy_alto_en": "<b>muy alto</b> en {ciudades}",
        "alto_en_una": "alto en 1 ciudad más",
        "alto_en_varias": "alto en {n} ciudades más",
        "sin_aviso": "Ninguna ciudad supera su percentil 75 en este periodo: no hay motivo para un aviso.",
        "h_hacer": "Qué hacer una noche de aviso",
        "sub_hacer": "Lo que reduce las colisiones y la desorientación, por orden de eficacia y de facilidad.",
        "tarjetas": [
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
        "sub_ranking": "Ranking de exposición en {temporada}: el brillo artificial del cielo de cada ciudad "
                       "multiplicado por la densidad de aves prevista en sus diez noches más intensas, "
                       "normalizado a 100 en la ciudad más expuesta del conjunto. Sigue el método de Horton y "
                       "col. (2019).",
        "col_ciudad": "ciudad",
        "col_cielo": "cielo vs natural",
        "col_aves": "aves/km² en noches punta",
        "col_exposicion": "exposición",
        "nota_ranking": "La columna «cielo vs natural» dice cuántas veces más brillante es el cielo de esa "
                        "ciudad que uno sin luz artificial. Aviso: entre la ciudad más y la menos iluminada "
                        "hay un factor 3-4, mientras que en aves apenas hay un factor 2, así que el orden lo "
                        "marca sobre todo la luz.",
        "h_metodo": "Cómo se calcula",
        "sub_metodo": "Sin acrónimos, en cuatro pasos.",
        "metodo": [
            "<b>Los radares meteorológicos ven aves.</b> Además de la lluvia, un radar mide el eco de los "
            "animales que cruzan su haz. La red europea publica en abierto un perfil vertical cada 5-15 "
            "minutos con cuántas aves hay por kilómetro cúbico a cada altura. Nosotros resumimos cada noche "
            "en una cifra: la densidad media de aves en la columna de aire, en aves por kilómetro cuadrado.",
            "<b>La meteorología explica buena parte de esa cifra.</b> Con once años de noches de 55 radares "
            "de España, Portugal y Francia entrenamos dos modelos: uno estima cuánta ave habrá y otro decide "
            "si la noche va a ser de paso fuerte. Las variables son el viento a la altura a la que vuelan "
            "(750, 1.500 y 3.000 metros), descompuesto en lo que empuja hacia el rumbo migratorio y lo que "
            "desvía; la temperatura y su cambio en 24 horas; la humedad, la nubosidad, la lluvia y la "
            "presión; y el día del año.",
            "<b>La validación se hace quitando radares enteros</b>, no noches al azar. Es la única prueba "
            "honesta para una ciudad sin radar: se entrena sin ese radar y se le pide predecirlo a ciegas. "
            "Así el modelo captura un <b>34 % de las noches de paso fuerte</b> frente al 10 % que daría el "
            "azar, con un 66 % de falsas alarmas. Es decir: acierta tres veces más que tirar una moneda, y se "
            "equivoca a menudo.",
            "<b>El aviso se calibra ciudad a ciudad.</b> Se corre el modelo sobre cinco años de meteorología "
            "en el punto exacto de la ciudad y los niveles se cortan por los percentiles de esa "
            "distribución. Por eso el aviso no necesita radar en la ciudad y significa lo mismo en todas.",
        ],
        "h_informes": "Informes técnicos",
        "sub_informes": "Cada fase con sus figuras, sus tablas y sus limitaciones.",
        "informes": {
            "fase0.html": "Fase 0 — ¿ven aves los radares españoles renovados?",
            "fase1.html": "Fase 1 — histórico 2016-2026 y climatologías por radar",
            "fase2.html": "Fase 2 — el modelo meteorológico y su validación",
            "fase3.html": "Fase 3 — previsión por ciudad",
            "ranking.html": "Ranking de exposición a la luz artificial",
            "diseno.html": "Documento de diseño del proyecto",
        },
        "nota_informes": "Los informes están en español; la traducción al inglés está pendiente.",
        "h_no_es": "Lo que esto no es",
        "no_es": [
            "No es un recuento de aves sobre tu tejado: es la densidad media en toda la columna de aire, la "
            "mayor parte de ella entre 200 y 3.000 metros de altura.",
            "No distingue especies. Un radar meteorológico no sabe si el eco es un zorzal o un mosquitero.",
            "En otoño y en el sur, parte de la señal puede ser insecto. Hace falta la velocidad de vuelo para "
            "separarlos y el archivo europeo dejó de publicarla en Francia en 2021 y casi siempre en España.",
            "El pronóstico se degrada con los días: la primera noche es fiable, la séptima mucho menos.",
            "Las cuatro ciudades españolas con radar nuevo son el caso difícil del modelo (mide bien el orden "
            "de las noches, pero el perfil llega truncado a seis capas). No conviene tomar decisiones firmes "
            "ahí hasta la temporada de 2027.",
        ],
        "h_datos": "Datos, método y crédito",
        "datos": "Perfiles verticales de aves: <a href='https://aloftdata.eu'>Aloft</a> (Desmet y col. 2025), "
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
        "pie": "Proyecto abierto y sin ánimo de lucro. Todo el código y los datos derivados están en "
               f"<a href='{REPO}'>github.com/Asensio94/sub-nocte</a> (licencia MIT); la página se regenera "
               "desde esos mismos ficheros, así que cualquiera puede reproducir lo que dice.",
        "generado": "Generado el {fecha}.",
    },
    "en": {
        "titulo": "Sub Nocte · nocturnal bird migration in Europe",
        "descripcion": "City-level forecast of nocturnal bird migration intensity in Europe, with lights-out "
                       "alerts, built on the open radar profiles published by Aloft.",
        "otro_idioma": "Español",
        "claim": "Every spring and autumn night, millions of birds cross Europe in the dark. A handful of "
                 "nights carry half of the passage. This page tries to say <b>which ones</b>, city by city, "
                 "so that the lights can go out on exactly those nights.",
        "beta": "<b>Technical preview, not a production service.</b> The model is validated (see below), but "
                "none of these cities has a radar close enough to check the forecast the next morning. Treat "
                "it as an indication, not a settled figure.",
        "h_prevision": "The nights ahead",
        "sub_prevision": "Updated on {fecha}. {noches} nights, {ciudades} cities.",
        "relativo": "<b>The level is relative to each city</b>, not an absolute number of birds: “very high” "
                    "means the night falls in the most intense 10 % of the record <i>for that same city</i>. "
                    "That way the alert means the same thing in Seville and in Bilbao, even though far more "
                    "birds pass over Seville.",
        "pico": "At the peak of the season it is normal for many cities to come out high at once: the "
                "percentile is measured over the whole season, quiet weeks included.",
        "sin_prevision": "Forecast not available yet.",
        "h_apagar": "Nights to switch off",
        "muy_alto_en": "<b>very high</b> in {ciudades}",
        "alto_en_una": "high in 1 more city",
        "alto_en_varias": "high in {n} more cities",
        "sin_aviso": "No city exceeds its 75th percentile in this period: there is no reason for an alert.",
        "h_hacer": "What to do on an alert night",
        "sub_hacer": "What actually reduces collisions and disorientation, ordered by effect and by ease.",
        "tarjetas": [
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
        "sub_ranking": "Exposure ranking for {temporada}: the artificial brightness of each city's sky "
                       "multiplied by the bird density forecast on its ten most intense nights, normalised "
                       "to 100 at the most exposed city in the set. It follows the method of Horton et al. "
                       "(2019).",
        "col_ciudad": "city",
        "col_cielo": "sky vs natural",
        "col_aves": "birds/km² on peak nights",
        "col_exposicion": "exposure",
        "nota_ranking": "The “sky vs natural” column says how many times brighter that city's sky is than a "
                        "sky with no artificial light. A caveat: between the most and the least lit city "
                        "there is a factor of 3-4, while in birds there is barely a factor of 2, so the "
                        "ordering is driven mostly by light.",
        "h_metodo": "How it is computed",
        "sub_metodo": "No acronyms, in four steps.",
        "metodo": [
            "<b>Weather radars see birds.</b> Besides rain, a radar measures the echo of the animals crossing "
            "its beam. The European network openly publishes a vertical profile every 5-15 minutes giving "
            "how many birds there are per cubic kilometre at each height. We summarise each night in a "
            "single figure: the mean bird density in the air column, in birds per square kilometre.",
            "<b>Weather explains a good part of that figure.</b> Using eleven years of nights from 55 radars "
            "in Spain, Portugal and France we train two models: one estimates how many birds there will be "
            "and the other decides whether the night will carry heavy passage. The variables are the wind at "
            "the heights where they fly (750, 1,500 and 3,000 metres), split into the part pushing along the "
            "migratory heading and the part pushing sideways; temperature and its 24-hour change; humidity, "
            "cloud cover, rain and pressure; and the day of the year.",
            "<b>Validation leaves whole radars out</b>, not random nights. It is the only honest test for a "
            "city without a radar: the model is trained without that radar and then asked to predict it "
            "blind. Done that way it captures <b>34 % of the heavy-passage nights</b> against the 10 % that "
            "chance would give, with 66 % false alarms. In other words: three times better than a coin "
            "flip, and wrong fairly often.",
            "<b>The alert is calibrated city by city.</b> The model is run over five years of weather at the "
            "city's exact location and the levels are cut at the percentiles of that distribution. That is "
            "why the alert needs no radar in the city and means the same thing everywhere.",
        ],
        "h_informes": "Technical reports",
        "sub_informes": "Each phase with its figures, its tables and its limitations.",
        "informes": {
            "fase0.html": "Phase 0 — do the renewed Spanish radars see birds?",
            "fase1.html": "Phase 1 — 2016-2026 archive and per-radar climatologies",
            "fase2.html": "Phase 2 — the weather model and its validation",
            "fase3.html": "Phase 3 — city-level forecast",
            "ranking.html": "Artificial light exposure ranking",
            "diseno.html": "Project design document",
        },
        "nota_informes": "The reports are in Spanish; an English translation is still pending.",
        "h_no_es": "What this is not",
        "no_es": [
            "It is not a count of the birds over your roof: it is the mean density across the whole air "
            "column, most of it between 200 and 3,000 metres up.",
            "It does not tell species apart. A weather radar cannot know whether the echo is a thrush or a "
            "warbler.",
            "In autumn and in the south, part of the signal may be insects. Separating them needs flight "
            "speed, and the European archive stopped publishing it in France in 2021 and almost always in "
            "Spain.",
            "The forecast decays with lead time: the first night is reliable, the seventh much less so.",
            "The four Spanish cities with a renewed radar are the model's hard case (it ranks their nights "
            "reasonably well, but the profile arrives truncated to six layers). Firm decisions there are "
            "better left until the 2027 season.",
        ],
        "h_datos": "Data, method and credit",
        "datos": "Bird vertical profiles: <a href='https://aloftdata.eu'>Aloft</a> (Desmet et al. 2025), "
                 "European weather radar network, CC0. Weather: <a href='https://open-meteo.com'>Open-Meteo"
                 "</a> (CC BY 4.0). Artificial light: Falchi et al. (2016), <i>The new world atlas of "
                 "artificial night sky brightness</i>, Science Advances 2(6):e1600377, and GFZ Data Services "
                 "doi:10.5880/GFZ.1.4.2016.001 — the original files are not redistributed here, only derived "
                 "results. Method: Van Doren & Horton (2018) for the model, Horton et al. (2019) for light "
                 "exposure, Horton et al. (2021) for the concentration of passage into few nights.",
        "cornell": "Sub Nocte follows the approach of <a href='https://birdcast.org'>BirdCast</a>, Cornell "
                   "University's service for the United States, and has no affiliation with it.",
        "pie": "Open, non-profit project. All the code and derived data live at "
               f"<a href='{REPO}'>github.com/Asensio94/sub-nocte</a> (MIT licence); the page is regenerated "
               "from those same files, so anyone can reproduce what it says.",
        "generado": "Generated on {fecha}.",
    },
}


def _fecha(d: dt.date, idioma: str) -> str:
    mes = MESES_LARGO[idioma][d.month - 1]
    return f"{d.day} de {mes} de {d.year}" if idioma == "es" else f"{d.day} {mes} {d.year}"


def _noche(d: pd.Timestamp, idioma: str) -> str:
    return f"{DIAS[idioma][d.weekday()]} {d.day} {MESES[idioma][d.month - 1]}"


def _celda(nivel: str, idioma: str) -> str:
    return (f"<td class='n' style='background:{COLOR.get(nivel, '#f6f6f6')};"
            f"color:{TEXTO.get(nivel, '#3a3f45')}'>{NIVEL[idioma].get(nivel, nivel)}</td>")


def calendario(prev: pd.DataFrame, idioma: str) -> str:
    """Tabla ciudad × noche con el nivel de aviso, con las ciudades de más aviso arriba."""
    c = COPY[idioma]
    prev = prev.assign(w=prev["nivel"].map(PESO).fillna(0))
    orden = prev.groupby("ciudad")["w"].max().sort_values(ascending=False).index
    noches = sorted(prev["night"].unique())
    cab = "".join(f"<th>{DIAS[idioma][pd.Timestamp(n).weekday()]}<br>{pd.Timestamp(n).day} "
                  f"{MESES[idioma][pd.Timestamp(n).month - 1]}</th>" for n in noches)
    filas = []
    for ciudad in orden:
        g = prev[prev["ciudad"] == ciudad].set_index("night")
        pais = PAIS[idioma].get(g["pais"].iat[0], g["pais"].iat[0])
        celdas = "".join(_celda(g.loc[n, "nivel"], idioma) if n in g.index else "<td class='n'></td>"
                         for n in noches)
        filas.append(f"<tr><td><b>{ciudad}</b> <span class='pill'>{pais}</span></td>{celdas}</tr>")
    leyenda = "".join(f"<span><i style='background:{COLOR[n]}'></i>{NIVEL[idioma][n]}</span>"
                      for n in ("bajo", "moderado", "alto", "muy alto"))
    return (f"<div class='cal'><table><tr><th>{c['col_ciudad']}</th>{cab}</tr>{''.join(filas)}</table></div>"
            f"<div class='leyenda'>{leyenda}</div>")


def noches_para_apagar(alto: pd.DataFrame, idioma: str) -> list[str]:
    """Una línea por noche: qué ciudades están en «muy alto» y cuántas más en «alto»."""
    c = COPY[idioma]
    p = [f"<h3>{c['h_apagar']}</h3><ul>"]
    for noche, g in alto.groupby("night"):
        muy = sorted(g[g["nivel"] == "muy alto"]["ciudad"])
        otras = len(g) - len(muy)
        partes = []
        if muy:
            partes.append(c["muy_alto_en"].format(ciudades=", ".join(muy)))
        if otras:
            partes.append(c["alto_en_una"] if otras == 1 else c["alto_en_varias"].format(n=otras))
        p.append(f"<li><b>{_noche(pd.Timestamp(noche), idioma)}</b>: " + "; ".join(partes) + ".</li>")
    p.append("</ul>")
    return p


def tabla_ranking(rk: pd.DataFrame, temporada: str, idioma: str, n: int = 12) -> str:
    c = COPY[idioma]
    g = rk[rk["season"] == temporada].nlargest(n, "exposicion_picos")
    filas = "".join(
        f"<tr><td>{i}. <b>{r.ciudad}</b> <span class='pill'>{PAIS[idioma].get(r.pais, r.pais)}</span></td>"
        f"<td>{r.veces_natural:.0f}×</td><td>{r.vid_picos:.0f}</td><td>{r.exposicion_picos:.0f}</td></tr>"
        for i, r in enumerate(g.itertuples(index=False), 1))
    return (f"<table><tr><th>{c['col_ciudad']}</th><th>{c['col_cielo']}</th><th>{c['col_aves']}</th>"
            f"<th>{c['col_exposicion']}</th></tr>{filas}</table>")


def _pagina(prev: pd.DataFrame | None, rk: pd.DataFrame | None, enlaces: list[str], idioma: str,
            prefijo: str, hoy: dt.date) -> str:
    """Arma el HTML completo de una de las dos páginas. `prefijo` corrige las rutas relativas."""
    c = COPY[idioma]
    otro = "en" if idioma == "es" else "es"
    ruta_otro = f"{prefijo}en/" if idioma == "es" else prefijo
    p = [f"<!doctype html><html lang='{idioma}'><meta charset='utf-8'>",
         "<meta name='viewport' content='width=device-width,initial-scale=1'>",
         f"<title>{c['titulo']}</title>",
         f"<meta name='description' content='{c['descripcion']}'>",
         f"<link rel='alternate' hreflang='es' href='{BASE}'>",
         f"<link rel='alternate' hreflang='en' href='{BASE}en/'>",
         f"<link rel='alternate' hreflang='x-default' href='{BASE}'>",
         f"<style>{CSS}</style>",
         "<header><div class='env'>",
         f"<div class='idioma'><span>{'Español' if idioma == 'es' else 'English'}</span> "
         f"<a href='{ruta_otro}' hreflang='{otro}'>{c['otro_idioma']}</a></div>",
         "<h1>Sub Nocte</h1>",
         "<p class='verso'>ibant obscuri sola sub nocte per umbram — Virgilio, <i>Eneida</i> VI</p>",
         f"<p class='claim'>{c['claim']}</p></div></header>",
         "<div class='env'>",
         f"<div class='aviso-beta'>{c['beta']}</div>"]

    if prev is not None and not prev.empty:
        noches = sorted(prev["night"].unique())
        p += [f"<h2>{c['h_prevision']}</h2><p class='sub'>"
              + c["sub_prevision"].format(fecha=_fecha(hoy, idioma), noches=len(noches),
                                          ciudades=prev["ciudad"].nunique()) + "</p>",
              f"<p>{c['relativo']}</p>", f"<p class='sub'>{c['pico']}</p>",
              calendario(prev, idioma)]
        alto = prev[prev["nivel"].isin(["alto", "muy alto"])]
        p += noches_para_apagar(alto, idioma) if not alto.empty else [f"<p>{c['sin_aviso']}</p>"]
    else:
        p.append(f"<h2>{c['h_prevision']}</h2><p class='sub'>{c['sin_prevision']}</p>")

    p += [f"<h2>{c['h_hacer']}</h2><p class='sub'>{c['sub_hacer']}</p><div class='tarjetas'>"]
    p += [f"<div><b>{t}</b><p>{d}</p></div>" for t, d in c["tarjetas"]]
    p.append("</div>")

    if rk is not None and not rk.empty:
        temporadas = set(rk["season"])
        temporada = "otoño" if hoy.month >= 7 else "primavera"
        temporada = temporada if temporada in temporadas else rk["season"].iat[0]
        p += [f"<h2>{c['h_ranking']}</h2><p class='sub'>"
              + c["sub_ranking"].format(temporada=TEMPORADA[idioma].get(temporada, temporada)) + "</p>",
              tabla_ranking(rk, temporada, idioma),
              f"<p class='sub'>{c['nota_ranking']}</p>"]

    p += [f"<h2>{c['h_metodo']}</h2><p class='sub'>{c['sub_metodo']}</p><ol>"]
    p += [f"<li>{paso}</li>" for paso in c["metodo"]]
    p.append("</ol>")

    if enlaces:
        p += [f"<h2>{c['h_informes']}</h2><p class='sub'>{c['sub_informes']}</p><ul>"]
        p += [f"<li><a href='{prefijo}{e}'>{c['informes'].get(e.rsplit('/', 1)[-1], e)}</a></li>"
              for e in enlaces]
        p.append(f"</ul><p class='sub'>{c['nota_informes']}</p>")

    p += [f"<h2>{c['h_no_es']}</h2><ul>"] + [f"<li>{x}</li>" for x in c["no_es"]] + ["</ul>"]
    p += [f"<h2>{c['h_datos']}</h2><p>{c['datos']}</p><p>{c['cornell']}</p>",
          f"<footer><p>{c['pie']}</p><p>{c['generado'].format(fecha=_fecha(hoy, idioma))}</p></footer>",
          "</div></html>"]
    return "\n".join(p)


def construir(prev: pd.DataFrame | None, rk: pd.DataFrame | None, informes: list[Path], out_dir: Path,
              log=print) -> list[Path]:
    """Escribe `index.html` (español) y `en/index.html` (inglés) en `out_dir`.

    Pages sirve la raíz del repositorio, así que los informes se enlazan donde ya están (`output/`) en lugar
    de duplicarlos; la página inglesa vive un nivel más abajo y sus rutas llevan `../`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    enlaces = [f.relative_to(out_dir).as_posix() for f in informes if f.exists()]
    (out_dir / ".nojekyll").touch()  # que Pages sirva los ficheros tal cual, sin pasarlos por Jekyll
    hoy = dt.datetime.now(dt.timezone.utc).date()
    if prev is not None and not prev.empty:
        # la descarga arranca el día anterior para poder calcular tendencias de 24 h: esa noche ya ha pasado
        prev = prev[pd.to_datetime(prev["night"]).dt.date >= hoy]

    escritos = []
    for idioma in IDIOMAS:
        destino = out_dir / "index.html" if idioma == "es" else out_dir / "en" / "index.html"
        destino.parent.mkdir(parents=True, exist_ok=True)
        prefijo = "" if idioma == "es" else "../"
        destino.write_text(_pagina(prev, rk, enlaces, idioma, prefijo, hoy), encoding="utf-8", newline="\n")
        log(f"{destino} ({destino.stat().st_size / 1000:.0f} kB)")
        escritos.append(destino)
    log(f"{len(enlaces)} informes enlazados")
    return escritos
