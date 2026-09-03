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

CSS = """
:root{--ink:#1b1f24;--soft:#5b646e;--line:#dde3ea;--bg:#fff;--box:#f7f9fb;--accent:#1d4e6f}
*{box-sizing:border-box}
body{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;color:var(--ink);background:var(--bg)}
.wrap{max-width:900px;margin:0 auto;padding:0 20px}
header{background:linear-gradient(180deg,#0d1b26,#16303f);color:#eaf1f6;padding:44px 0 34px;position:relative}
header h1{margin:0;font-size:44px;letter-spacing:-.5px;font-weight:600}
header .verse{margin:6px 0 0;font-style:italic;color:#9fb6c6;font-size:15px}
header p.claim{margin:16px 0 0;font-size:18px;color:#cddbe5;max-width:640px}
.lang{position:absolute;top:16px;right:20px;font-size:13px}
.lang a,.lang span{padding:3px 9px;border-radius:999px;text-decoration:none}
.lang a{color:#cddbe5;border:1px solid #35566b}
.lang span{background:#eaf1f6;color:#12222d;border:1px solid #eaf1f6}
.beta-note{background:#fff6e0;border:1px solid #f0d79a;border-radius:8px;padding:12px 16px;margin:22px 0;font-size:14.5px}
h2{margin:38px 0 6px;font-size:24px;letter-spacing:-.2px}
h2+p.sub{margin:0 0 16px;color:var(--soft);font-size:15px}
h3{margin:26px 0 8px;font-size:18px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:right}
th{color:var(--soft);font-weight:600;text-align:right}
td:first-child,th:first-child{text-align:left}
.cal{overflow-x:auto;margin:8px 0 6px}
.cal table{width:auto;min-width:100%}
.cal td.n{text-align:center;font-size:12px;white-space:nowrap;border:2px solid #fff;border-radius:4px}
.cal th{font-size:12px;text-align:center;line-height:1.25}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--soft);margin:6px 0 0}
.legend span i{display:inline-block;width:13px;height:13px;border-radius:3px;vertical-align:-2px;margin-right:5px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:16px 0}
.cards div{background:var(--box);border:1px solid var(--line);border-radius:8px;padding:14px 16px}
.cards b{display:block;font-size:15px;margin-bottom:4px}
.cards p{margin:0;font-size:14px;color:var(--soft)}
ul{padding-left:20px}li{margin:5px 0}
a{color:var(--accent)}
footer{margin:56px 0 0;padding:26px 0 40px;border-top:1px solid var(--line);color:var(--soft);font-size:13.5px}
.pill{display:inline-block;background:var(--box);border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:13px;color:var(--soft)}
@media (max-width:620px){header h1{font-size:34px}h2{font-size:21px}.lang{position:static;margin-bottom:14px}}
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
        "peak": "En pleno pico de la temporada es normal que muchas ciudades salgan altas a la vez: el "
                "percentil se mide sobre la temporada entera, que incluye sus semanas flojas.",
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
        "sub_method": "Sin acrónimos, en cuatro pasos.",
        "method": [
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
        "h_reports": "Informes técnicos",
        "sub_reports": "Cada fase con sus figuras, sus tablas y sus limitaciones.",
        "reports": {
            "phase0.html": "Fase 0 — ¿ven aves los radares españoles renovados?",
            "phase1.html": "Fase 1 — histórico 2016-2026 y climatologías por radar",
            "phase2.html": "Fase 2 — el modelo meteorológico y su validación",
            "phase3.html": "Fase 3 — previsión por ciudad",
            "ranking.html": "Ranking de exposición a la luz artificial",
            "design.html": "Documento de diseño del proyecto",
        },
        "note_reports": "Los informes técnicos están en inglés.",
        "h_not": "Lo que esto no es",
        "not_this": [
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
        "peak": "At the peak of the season it is normal for many cities to come out high at once: the "
                "percentile is measured over the whole season, quiet weeks included.",
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
        "sub_method": "No acronyms, in four steps.",
        "method": [
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
        "h_reports": "Technical reports",
        "sub_reports": "Each phase with its figures, its tables and its limitations.",
        "reports": {
            "phase0.html": "Phase 0 — do the renewed Spanish radars see birds?",
            "phase1.html": "Phase 1 — 2016-2026 archive and per-radar climatologies",
            "phase2.html": "Phase 2 — the weather model and its validation",
            "phase3.html": "Phase 3 — city-level forecast",
            "ranking.html": "Artificial light exposure ranking",
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
            "speed, and the European archive stopped publishing it in France in 2021 and almost always in "
            "Spain.",
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
         f"<meta name='description' content='{c['description']}'>",
         f"<link rel='alternate' hreflang='es' href='{BASE}'>",
         f"<link rel='alternate' hreflang='en' href='{BASE}en/'>",
         f"<link rel='alternate' hreflang='x-default' href='{BASE}'>",
         f"<style>{CSS}</style>",
         "<header><div class='wrap'>",
         f"<div class='lang'><span>{'Español' if lang == 'es' else 'English'}</span> "
         f"<a href='{other_path}' hreflang='{other}'>{c['other_lang']}</a></div>",
         "<h1>Sub Nocte</h1>",
         "<p class='verse'>ibant obscuri sola sub nocte per umbram — Virgil, <i>Aeneid</i> VI</p>",
         f"<p class='claim'>{c['claim']}</p></div></header>",
         "<div class='wrap'>",
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

    p += [f"<h2>{c['h_method']}</h2><p class='sub'>{c['sub_method']}</p><ol>"]
    p += [f"<li>{step}</li>" for step in c["method"]]
    p.append("</ol>")

    if links:
        p += [f"<h2>{c['h_reports']}</h2><p class='sub'>{c['sub_reports']}</p><ul>"]
        p += [f"<li><a href='{prefix}{e}'>{c['reports'].get(e.rsplit('/', 1)[-1], e)}</a></li>"
              for e in links]
        p.append(f"</ul><p class='sub'>{c['note_reports']}</p>")

    p += [f"<h2>{c['h_not']}</h2><ul>"] + [f"<li>{x}</li>" for x in c["not_this"]] + ["</ul>"]
    p += [f"<h2>{c['h_data']}</h2><p>{c['data']}</p><p>{c['cornell']}</p>",
          f"<footer><p>{c['footer']}</p><p>{c['generated'].format(date=_date(today, lang))}</p></footer>",
          "</div></html>"]
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
