"""The method page (metodo.html, en/method.html): how the forecast is made, and every technical report explained.

The reports are written by their own commands, in English and each with its own look; this page is the way in,
and says for each one what question it answers, so nobody has to open them blind.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import site
from .web import BASE, COMMON_CSS, CSS as SITE_CSS, FAVICON, FONTS, REPO, method_section, site_footer

PAGE = site.PAGES["method"]

# group -> reports, each (path from the root, title, what it answers); the same for both languages but the words
GROUPS = {
    "es": [
        ("Cómo se hizo la previsión, fase a fase", [
            ("output/phase0.html", "Fase 0 — ¿ven aves los radares españoles renovados?",
             "Antes de nada: si los radares de AEMET renovados en 2021-2022 siguen viendo aves por la noche, con "
             "qué dirección y velocidad, y si concuerdan entre sí. Sin esto no habría proyecto."),
            ("output/phase1.html", "Fase 1 — diez años de radar y los umbrales de cada radar",
             "El archivo 2016-2026 noche a noche y, para cada radar y época del año, qué es una noche normal y qué "
             "es una noche fuerte. De aquí salen los niveles «alto» y «muy alto»."),
            ("output/phase2.html", "Fase 2 — ¿predice la meteorología la migración?",
             "El modelo que aprende cómo el viento, la temperatura, la presión y la lluvia mueven la migración, y "
             "su validación dejando fuera radares enteros (AUC 0,77 en Europa, 0,74 en España)."),
            ("output/phase3.html", "Fase 3 — la previsión por ciudad",
             "El modelo aplicado a cada ciudad con la previsión de los próximos siete días, los umbrales en vigor "
             "y sus limitaciones. Es la tabla que resume la portada."),
        ]),
        ("Parques eólicos", [
            ("output/wind.html", "Previsión nocturna por zona eólica",
             "La previsión de la semana para cada zona de España y Portugal, con lo que costaría parar y la "
             "sugerencia de cada noche, en tablas y figuras. La versión para leer es "
             "<a href='parques.html'>Parques eólicos</a>."),
            ("output/wind_check.html", "La regla de parada, probada desde 2021",
             "Qué habría hecho la regla en cinco temporadas (noches paradas, producción perdida, migración "
             "cubierta) y si el radar más cercano medía paso fuerte esas noches."),
            ("output/wind_france.html", "Francia — previsión nocturna por zona eólica",
             "Lo mismo para las zonas eólicas de Francia, con sus propios umbrales calculados sobre ERA5."),
            ("output/wind_check_france.html", "Francia — la regla probada desde 2021",
             "La regla de parada aplicada a las zonas francesas y contrastada con los radares de Météo-France."),
        ]),
        ("¿Acierta?", [
            ("output/scorecard.html", "Verificación de las previsiones publicadas",
             "Cada previsión que ya salió en la web, comparada con lo que midieron después los radares: lugar a "
             "lugar, semana a semana y según la antelación."),
        ]),
        ("Luz artificial", [
            ("output/ranking.html", "Ranking de exposición a la luz",
             "Dónde coinciden mucho paso y mucha luz: las ciudades en las que apagar luces las noches fuertes "
             "protege a más aves."),
        ]),
        ("El proyecto", [
            ("docs/proposal/proposal_es.html", "Propuesta a SEO/BirdLife y AEMET",
             "Qué falta para que la previsión se compruebe en horas y no en días: los datos de radar con poco "
             "retraso."),
            ("docs/proposal/proposal_en.html", "La misma propuesta, en inglés",
             "Para Aloft y la red europea de radares OPERA."),
            ("docs/design.html", "Documento de diseño",
             "El planteamiento inicial: qué existe ya en Europa, qué se puede predecir y qué puede salir mal."),
        ]),
    ],
    "en": [
        ("How the forecast was built, phase by phase", [
            ("output/phase0.html", "Phase 0 — do the renewed Spanish radars see birds?",
             "First things first: whether the AEMET radars renewed in 2021-2022 still see birds at night, with what "
             "direction and speed, and whether they agree with each other. Without this there is no project."),
            ("output/phase1.html", "Phase 1 — ten years of radar and each radar's thresholds",
             "The 2016-2026 archive night by night and, for each radar and time of year, what a normal night and a "
             "heavy night are. The «high» and «very high» levels come from here."),
            ("output/phase2.html", "Phase 2 — does the weather predict migration?",
             "The model that learns how wind, temperature, pressure and rain move migration, and its validation "
             "leaving whole radars out (AUC 0.77 in Europe, 0.74 in Spain)."),
            ("output/phase3.html", "Phase 3 — the per-city forecast",
             "The model applied to each city with the forecast for the next seven days, the thresholds in force and "
             "its limitations. It is the table the home page summarises."),
        ]),
        ("Wind farms", [
            ("output/wind.html", "Nightly forecast per wind zone",
             "The week's forecast for each zone in Spain and Portugal, with what stopping would cost and each "
             "night's suggestion, in tables and figures. The version to read is "
             "<a href='windfarms.html'>Wind farms</a>."),
            ("output/wind_check.html", "The stopping rule, tested since 2021",
             "What the rule would have done over five seasons (nights stopped, output lost, migration covered) and "
             "whether the nearest radar measured heavy passage on those nights."),
            ("output/wind_france.html", "France — nightly forecast per wind zone",
             "The same for the French wind zones, with their own thresholds computed on ERA5."),
            ("output/wind_check_france.html", "France — the rule tested since 2021",
             "The stopping rule applied to the French zones and checked against the Météo-France radars."),
        ]),
        ("Does it work?", [
            ("output/scorecard.html", "Checking the published forecasts",
             "Every forecast already published, against what the radars measured afterwards: place by place, week "
             "by week and by lead time."),
        ]),
        ("Artificial light", [
            ("output/ranking.html", "Light exposure ranking",
             "Where heavy passage and much light coincide: the cities where switching lights off on heavy nights "
             "protects the most birds."),
        ]),
        ("The project", [
            ("docs/proposal/proposal_en.html", "Proposal to Aloft and OPERA",
             "What is missing for the forecast to be checked in hours rather than days: radar data with little "
             "delay."),
            ("docs/proposal/proposal_es.html", "The same proposal, in Spanish", "For SEO/BirdLife and AEMET."),
            ("docs/design.html", "Design document",
             "The initial plan, in Spanish: what already exists in Europe, what can be predicted and what can go "
             "wrong."),
        ]),
    ],
}

COPY = {
    "es": {"title": "Sub Nocte · método e informes técnicos",
           "description": "Cómo se calcula la previsión de migración nocturna de Sub Nocte y qué cuenta cada "
                          "informe técnico.",
           "kicker": "Sub Nocte · método", "h1": "Cómo se hace, y dónde está cada cifra",
           "lede": "Primero el método, paso a paso, del eco del radar a la alerta. Después, cada informe técnico "
                   "con la pregunta que responde. Los informes están en inglés y llevan esta misma barra arriba "
                   "para volver.",
           "h_reports": "Los informes técnicos", "missing": "(aún no publicado)",
           "code": "Todo el código, los datos derivados y el historial de cada cambio están en el "
                   "<a href='{repo}'>repositorio</a>."},
    "en": {"title": "Sub Nocte · method and technical reports",
           "description": "How the Sub Nocte nocturnal migration forecast is computed and what each technical "
                          "report covers.",
           "kicker": "Sub Nocte · method", "h1": "How it is done, and where every figure is",
           "lede": "First the method, step by step, from the radar echo to the alert. Then each technical report "
                   "with the question it answers. The reports carry this same bar at the top to come back.",
           "h_reports": "The technical reports", "missing": "(not published yet)",
           "code": "All the code, the derived data and the history of every change are in the "
                   "<a href='{repo}'>repository</a>."},
}


def page(lang: str, today: dt.date, root: Path) -> str:
    c = COPY[lang]
    depth = PAGE[lang].count("/")
    up = "../" * depth
    p = [f"<!doctype html><html lang='{lang}'><meta charset='utf-8'>",
         "<meta name='viewport' content='width=device-width,initial-scale=1'>",
         f"<title>{c['title']}</title>", FAVICON,
         f"<meta name='description' content='{c['description']}'>",
         f"<link rel='alternate' hreflang='es' href='{BASE}{PAGE['es']}'>",
         f"<link rel='alternate' hreflang='en' href='{BASE}{PAGE['en']}'>",
         "<link rel='preconnect' href='https://fonts.googleapis.com'>",
         "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>",
         f"<link rel='stylesheet' href='{FONTS}'>",
         f"<style>{COMMON_CSS}{SITE_CSS}{site.CSS}{CSS}</style>",
         site.page_bar(lang, "method", depth),
         "<header class='site-header'>", f"<p class='kicker'>{c['kicker']}</p>", f"<h1>{c['h1']}</h1>",
         f"<p class='lede'>{c['lede']}</p>", "</header>",
         method_section(lang),
         "<main class='wrap'>", f"<h2 id='informes'>{c['h_reports']}</h2>"]
    for group, items in GROUPS[lang]:
        p.append(f"<h3>{group}</h3><ul class='reports'>")
        for path, title, what in items:
            there = (root / path).exists()
            link = f"<a href='{up}{path}'>{title}</a>" if there else f"{title} <small>{c['missing']}</small>"
            p.append(f"<li>{link}<p>{what}</p></li>")
        p.append("</ul>")
    p += [f"<p class='data-note'>{c['code'].format(repo=REPO)}</p>", "</main>", site_footer(lang, today), "</html>"]
    return "\n".join(p)


def reports() -> list[str]:
    return [path for _, items in GROUPS["es"] for path, _, _ in items]


def build(root: Path, log=print, today: dt.date | None = None) -> list[Path]:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    written = []
    for lang in ("es", "en"):
        dest = root / PAGE[lang]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page(lang, today, root), encoding="utf-8", newline="\n")
        log(f"{dest} ({dest.stat().st_size / 1000:.0f} kB)")
        written.append(dest)
    return written


CSS = """
.kicker{margin:0;font:600 21px/1.2 var(--font-title);text-transform:uppercase;letter-spacing:.08em;color:var(--accent)}
.site-header h1{font-size:clamp(34px,5vw,54px)}
ul.reports{list-style:none;padding:0;margin:8px 0 22px}
ul.reports li{padding:10px 0 4px;border-top:1px solid var(--line)}
ul.reports li>a{font:600 19px/1.25 var(--font-title);text-transform:uppercase;letter-spacing:.03em}
ul.reports li p{margin:4px 0 6px;max-width:72ch}
"""
