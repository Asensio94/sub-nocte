"""The wind farms page (parques.html, en/windfarms.html): tonight's suggestion per wind zone, on a map and in a table.

It reads the same inputs as the routes map (`routes_page.load`) and reuses its zone sheet, so the side panel says
the same thing on both pages. The map is still: one circle per zone, coloured by the night picked.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from . import routes as R
from . import routes_page as RP
from . import site
from .web import (BASE, COMMON_CSS, CSS as SITE_CSS, FAVICON, FONTS, LEVEL_NAME, REPO, _date, _night, _num,
                  site_footer, wind_table)
from .wind import CELL_DEG, CHEAP, CUT_IN, CUT_OUT, EXPENSIVE, MIN_TURBINES, RATED

ADVICE_ORDER = ["stop", "stop at peak hours", "watch", "run"]
PAGE = site.PAGES["farms"]


def upcoming(inp: RP.Inputs, today: dt.date) -> pd.DataFrame | None:
    wf = inp.wind_forecast
    if wf is None:
        return None
    wf = wf[(pd.to_datetime(wf["night"]).dt.date >= today) & wf["level"].notna()]
    return wf if len(wf) else None


def _pct(x: float, lang: str) -> str:
    return RP._pct(x, lang)


def night_table(g: pd.DataFrame, lang: str) -> str:
    """Every zone on one night, the suggestions first and, within them, the largest capacity first."""
    c = COPY[lang]
    w = {a: i for i, a in enumerate(ADVICE_ORDER)}
    g = g.assign(_w=g["advice"].map(w)).sort_values(["_w", "power_mw"], ascending=[True, False])
    rows = []
    for r in g.itertuples():
        name = r.place if isinstance(r.place, str) else r.zone
        rows.append(f"<tr class='{'run' if r.advice == 'run' else 'act'}'><td>{name}<small>{r.zone}</small></td>"
                    f"<td>{RP.COPY[lang]['country'].get(r.country, r.country)}</td>"
                    f"<td class='num'>{_num(r.turbines, lang)}</td><td class='num'>{_num(r.power_mw, lang)}</td>"
                    f"<td>{LEVEL_NAME[lang].get(r.level, r.level)}</td>"
                    f"<td class='num'>{_num(r.wind100_mean, lang, 1)}</td><td class='num'>{_pct(r.power_frac, lang)}</td>"
                    f"<td>{RP.COPY[lang]['cost'].get(r.cost, r.cost)}</td>"
                    f"<td><i class='dot' style='background:{RP.ADVICE_COLOR[r.advice]}'></i>"
                    f"{RP.ADVICE_NAME[lang][r.advice]}</td></tr>")
    return "".join(rows)


def payload(inp: RP.Inputs, wf: pd.DataFrame | None, lang: str) -> tuple[dict, list]:
    c = COPY[lang]
    clim = R.climatology(inp.nights)
    zones = RP.zone_info(inp, RP.in_map(clim), lang)
    lon = [z[2] for z in zones]
    lat = [z[3] for z in zones]
    extent = [min(lon) - 0.8, max(lon) + 0.8, min(lat) - 0.6, max(lat) + 0.6]
    data = {"extent": extent, "land": RP.land(inp.rings), "advice": RP.ADVICE_COLOR, "zones": zones,
            "nights": {}, "text": {"hint": c["hint"], "zone_night": RP.COPY[lang]["zone_night"],
                                   "advice": RP.ADVICE_NAME[lang], "why": RP.COPY[lang]["why"]}}
    nights = []
    if wf is not None:
        for night, g in wf.groupby("night"):
            night = pd.Timestamp(night)
            key = f"{night:%Y-%m-%d}"
            acted = g[g["advice"].isin(["stop", "stop at peak hours"])]
            data["nights"][key] = {"night": _night(night, lang), "zs": RP.zone_nights(g, night, lang),
                                   "cap": c["cap"].format(night=_night(night, lang), stop=len(acted),
                                                          mw=_num(acted["power_mw"].sum(), lang),
                                                          watch=int((g["advice"] == "watch").sum()), n=len(g))}
            nights.append((key, night, g))
    return data, nights, clim


def page(inp: RP.Inputs, lang: str, today: dt.date) -> str:
    c = COPY[lang]
    wf = upcoming(inp, today)
    data, nights, clim = payload(inp, wf, lang)
    ev = RP.evidence(inp, clim)
    depth = PAGE[lang].count("/")
    up = "../" * depth
    first = nights[0][0] if nights else ""
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    z = inp.zones.drop_duplicates("zone")
    countries = ", ".join(RP.COPY[lang]["country"].get(k, k) for k in z["country"].drop_duplicates())
    acted = wf[wf["advice"].isin(["stop", "stop at peak hours"])] if wf is not None else None
    figures = [(_num(len(z), lang), c["fig_zones"]), (_num(z["turbines"].sum(), lang), c["fig_turbines"]),
               (_num(z["power_mw"].sum() / 1000, lang, 1), c["fig_gw"])]
    if acted is not None:
        figures.append((_num(acted["night"].nunique(), lang), c["fig_nights"].format(n=wf["night"].nunique())))

    buttons = "".join(f"<button type='button' data-night='{k}'>{_night(n, lang)}</button>" for k, n, _ in nights)
    tables = "".join(f"<tbody data-night='{k}'{'' if k == first else ' hidden'}>{night_table(g, lang)}</tbody>"
                     for k, _, g in nights)
    head = "".join(f"<th>{h}</th>" for h in c["cols"])
    decision = ("<div class='scroll'><table class='decide'><tr><th></th>"
                + "".join(f"<th>{c['cost_h'][k]}</th>" for k in ("cheap", "moderate", "expensive")) + "</tr>"
                + "".join(f"<tr><th>{LEVEL_NAME[lang][lv]}</th>" + "".join(
                    f"<td><i class='dot' style='background:{RP.ADVICE_COLOR[a]}'></i>{RP.ADVICE_NAME[lang][a]}</td>"
                    for a in row) + "</tr>"
                    for lv, row in (("very high", ("stop", "stop at peak hours", "watch")),
                                    ("high", ("watch",) * 3), ("moderate", ("run",) * 3), ("low", ("run",) * 3)))
                + "</table></div>")
    legend = ("<div class='legend'>" + "".join(
        f"<span><i class='dot' style='background:{RP.ADVICE_COLOR[a]}'></i>{RP.ADVICE_NAME[lang][a]}</span>"
        for a in ADVICE_ORDER) + f"<span>{c['legend_size']}</span></div>")
    num = dict(cell=_num(CELL_DEG, lang, 1), min=MIN_TURBINES, cut_in=_num(CUT_IN, lang), rated=_num(RATED, lang),
               cut_out=_num(CUT_OUT, lang), cheap=_pct(CHEAP, lang), expensive=_pct(EXPENSIVE, lang),
               countries=countries)

    p = [f"<!doctype html><html lang='{lang}'><meta charset='utf-8'>",
         "<meta name='viewport' content='width=device-width,initial-scale=1'>",
         f"<title>{c['title']}</title>", FAVICON,
         f"<meta name='description' content='{c['description']}'>",
         f"<link rel='alternate' hreflang='es' href='{BASE}{PAGE['es']}'>",
         f"<link rel='alternate' hreflang='en' href='{BASE}{PAGE['en']}'>",
         "<link rel='preconnect' href='https://fonts.googleapis.com'>",
         "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>",
         f"<link rel='stylesheet' href='{FONTS}'>",
         f"<style>{COMMON_CSS}{SITE_CSS}{RP.CSS}{site.CSS}{CSS}</style>",
         site.page_bar(lang, "farms", depth),
         "<header class='site-header'>",
         f"<p class='kicker'>{c['kicker']}</p>",
         f"<h1>{c['h1']}</h1>",
         f"<p class='lede'>{c['lede']}</p>",
         "<div class='figures'>" + "".join(f"<div><b>{v}</b><span>{k}</span></div>" for v, k in figures) + "</div>",
         "</header>", "<main class='wrap'>"]
    if nights:
        p += ["<section class='routes farms' aria-labelledby='h-map'>",
              f"<h2 id='h-map'>{c['h_map']}</h2>",
              f"<div class='controls' role='group' aria-label='{c['pick_night']}'>{buttons}</div>",
              "<p class='cap' id='map-cap'></p>",
              "<div class='stage'><div id='map' class='map'><canvas id='map-base'></canvas>"
              f"<canvas id='map-top' aria-label='{c['map_alt']}' role='img'></canvas></div>"
              f"<aside id='map-panel' class='panel' aria-live='polite'><p class='hint'>{c['hint']}</p></aside></div>",
              f"<label class='zone-pick'><span>{c['pick_zone']}</span> <select id='map-zone'><option value=''>—</option>"
              + "".join(f"<option value='{z_[0]}'>{z_[1]} · {_num(z_[4], lang)} MW</option>" for z_ in data["zones"])
              + "</select></label>", legend,
              f"<noscript><p>{c['noscript']}</p></noscript>", "</section>",
              f"<h2 id='tabla'>{c['h_table']}</h2><p class='sub'>{c['sub_table']}</p>",
              "<input type='checkbox' id='show-all' class='show-all'>"
              f"<label for='show-all' class='show-all-l'>{c['show_all']}</label>",
              f"<div class='scroll'><table class='zones'><thead><tr>{head}</tr></thead>{tables}</table></div>",
              f"<p class='sub'>{c['table_note']}</p>",
              f"<h2>{c['h_week']}</h2><p class='sub'>{c['sub_week']}</p>",
              wind_table(wf, lang) if acted is not None and len(acted) else f"<p>{c['no_stop']}</p>"]
    else:
        p.append(f"<p class='empty'>{c['no_forecast']}</p>")

    p += [f"<h2>{c['h_why']}</h2><p class='sub'>{c['sub_why']}</p>", RP._why(ev, lang),
          f"<h2>{c['h_method']}</h2><ol class='steps'>"
          + "".join(f"<li><h3>{t}</h3><p>{b.format(**num)}</p></li>" for t, b in c["method"]) + "</ol>",
          f"<h3 class='decide-h'>{c['h_decide']}</h3>", decision, f"<p class='sub'>{c['decide_note']}</p>",
          f"<h2>{c['h_limits']}</h2><ul>" + "".join(f"<li>{x}</li>" for x in c["limits"]) + "</ul>",
          f"<h2>{c['h_more']}</h2><ul class='more'>"
          + "".join(f"<li><a href='{up}{h}'>{t}</a> — {d}</li>" for h, t, d in c["more"]) + "</ul>",
          f"<h2>{c['h_sources']}</h2><p class='data-note'>{c['sources']}</p>",
          f"<p class='data-note'>{c['code'].format(repo=REPO)}</p>",
          "</main>", site_footer(lang, today),
          f"<script type='application/json' id='farms-data'>{blob}</script>",
          f"<script>var FIRST='{first}';{JS}</script>", "</html>"]
    return "\n".join(p)


def build(inp: RP.Inputs, root: Path, log=print, today: dt.date | None = None) -> list[Path]:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    written = []
    for lang in ("es", "en"):
        dest = root / PAGE[lang]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page(inp, lang, today), encoding="utf-8", newline="\n")
        log(f"{dest} ({dest.stat().st_size / 1000:.0f} kB)")
        written.append(dest)
    return written


CSS = """
.site-header h1{font-size:clamp(36px,5.4vw,56px)}
.farms .controls button{min-width:0}
.farms .stage{grid-template-columns:minmax(0,1fr) 320px}
@media (max-width:860px){.farms .stage{grid-template-columns:1fr}}
.farms .legend{display:flex;flex-wrap:wrap}
.legend i.dot,table i.dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px;vertical-align:-1px;border:1px solid rgba(0,0,0,.25)}
table.zones{width:100%;border-collapse:collapse;font-size:15px}
table.zones th,table.zones td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
table.zones th{font:600 13px/1.2 var(--font-title);text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
table.zones td.num{text-align:right;font-family:var(--font-data);font-variant-numeric:tabular-nums}
table.zones small{display:block;color:var(--muted);font:12px var(--font-data)}
table.zones tr.run{display:none}
.show-all{margin:0 6px 10px 0}
.show-all-l{font:600 14px var(--font-title);text-transform:uppercase;letter-spacing:.06em;cursor:pointer}
.show-all:checked~.scroll tr.run{display:table-row}
table.decide{border-collapse:collapse;font-size:15px;margin:6px 0}
table.decide th,table.decide td{padding:7px 12px;border:1px solid var(--line);text-align:left}
table.decide th{font:600 14px var(--font-title);text-transform:uppercase;letter-spacing:.05em}
.decide-h{margin-top:22px}
ul.more li{margin:0 0 6px}
.empty{font-size:18px}
"""

# Still map: land once, zones on top; a click or the list opens the zone sheet with the night picked.
JS = r"""
(function(){
var D=JSON.parse(document.getElementById('farms-data').textContent),E=D.extent,T=D.text;
var wrap=document.getElementById('map');if(!wrap)return;
var cb=document.getElementById('map-base'),ct=document.getElementById('map-top'),panel=document.getElementById('map-panel'),
cap=document.getElementById('map-cap'),zoneSel=document.getElementById('map-zone');
var W=0,H=0,S=1,OX=0,KX=Math.cos((E[2]+E[3])/360*Math.PI),N=null,key=FIRST,sel=null,ZB={};
D.zones.forEach(function(z){ZB[z[0]]=z});
function px(lon){return OX+(lon-E[0])*KX*S}
function py(lat){return (E[3]-lat)*S}
function landPath(c){c.beginPath();D.land.forEach(function(r){c.moveTo(px(r[0]/100),py(r[1]/100));
for(var k=2;k<r.length;k+=2)c.lineTo(px(r[k]/100),py(r[k+1]/100));c.closePath()})}
function drawBase(){var c=cb.getContext('2d');c.fillStyle='#0a1322';c.fillRect(0,0,W,H);landPath(c);
c.fillStyle='#1a2b45';c.fill();c.strokeStyle='rgba(176,196,228,.6)';c.lineWidth=.9;c.stroke()}
function zr(z){return (3+Math.sqrt(z[4])/2.6)*Math.min(1,.55+W/1400)}
var RANK={'run':0,'watch':1,'stop at peak hours':2,'stop':3};
function adv(z){var s=N&&N.zs[z[0]];return s?s[0]:null}
function drawTop(){var c=ct.getContext('2d');c.clearRect(0,0,W,H);
var zs=D.zones.filter(adv).sort(function(a,b){return RANK[adv(a)]-RANK[adv(b)]||b[4]-a[4]});
zs.forEach(function(z){var x=px(z[2]),y=py(z[3]),r=zr(z);c.beginPath();c.arc(x,y,r,0,7);var a=adv(z);c.globalAlpha=a==='run'?.42:.95;
c.fillStyle=D.advice[a];c.fill();c.globalAlpha=1;c.lineWidth=1;c.strokeStyle='#0a1322';c.stroke();
if(sel===z[0]){c.beginPath();c.arc(x,y,r+4,0,7);c.strokeStyle='#fff';c.lineWidth=2;c.stroke()}})}
function fill(t,o){return t.replace(/\{(\w+)\}/g,function(m,k){return o[k]==null?m:o[k]})}
function show(){if(!sel){panel.innerHTML='<p class="hint">'+T.hint+'</p>';zoneSel.value='';return}
var z=ZB[sel],s=N&&N.zs[sel],night='';if(s)night='<div class="tonight" style="--c:'+D.advice[s[0]]+'">'+
fill(T.zone_night,{night:N.night,level:s[1],rel:s[2],wind:s[3],frac:s[4],cost:s[5],advice:T.advice[s[0]],
why:T.why[s[0]]})+'</div>';panel.innerHTML=z[7].replace('@@N@@',night);zoneSel.value=sel}
function setNight(k){if(!D.nights[k])return;key=k;N=D.nights[k];cap.innerHTML=N.cap;
document.querySelectorAll('.controls [data-night]').forEach(function(b){b.setAttribute('aria-pressed',String(b.getAttribute('data-night')===k))});
document.querySelectorAll('tbody[data-night]').forEach(function(t){t.hidden=t.getAttribute('data-night')!==k});
drawTop();show()}
function resize(){var dpr=Math.min(window.devicePixelRatio||1,2);W=wrap.clientWidth;
var maxH=Math.max(360,Math.min(window.innerHeight*.8,900)),dx=(E[1]-E[0])*KX,dy=E[3]-E[2];
S=Math.min(W/dx,maxH/dy);H=Math.round(dy*S);OX=(W-dx*S)/2;wrap.style.height=H+'px';
[cb,ct].forEach(function(c){c.width=Math.round(W*dpr);c.height=Math.round(H*dpr);c.style.width=W+'px';
c.style.height=H+'px';c.getContext('2d').setTransform(dpr,0,0,dpr,0,0)});drawBase();drawTop()}
document.querySelectorAll('.controls [data-night]').forEach(function(b){b.addEventListener('click',function(){setNight(b.getAttribute('data-night'))})});
zoneSel.addEventListener('change',function(){sel=zoneSel.value||null;show();drawTop()});
ct.addEventListener('click',function(ev){var b=ct.getBoundingClientRect(),x=ev.clientX-b.left,y=ev.clientY-b.top,best=null,bd=9;
D.zones.forEach(function(z){if(!adv(z))return;var d=Math.hypot(px(z[2])-x,py(z[3])-y)-zr(z);if(d<bd){bd=d;best=z[0]}});
sel=best;show();drawTop()});
var t=0;window.addEventListener('resize',function(){clearTimeout(t);t=setTimeout(resize,120)});
resize();setNight(key);
})();
"""

COPY: dict[str, dict] = {
    "es": {
        "title": "Sub Nocte · parques eólicos y migración nocturna",
        "description": "Qué parques eólicos de la península y Francia tienen paso fuerte de aves las próximas noches, "
                       "cuánto costaría pararlos y la sugerencia que sale de cruzar las dos cosas.",
        "kicker": "Sub Nocte · parques eólicos",
        "h1": "¿Qué parques deberían parar esta noche?",
        "lede": "Para cada zona eólica, la previsión de migración nocturna de las próximas noches y lo que costaría "
                "parar con el viento previsto. La sugerencia es <b>parar</b> solo cuando hay mucho paso y poco "
                "viento; en el resto, vigilar o seguir.",
        "fig_zones": "zonas eólicas en España, Portugal y Francia", "fig_turbines": "aerogeneradores", "fig_gw": "GW instalados",
        "fig_nights": "de {n} noches con alguna parada sugerida",
        "h_map": "Mapa por noche",
        "pick_night": "Elige la noche",
        "cap": "<b>{night}.</b> {stop} de {n} zonas con parada sugerida ({mw} MW), {watch} para vigilar. El color es "
               "la sugerencia; el tamaño, la potencia.",
        "map_alt": "Mapa de las zonas eólicas coloreadas según la sugerencia de la noche elegida",
        "hint": "Pulsa un círculo, o elige una zona en la lista, para ver por qué la sugerencia es esa.",
        "pick_zone": "Ir a una zona",
        "legend_size": "tamaño: potencia instalada",
        "noscript": "El mapa necesita JavaScript; la tabla de abajo tiene los mismos datos.",
        "h_table": "Zona por zona",
        "sub_table": "La noche elegida arriba. Primero las zonas con parada sugerida y, dentro de cada grupo, las de "
                     "más potencia.",
        "show_all": "Mostrar también las zonas sin nada que hacer («seguir»)",
        "cols": ["zona", "país", "aerog.", "MW", "paso", "viento 100 m (m/s)", "producción", "parar es",
                 "sugerencia"],
        "table_note": "Paso: el nivel de la noche frente al propio registro de la zona en la misma fecha. "
                      "Producción: la parte de su potencia que darían los aerogeneradores con el viento previsto "
                      "durante las horas de noche.",
        "h_week": "La semana de un vistazo",
        "sub_week": "Por noche, cuántas zonas llegan a muy alto y dónde se sugiere parar.",
        "no_stop": "Ninguna zona cumple la regla de parada en estas noches.",
        "no_forecast": "Ahora mismo no hay previsión para los parques: fuera de las temporadas de paso (marzo-mayo "
                       "y agosto-noviembre) no hay umbral con el que medir una noche.",
        "h_why": "Por qué parar, y solo unas noches",
        "sub_why": "Cifras calculadas con los mismos datos que alimentan esta página.",
        "h_method": "Cómo se calcula",
        "method": [
            ("Zonas eólicas",
             "Los aerogeneradores que hay en OpenStreetMap se agrupan en celdas de {cell}° (unos 55 × 42 km en la "
             "península). Una celda con {min} aerogeneradores o más es una zona, y su punto de previsión es el "
             "centro de sus aerogeneradores. Países: {countries}."),
            ("Cuánto paso se espera",
             "El mismo modelo que da la previsión por ciudad: aprende de las noches de radar de 2021 a 2026 cómo la meteorología "
             "de cada noche (viento, temperatura, presión, lluvia) mueve la migración, y se aplica en el punto de "
             "la zona con la previsión de Open-Meteo. El nivel no es absoluto: se compara con el registro de la "
             "propia zona en la misma época (ERA5, la reconstrucción del tiempo pasado de Copernicus, 2021-2026). "
             "<b>Alto</b> es por encima de su percentil 75 (lo que solo supera una noche de cada cuatro) y "
             "<b>muy alto</b>, de su percentil 90 (una de cada diez)."),
            ("Cuánto cuesta parar",
             "El viento previsto a 100 m en las horas de noche pasa por una curva de potencia genérica: nada por "
             "debajo de {cut_in} m/s, potencia nominal desde {rated} m/s y parada de seguridad a {cut_out} m/s. "
             "Sale la parte de su potencia que produciría la zona. Por debajo del {cheap}, parar es <b>barato</b>; "
             "desde el {expensive}, <b>caro</b>."),
            ("La sugerencia",
             "Las dos mitades se cruzan en la tabla fija de abajo. Es una forma de ordenar las noches, no una "
             "orden de parada: quien decide es cada parque y su plan de vigilancia."),
        ],
        "h_decide": "La tabla de decisión",
        "cost_h": {"cheap": "parar es barato", "moderate": "moderado", "expensive": "caro"},
        "decide_note": "«Parar en horas punta»: con viento, parar toda la noche ya cuesta; basta con las horas de "
                       "más paso, que suelen ser las primeras de la noche.",
        "h_limits": "Qué no dice esta página",
        "limits": [
            "<b>No mide a la altura del rotor.</b> El radar ve de unos 200 m a 3 km; las palas barren de 30 a 200 m "
            "sobre el suelo. En las sierras, con los parques a 800-1.500 m, las dos bandas se acercan, pero no hay "
            "dato de altura por zona.",
            "<b>No distingue especies.</b> Es migración nocturna, sobre todo de paseriformes. La mortalidad "
            "documentada en los parques españoles es sobre todo de rapaces y planeadoras diurnas y de murciélagos: "
            "eso no está aquí.",
            "<b>Curva genérica e inventario de OpenStreetMap.</b> La producción sale de una curva de potencia "
            "genérica, no de las máquinas reales; la potencia y el rotor solo están etiquetados en parte de los "
            "aerogeneradores, y faltan los que nadie ha cartografiado.",
            "<b>El radar más cercano está lejos.</b> A decenas de kilómetros, y los radares renovados de AEMET "
            "aciertan menos que los demás (AUC 0,55-0,66 frente a 0,74 en el conjunto de España; el AUC, área "
            "bajo la curva ROC, mide si el modelo pone las noches fuertes por delante de las flojas: 0,5 es "
            "azar y 1, perfecto).",
            "<b>Solo en temporada.</b> Fuera de marzo-mayo y agosto-noviembre no hay umbral y no hay sugerencia.",
            "<b>No es una orden.</b> Es una sugerencia para ordenar las noches, no sustituye los planes de "
            "vigilancia de cada parque ni ninguna decisión de la administración.",
        ],
        "h_more": "Para ir más a fondo",
        "more": [
            ("rutas.html", "Mapa de rutas", "por dónde pasa la migración sobre cada parque, según los radares."),
            ("output/wind.html", "Informe técnico de parques eólicos",
             "la previsión completa con sus figuras y tablas (en inglés)."),
            ("output/wind_check.html", "Verificación de la regla",
             "qué habría hecho desde 2021 y si el radar le daba la razón (en inglés)."),
            ("metodo.html", "Método", "todos los informes técnicos, explicados."),
        ],
        "h_sources": "Fuentes",
        "sources": "Aerogeneradores: © colaboradores de <a href='https://www.openstreetmap.org/copyright'>"
                   "OpenStreetMap</a> (ODbL). Previsión meteorológica: <a href='https://open-meteo.com'>Open-Meteo"
                   "</a> (CC BY 4.0). Registro de cada zona: reanálisis ERA5 de Copernicus. Radar: perfiles "
                   "vol2bird (el programa que separa los ecos de aves de los de lluvia e insectos) de "
                   "<a href='https://aloftdata.eu'>Aloft</a> (CC0), el archivo abierto europeo de perfiles de aves, "
                   "sobre los radares de AEMET, IPMA y Météo-France de la red europea OPERA. Costas y fronteras: <a href='https://www.naturalearthdata.com'>Natural Earth</a>.",
        "code": "El código y los datos de cada noche (<code>data/wind/forecast.csv</code>) están en el "
                "<a href='{repo}'>repositorio</a>.",
    },
    "en": {
        "title": "Sub Nocte · wind farms and nocturnal migration",
        "description": "Which wind farms in Iberia and France face heavy bird passage over the coming nights, what "
                       "stopping them would cost, and the suggestion that comes from crossing the two.",
        "kicker": "Sub Nocte · wind farms",
        "h1": "Which wind farms should stop tonight?",
        "lede": "For each wind zone, the nocturnal migration forecast for the coming nights and what stopping would "
                "cost with the wind forecast. The suggestion is to <b>stop</b> only when passage is heavy and wind "
                "is light; otherwise, watch or keep running.",
        "fig_zones": "wind zones in Spain, Portugal and France", "fig_turbines": "turbines", "fig_gw": "GW installed",
        "fig_nights": "of {n} nights with a suggested stop",
        "h_map": "Map by night",
        "pick_night": "Pick the night",
        "cap": "<b>{night}.</b> {stop} of {n} zones with a suggested stop ({mw} MW), {watch} to watch. Colour is the "
               "suggestion; size, the capacity.",
        "map_alt": "Map of the wind zones coloured by the suggestion for the night picked",
        "hint": "Tap a circle, or pick a zone from the list, to see why the suggestion is what it is.",
        "pick_zone": "Go to a zone",
        "legend_size": "size: installed capacity",
        "noscript": "The map needs JavaScript; the table below has the same data.",
        "h_table": "Zone by zone",
        "sub_table": "The night picked above. Zones with a suggested stop first and, within each group, the largest "
                     "capacity first.",
        "show_all": "Also show the zones with nothing to do («run»)",
        "cols": ["zone", "country", "turb.", "MW", "passage", "wind 100 m (m/s)", "output", "stopping is",
                 "suggestion"],
        "table_note": "Passage: the night's level against the zone's own record at the same date. Output: the share "
                      "of capacity the turbines would deliver with the forecast wind over the night hours.",
        "h_week": "The week at a glance",
        "sub_week": "Per night, how many zones reach very high and where stopping is suggested.",
        "no_stop": "No zone meets the stopping rule on these nights.",
        "no_forecast": "There is no wind farm forecast right now: outside the passage seasons (March-May and "
                       "August-November) there is no threshold to measure a night against.",
        "h_why": "Why stop, and only on a few nights",
        "sub_why": "Figures computed from the same data that feed this page.",
        "h_method": "How it is computed",
        "method": [
            ("Wind zones",
             "The turbines mapped in OpenStreetMap are grouped into cells of {cell}° (about 55 × 42 km in Iberia). "
             "A cell with {min} turbines or more is a zone, and its forecast point is the centre of its turbines. "
             "Countries: {countries}."),
            ("How much passage is expected",
             "The same model as the per-city forecast: it learns from the radar nights of 2021 to 2026 how each night's weather "
             "(wind, temperature, pressure, rain) moves migration, and is applied at the zone's point with the "
             "Open-Meteo forecast. The level is not absolute: it is set against the zone's own record at the same "
             "time of year (ERA5, Copernicus's reconstruction of past weather, 2021-2026). <b>High</b> is above its "
             "75th percentile (what only one night in four exceeds) and <b>very high</b> above its 90th (one in "
             "ten)."),
            ("What stopping costs",
             "The wind forecast at 100 m over the night hours goes through a generic power curve: nothing below "
             "{cut_in} m/s, rated power from {rated} m/s and safety cut-out at {cut_out} m/s. Out comes the share "
             "of capacity the zone would produce. Below {cheap}, stopping is <b>cheap</b>; from {expensive}, "
             "<b>expensive</b>."),
            ("The suggestion",
             "The two halves cross in the fixed table below. It is a way of ranking nights, not a stop order: each "
             "farm and its monitoring plan decide."),
        ],
        "h_decide": "The decision table",
        "cost_h": {"cheap": "stopping is cheap", "moderate": "moderate", "expensive": "expensive"},
        "decide_note": "«Stop at peak hours»: with wind, stopping all night already costs; the hours of heaviest "
                       "passage are enough, usually the first of the night.",
        "h_limits": "What this page does not say",
        "limits": [
            "<b>Not at rotor height.</b> The radar sees from about 200 m to 3 km; the blades sweep 30 to 200 m above "
            "the ground. On ridges, with farms at 800-1,500 m, the two bands come closer, but there is no height "
            "per zone.",
            "<b>No species.</b> This is nocturnal migration, mostly passerines. The documented mortality at Spanish "
            "wind farms is mostly diurnal raptors and soaring birds, and bats: that is not here.",
            "<b>Generic curve, OpenStreetMap inventory.</b> Output comes from a generic power curve, not the real "
            "machines; capacity and rotor are tagged on only part of the turbines, and the unmapped ones are "
            "missing.",
            "<b>The nearest radar is far.</b> Tens of kilometres away, and the renewed AEMET radars do worse than "
            "the rest (AUC 0.55-0.66 against 0.74 for Spain as a whole; the AUC, area under the ROC curve, measures "
            "whether the model ranks heavy nights ahead of light ones: 0.5 is chance and 1 is perfect).",
            "<b>In season only.</b> Outside March-May and August-November there is no threshold and no suggestion.",
            "<b>Not an order.</b> It is a suggestion to rank nights; it does not replace each farm's monitoring "
            "plan nor any decision by the authorities.",
        ],
        "h_more": "To go further",
        "more": [
            ("en/routes.html", "Routes map", "where migration crosses each farm, as the radars see it."),
            ("output/wind.html", "Wind farm technical report", "the full forecast with its figures and tables."),
            ("output/wind_check.html", "Checking the rule",
             "what it would have done since 2021 and whether the radar agreed."),
            ("en/method.html", "Method", "every technical report, explained."),
        ],
        "h_sources": "Sources",
        "sources": "Turbines: © <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors "
                   "(ODbL). Weather forecast: <a href='https://open-meteo.com'>Open-Meteo</a> (CC BY 4.0). Each "
                   "zone's record: Copernicus ERA5 reanalysis. Radar: vol2bird profiles from "
                   "<a href='https://aloftdata.eu'>Aloft</a> (CC0), the open European archive of bird profiles (vol2bird "
                   "is the program that sorts bird echoes from rain and insects), over the AEMET, IPMA and "
                   "Météo-France radars of the European OPERA network. "
                   "Coasts and borders: <a href='https://www.naturalearthdata.com'>Natural Earth</a>.",
        "code": "The code and each night's data (<code>data/wind/forecast.csv</code>) are in the "
                "<a href='{repo}'>repository</a>.",
    },
}
