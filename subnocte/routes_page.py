"""The routes page: where the nocturnal migration flies, season by season and over the coming nights, and why
the wind farms in its way should stop on a few of them.

One self-contained page per language (`rutas.html`, `en/routes.html`). The data travel inline as one JSON block
and a short script draws them on canvas: no tile server, no map library, nothing fetched at view time but the
fonts. Every number the prose quotes is computed here from the versioned data files, not typed in.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import routes as R
from . import site
from .logo import LOGO_SVG
from .web import (BASE, COMMON_CSS, CSS as SITE_CSS, FAVICON, FONTS, LEVEL_NAME, MONTHS, REPO, SEASON_NAME,
                  _date, _night, _num, site_footer)

ADVICE_COLOR = {"run": "#8a94a6", "watch": "#ffd98e", "stop at peak hours": "#f08c1e", "stop": "#e0452f"}
ADVICE_NAME = {"es": {"run": "seguir", "watch": "vigilar", "stop at peak hours": "parar en horas punta",
                      "stop": "parar"},
               "en": {a: a for a in ADVICE_COLOR}}
LOG_RANGE = (-0.3, 1.8)    # log10 of birds/km² at the two ends of the colour ramp (0.5 to 63)
PAGE = {"es": "rutas.html", "en": "en/routes.html"}


@dataclass
class Inputs:
    nights: pd.DataFrame                       # data/routes/flight_nights.parquet
    zones: pd.DataFrame                        # wind zones of every region with thresholds
    zone_thresholds: pd.DataFrame
    wind_forecast: pd.DataFrame | None = None
    check_by_zone: pd.DataFrame | None = None
    check_radar: pd.DataFrame | None = None
    check_hindcast: pd.DataFrame | None = None
    city_forecast: pd.DataFrame | None = None
    city_thresholds: pd.DataFrame | None = None
    cities: pd.DataFrame | None = None
    rings: list = field(default_factory=list)  # country outlines, lon/lat arrays


def _read(f: Path, **kw) -> pd.DataFrame | None:
    return pd.read_csv(f, **kw) if f.exists() else None


def load(root: Path) -> Inputs:
    """Everything the page needs, from the files the other commands leave in `data/`."""
    from .flows import borders

    wind = root / "data" / "wind"
    regions = [d for d in (wind, wind / "france") if (d / "thresholds.csv").exists() and (d / "zones.csv").exists()]

    def cat(name: str, **kw) -> pd.DataFrame | None:
        parts = [x for d in regions if (x := _read(d / name, **kw)) is not None]
        return pd.concat(parts, ignore_index=True) if parts else None

    return Inputs(
        nights=pd.read_parquet(root / "data" / "routes" / "flight_nights.parquet"),
        zones=cat("zones.csv"), zone_thresholds=cat("thresholds.csv"),
        wind_forecast=cat("forecast.csv", parse_dates=["night"]), check_by_zone=cat("check_by_zone.csv"),
        check_radar=_read(wind / "check_radar.csv"), check_hindcast=_read(wind / "check_hindcast.csv"),
        city_forecast=_read(root / "data" / "phase3_forecast.csv", parse_dates=["night"]),
        city_thresholds=_read(root / "data" / "phase3_thresholds.csv"),
        cities=_read(root / "data" / "cities.csv"),
        rings=borders(root / "data" / "cache" / "ne"),
    )


# ---------------------------------------------------------------- the pieces of the payload

def in_map(df: pd.DataFrame, pad: float = 1.0) -> pd.DataFrame:
    e = R.EXTENT
    return df[df["lon"].between(e[0] - pad, e[1] + pad) & df["lat"].between(e[2] - pad, e[3] + pad)]


def land(rings: list, tol: float = 0.04) -> list[list[int]]:
    """Country outlines thinned to one point every `tol` degrees and packed as flat lists of lon,lat × 100."""
    e, out = R.EXTENT, []
    for r in rings:
        if not ((r[:, 0] > e[0] - 2) & (r[:, 0] < e[1] + 2) & (r[:, 1] > e[2] - 2) & (r[:, 1] < e[3] + 2)).any():
            continue
        keep = [r[0]]
        for p in r[1:]:
            if abs(p[0] - keep[-1][0]) + abs(p[1] - keep[-1][1]) >= tol:
                keep.append(p)
        if len(keep) >= 4:
            out.append([int(round(c * 100)) for p in keep for c in p])
    return out


def _q(a: np.ndarray, k: float = 100) -> list[int]:
    return [int(x) for x in np.round(np.nan_to_num(a) * k).ravel()]


def fields(st: pd.DataFrame, pts: pd.DataFrame) -> dict:
    """Direction (u, v, how much of it to draw) and intensity (log10 birds/km², how much of it) on the grid."""
    lon, lat = R.grid()
    u, v, a = R.direction_field(st, lon, lat)
    z, ia = R.intensity_field(pts, lon, lat)
    return {"u": _q(u), "v": _q(v), "a": _q(a), "i": _q(np.log10(np.maximum(z, 1e-3))), "ia": _q(ia)}


def _points(lonlat: pd.DataFrame, vid: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"lon": lonlat["lon"].to_numpy(), "lat": lonlat["lat"].to_numpy(),
                         "vid": vid.to_numpy()}).dropna()


def season_points(inp: Inputs, season: str) -> pd.DataFrame:
    """Mean expected birds/km² over the season at every wind zone and city (the model's hindcast)."""
    parts = []
    for th, places, key in ((inp.zone_thresholds, inp.zones, "zone"), (inp.city_thresholds, inp.cities, "city")):
        if th is None or places is None:
            continue
        ex = R.season_exposure(th, key=key)
        ex = ex[ex["season"] == season].merge(places[[key, "lat", "lon"]], on=key)
        parts.append(_points(ex, ex["vid"]))
    return in_map(pd.concat(parts, ignore_index=True)) if parts else pd.DataFrame(columns=["lon", "lat", "vid"])


def night_points(inp: Inputs, night: pd.Timestamp) -> pd.DataFrame:
    """Expected birds/km² on one forecast night at every wind zone and city."""
    parts = []
    for fc in (inp.wind_forecast, inp.city_forecast):
        if fc is None:
            continue
        g = fc[pd.to_datetime(fc["night"]) == night]
        parts.append(_points(g, g["pred"].clip(lower=0) ** 3))
    return in_map(pd.concat(parts, ignore_index=True)) if parts else pd.DataFrame(columns=["lon", "lat", "vid"])


def steadiness_word(r: float, lang: str) -> str:
    words = {"es": ["sin dirección clara", "variable", "constante", "muy constante"],
             "en": ["no clear direction", "variable", "steady", "very steady"]}[lang]
    return words[0 if r < 0.4 else 1 if r < 0.6 else 2 if r < 0.8 else 3]


def _pct(x: float, lang: str, nd: int = 0) -> str:
    s = _num(100 * x, lang, nd)
    return f"{s} %" if lang == "es" else f"{s}%"


def station_rows(st: pd.DataFrame, when: str, lang: str) -> list[list]:
    c = COPY[lang]
    rows = []
    for r in st.itertuples():
        # the panel sentence is filled in by the page from `station_html`: only the values travel
        f = {"when": when, "dir": R.compass(r.heading, lang), "heading": _num(r.heading, lang),
             "word": steadiness_word(r.steadiness, lang), "r": _num(r.steadiness, lang, 2),
             "nights": _num(r.nights, lang), "years": r.years, "speed": _num(r.speed, lang, 1),
             "alt": _num(r.alt, lang), "top": _pct(r.top_share, lang), "p90": _num(r.p90, lang),
             "radars": r.radars}
        rows.append([r.station, round(r.lon, 3), round(r.lat, 3), round(r.heading, 1), round(r.steadiness, 2), f])
    return rows


def zone_info(inp: Inputs, clim: pd.DataFrame, lang: str) -> list[list]:
    """Per wind zone: what does not change from night to night, written out for the side panel."""
    c = COPY[lang]
    z = inp.zones.drop_duplicates("zone").copy()
    ex = R.season_exposure(inp.zone_thresholds, key="zone")
    ex["rank"] = ex.groupby("season")["vid"].rank(ascending=False, method="min").astype(int)
    total = ex.groupby("season")["zone"].nunique()
    bz = (inp.check_by_zone.set_index("zone") if inp.check_by_zone is not None
          else pd.DataFrame(columns=["radar", "dist_km", "nights", "rho", "very_high_busy"]))
    chance = _chance(inp)
    out = []
    for r in z.itertuples():
        parts = [c["zone_head"].format(place=r.place if isinstance(r.place, str) else r.zone, zone=r.zone,
                                       country=c["country"].get(r.country, r.country),
                                       turbines=_num(r.turbines, lang), mw=_num(r.power_mw, lang))]
        exp = {}
        for season in ("autumn", "spring"):
            st = clim[clim["season"] == season]
            h, s = R.at(r.lon, r.lat, st)
            e = ex[(ex["zone"] == r.zone) & (ex["season"] == season)]
            if np.isnan(h):
                route = c["zone_no_route"].format(season=SEASON_NAME[lang][season])
            else:
                d = R._dist_km(np.array([r.lon]), np.array([r.lat]), st["lon"].to_numpy(), st["lat"].to_numpy())[0]
                near = st.iloc[int(np.argmin(d))]
                route = c["zone_route"].format(season=SEASON_NAME[lang][season], dir=R.compass(h, lang),
                                               word=steadiness_word(s, lang), r=_num(s, lang, 2),
                                               station=near["station"], km=_num(d.min(), lang))
            if len(e):
                rank, n = int(e["rank"].iat[0]), int(total[season])
                exp[season] = float(e["pct"].iat[0])
                route += " " + c["zone_rank"].format(rank=rank, n=n)
            parts.append(f"<p>{route}</p>")
        if r.zone in bz.index:
            b = bz.loc[r.zone]
            b = b.iloc[0] if isinstance(b, pd.DataFrame) else b
            from .flows import radar_name
            vhb = (c["zone_check_vh"].format(busy=_pct(b["very_high_busy"], lang), chance=_pct(chance, lang))
                   if pd.notna(b["very_high_busy"]) else "")
            parts.append("<p>" + c["zone_check"].format(radar=radar_name(b["radar"], lang),
                                                        km=_num(b["dist_km"], lang), nights=_num(b["nights"], lang),
                                                        rho=_num(b["rho"], lang, 2)) + vhb + "</p>")
        else:
            parts.append(f"<p>{c['zone_no_check']}</p>")
        name = r.place if isinstance(r.place, str) else r.zone
        out.append([r.zone, name, round(r.lon, 3), round(r.lat, 3), round(float(r.power_mw), 1),
                    round(exp.get("autumn", np.nan), 2) if "autumn" in exp else None,
                    round(exp.get("spring", np.nan), 2) if "spring" in exp else None, "".join(parts)])
    return sorted(out, key=lambda x: (x[1], -x[4]))


def zone_nights(g: pd.DataFrame, night: pd.Timestamp, lang: str) -> dict:
    """Per wind zone on one forecast night: its advice and the values of the sentence that says why."""
    c = COPY[lang]
    out = {}
    for r in g.itertuples():
        level = LEVEL_NAME[lang].get(r.level, r.level)
        rel = (c["above"].format(p=int(round(100 * r.percentile))) if pd.notna(r.percentile) and r.percentile >= 0.5
               else c["below"])
        out[r.zone] = [r.advice, level, rel, _num(r.wind100_mean, lang, 1), _pct(r.power_frac, lang),
                       c["cost"].get(r.cost, r.cost)]
    return out


def _chance(inp: Inputs) -> float:
    cr = inp.check_radar
    if cr is None:
        return np.nan
    return float(cr.loc[cr["group"] == "all nights", "busy"].iat[0])


def evidence(inp: Inputs, clim: pd.DataFrame) -> dict:
    """The figures of the «why stop» section, computed from the data rather than typed in."""
    st = in_map(clim)
    out = {"top_share": float(st["top_share"].median()),
           "autumn_steady": int(((st["season"] == "autumn") & (st["steadiness"] >= 0.7)).sum()),
           "autumn_n": int((st["season"] == "autumn").sum()),
           "stations": int(st["station"].nunique()),
           "nights": int(R.usable(inp.nights)["night"].count())}
    sw = st[(st["season"] == "autumn") & st["heading"].between(180, 247.5)]
    out["autumn_sw"] = len(sw)
    if inp.check_hindcast is not None:
        from .wind_check import overall
        ov = overall(inp.check_hindcast).set_index("rule")
        out.update(stop_nights=float(ov.loc["stop", "nights_per_zone"]),
                   stop_lost=float(ov.loc["stop", "output_lost"]),
                   stop_covered=float(ov.loc["stop", "migration_covered"]),
                   all_lost=float(ov.loc["every very high night", "output_lost"]),
                   zones=int(inp.check_hindcast["zones"].max()))
    if inp.check_radar is not None:
        cr = inp.check_radar.set_index("group")
        out.update(chance=float(cr.loc["all nights", "busy"]), stop_busy=float(cr.loc["advice stop", "busy"]),
                   lift=float(cr.loc["advice stop", "lift"]))
    return out


def payload(inp: Inputs, lang: str, today: dt.date) -> tuple[dict, pd.DataFrame, list]:
    """The JSON the page script draws from, the season climatology, and the forecast nights shown."""
    c = COPY[lang]
    clim = R.climatology(inp.nights)
    st_map = in_map(clim)
    g = R.grid()
    data = {"grid": {"lon0": float(g[0][0, 0]), "lat0": float(g[1][0, 0]), "step": R.GRID,
                     "nx": int(g[0].shape[1]), "ny": int(g[0].shape[0])},
            "extent": list(R.EXTENT), "log": list(LOG_RANGE), "land": land(inp.rings),
            "advice": ADVICE_COLOR, "modes": {}, "zones": zone_info(inp, st_map, lang),
            "text": {**{k: c[k] for k in ("hint", "pause", "play", "station_html", "zone_night")},
                     "advice": ADVICE_NAME[lang], "why": c["why"]}}
    for season in ("autumn", "spring"):
        st = st_map[st_map["season"] == season]
        m = fields(st, season_points(inp, season))
        m.update(kind="history", season=season, st=station_rows(st, c["in_season"].format(
                     season=SEASON_NAME[lang][season]), lang),
                 cap=c["cap_history"].format(season=SEASON_NAME[lang][season], n=len(st),
                                             nights=_num(st["nights"].sum(), lang)))
        data["modes"][season] = m
    nights = []
    wf = None if inp.wind_forecast is None else inp.wind_forecast[
        (pd.to_datetime(inp.wind_forecast["night"]).dt.date >= today) & inp.wind_forecast["level"].notna()]
    wf = None if wf is None else wf[pd.to_datetime(wf["night"]).dt.month.map(R.season_of).notna()]
    if wf is not None and len(wf):
        # The usual direction changes little over one week: one window around the middle night serves them all
        days = sorted(wf["night"].unique())
        w = in_map(R.window(inp.nights, pd.Timestamp(days[len(days) // 2]).date()))
        lon, lat = R.grid()
        u, v, a = R.direction_field(w, lon, lat)
        data["fdir"] = {"u": _q(u), "v": _q(v), "a": _q(a), "st": station_rows(w, c["around"], lang)}
        for night, g_ in wf.groupby("night"):
            night = pd.Timestamp(night)
            z, ia = R.intensity_field(night_points(inp, night), lon, lat)
            m = {"i": _q(np.log10(np.maximum(z, 1e-3))), "ia": _q(ia)}
            n_stop = int(g_["advice"].isin(["stop", "stop at peak hours"]).sum())
            m.update(kind="forecast", season=R.season_of(night.month), night=_night(night, lang),
                     zs=zone_nights(g_, night, lang),
                     cap=c["cap_forecast"].format(night=_night(night, lang), stop=n_stop,
                                                  mw=_num(g_.loc[g_["advice"].isin(["stop", "stop at peak hours"]),
                                                                 "power_mw"].sum(), lang),
                                                  window=R.WINDOW_DAYS))
            key = f"{night:%Y-%m-%d}"
            data["modes"][key] = m
            nights.append((key, night))
    return data, clim, nights


# ---------------------------------------------------------------- the page

def _figures(ev: dict, lang: str) -> str:
    c = COPY[lang]
    items = [(_num(ev["nights"], lang), c["fig_nights"]), (_num(ev["stations"], lang), c["fig_stations"]),
             (_pct(ev["top_share"], lang), c["fig_top"])]
    if "lift" in ev:
        items.append((f"×{_num(ev['lift'], lang, 1)}", c["fig_lift"]))
    return "<div class='figures'>" + "".join(f"<div><b>{v}</b><span>{k}</span></div>" for v, k in items) + "</div>"


def _why(ev: dict, lang: str) -> str:
    c = COPY[lang]
    cards = [(c["why_front_h"], c["why_front"].format(sw=ev["autumn_sw"], n=ev["autumn_n"],
                                                       steady=ev["autumn_steady"])),
             (c["why_few_h"], c["why_few"].format(top=_pct(ev["top_share"], lang)))]
    if "stop_nights" in ev:
        cards.append((c["why_cheap_h"], c["why_cheap"].format(
            nights=_num(ev["stop_nights"], lang, 1), lost=_pct(ev["stop_lost"], lang, 1),
            covered=_pct(ev["stop_covered"], lang, 1), all=_pct(ev["all_lost"], lang, 1), zones=ev["zones"])))
    if "lift" in ev:
        cards.append((c["why_right_h"], c["why_right"].format(busy=_pct(ev["stop_busy"], lang),
                                                               chance=_pct(ev["chance"], lang),
                                                               lift=_num(ev["lift"], lang, 1))))
    return "<div class='cards'>" + "".join(f"<div><b>{t}</b><p>{d}</p></div>" for t, d in cards) + "</div>"


def _table(clim: pd.DataFrame, lang: str) -> str:
    c = COPY[lang]
    rows = []
    for r in in_map(clim).sort_values(["season", "station"]).itertuples():
        rows.append(f"<tr><td>{r.station}</td><td>{SEASON_NAME[lang][r.season]}</td><td>{r.years}</td>"
                    f"<td>{_num(r.nights, lang)}</td><td>{R.compass(r.heading, lang)} · {_num(r.heading, lang)}°</td>"
                    f"<td>{_num(r.steadiness, lang, 2)}</td><td>{_num(r.speed, lang, 1)}</td>"
                    f"<td>{_num(r.alt, lang)}</td><td>{_pct(r.top_share, lang)}</td></tr>")
    head = "".join(f"<th>{h}</th>" for h in c["table_cols"])
    return (f"<details><summary>{c['table_summary']}</summary><div class='scroll'><table><tr>{head}</tr>"
            f"{''.join(rows)}</table></div><p class='sub'>{c['table_note']}</p></details>")


def page(inp: Inputs, lang: str, today: dt.date) -> str:
    c = COPY[lang]
    data, clim, nights = payload(inp, lang, today)
    ev = evidence(inp, clim)
    prefix = "" if lang == "es" else "../"
    first = nights[0][0] if nights else ("autumn" if today.month >= 7 else "spring")
    options = "".join(f"<option value='{k}'>{_night(n, lang)}</option>" for k, n in nights)
    buttons = [("forecast", c["mode_forecast"])] if nights else []
    buttons += [("autumn", c["mode_autumn"]), ("spring", c["mode_spring"])]
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    legend = ("<div class='legend'>"
              f"<span><i class='ramp'></i>{c['legend_ramp']}</span>"
              f"<span><i class='line'></i>{c['legend_line']}</span>"
              f"<span><i class='st'></i>{c['legend_station']}</span>"
              "<span class='forecast-only'>" + " ".join(
                  f"<i class='dot' style='background:{ADVICE_COLOR[a]}'></i>{ADVICE_NAME[lang][a]}"
                  for a in ("stop", "stop at peak hours", "watch", "run")) + f" · {c['legend_size']}</span>"
              f"<span class='history-only'><i class='dot hot'></i>{c['legend_exposure']} · {c['legend_size']}</span>"
              "</div>")
    p = [f"<!doctype html><html lang='{lang}'><meta charset='utf-8'>",
         "<meta name='viewport' content='width=device-width,initial-scale=1'>",
         f"<title>{c['title']}</title>", FAVICON,
         f"<meta name='description' content='{c['description']}'>",
         f"<link rel='alternate' hreflang='es' href='{BASE}rutas.html'>",
         f"<link rel='alternate' hreflang='en' href='{BASE}en/routes.html'>",
         "<link rel='preconnect' href='https://fonts.googleapis.com'>",
         "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>",
         f"<link rel='stylesheet' href='{FONTS}'>",
         f"<style>{COMMON_CSS}{SITE_CSS}{CSS}{site.CSS}</style>",
         site.page_bar(lang, "routes", prefix.count("../")),
         "<header class='site-header'>",
         f"<h1><a href='{prefix or './'}' class='home'>{LOGO_SVG}Sub <span>Nocte</span></a></h1>",
         f"<p class='kicker'>{c['kicker']}</p>",
         f"<p class='lede'>{c['claim']}</p>",
         _figures(ev, lang), "</header>",
         "<main class='wrap'>",
         "<section class='routes' aria-labelledby='h-map'>",
         f"<h2 id='h-map'>{c['h_map']}</h2>",
         "<div class='controls' role='group' aria-label='" + c["controls"] + "'>"
         + "".join(f"<button type='button' data-mode='{k}'>{t}</button>" for k, t in buttons)
         + (f"<label class='night-pick'><span>{c['pick_night']}</span> <select id='map-night'>{options}</select>"
            "</label>" if nights else "")
         + f"<button type='button' id='map-play' class='play'>{c['pause']}</button></div>",
         f"<p class='cap' id='map-cap'></p>",
         "<div class='stage'><div id='map' class='map'><canvas id='map-base'></canvas><canvas id='map-fx'></canvas>"
         f"<canvas id='map-top' aria-label='{c['map_alt']}' role='img'></canvas></div>"
         f"<aside id='map-panel' class='panel' aria-live='polite'><p class='hint'>{c['hint']}</p></aside></div>",
         f"<label class='zone-pick'><span>{c['pick_zone']}</span> <select id='map-zone'><option value=''>—</option>"
         + "".join(f"<option value='{z[0]}'>{z[1]} · {_num(z[4], lang)} MW</option>" for z in data["zones"]) + "</select></label>",
         legend,
         f"<p class='read'>{c['read']}</p>",
         f"<noscript><p>{c['noscript']}</p></noscript>",
         "</section>",
         f"<h2>{c['h_why']}</h2><p class='sub'>{c['sub_why']}</p>", _why(ev, lang),
         f"<p>{c['why_more'].format(wind=prefix + site.PAGES['farms'][lang], check=prefix + 'output/wind_check.html')}</p>",
         f"<h2>{c['h_table']}</h2><p class='sub'>{c['sub_table']}</p>", _table(clim, lang),
         f"<h2>{c['h_method']}</h2><ol class='steps'>"
         + "".join(f"<li><h3>{t}</h3><p>{b}</p></li>" for t, b in c["method"]).format(
             vec=_pct(R.MIN_VEC_FRAC, lang), mins=R.MIN_NIGHT_MIN, speed=_num(R.MAX_SPEED, lang),
             cap=_num(100 * R.CAP_Q, lang), min_n=R.MIN_NIGHTS, sigma=R.SIGMA_KM, fade0=R.FADE_KM[0],
             fade1=R.FADE_KM[1], grid=_num(R.GRID, lang, 1), window=R.WINDOW_DAYS)
         + "</ol>",
         f"<h2>{c['h_limits']}</h2><ul>" + "".join(f"<li>{x}</li>" for x in c["limits"]) + "</ul>",
         f"<h2>{c['h_sources']}</h2><p class='data-note'>{c['sources']}</p>",
         f"<p class='data-note'>{c['code'].format(repo=REPO)}</p>",
         "</main>", site_footer(lang, today),
         f"<script type='application/json' id='routes-data'>{blob}</script>",
         f"<script>var FIRST='{first}';{JS}</script>", "</html>"]
    return "\n".join(p)


def build(inp: Inputs, root: Path, log=print, today: dt.date | None = None) -> list[Path]:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    written = []
    for lang in ("es", "en"):
        dest = root / PAGE[lang]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page(inp, lang, today), encoding="utf-8", newline="\n")
        log(f"{dest} ({dest.stat().st_size / 1000:.0f} kB)")
        written.append(dest)
    return written


# ---------------------------------------------------------------- look and behaviour

CSS = """
.site-header h1 a.home{text-decoration:none;color:inherit}
.kicker{margin:-6px 0 0;font:600 21px/1.2 var(--font-title);text-transform:uppercase;letter-spacing:.08em;color:var(--accent)}
.routes{background:#0b1424;color:#e8ecf4;margin:8px -16px 26px;padding:18px 16px 16px}
@media (min-width:1032px){.routes{margin-left:0;margin-right:0}}
.routes h2{color:#fff;margin-top:0}
.routes .cap,.routes .read{color:#aab3c5;font-size:15px;max-width:78ch}
.routes .cap{min-height:3em;margin:6px 0 10px}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0 4px}
.controls button{font:600 14px/1 var(--font-title);text-transform:uppercase;letter-spacing:.06em;background:transparent;color:#cfd6e4;border:1.5px solid #3a4a66;padding:8px 12px 7px;cursor:pointer}
.controls button[aria-pressed=true]{background:#ffd28a;color:#1a1408;border-color:#ffd28a}
.controls .play{margin-left:auto}
.routes select{font:14px var(--font-data);background:#13223a;color:#e8ecf4;border:1px solid #3a4a66;padding:6px 8px;max-width:100%}
.routes select:disabled{opacity:.45}
.night-pick span,.zone-pick span{font:600 13px var(--font-title);text-transform:uppercase;letter-spacing:.06em;color:#aab3c5}
.stage{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:14px;align-items:start}
.map{position:relative;width:100%;min-height:200px;touch-action:manipulation}
.map canvas{position:absolute;left:0;top:0;display:block}
#map-top{cursor:pointer}
.panel{background:#111d31;border:1px solid #2a3a56;padding:12px 14px;font-size:15px;line-height:1.45;max-height:86vh;overflow:auto}
.panel h3{margin:0 0 4px;color:#fff}
.panel p{margin:0 0 9px}
.panel .hint{color:#aab3c5;margin:0}
.panel small{color:#aab3c5}
.panel .tonight{border-left:4px solid var(--c,#8a94a6);padding:2px 0 1px 10px;margin:0 0 10px}
.panel .advice b{text-transform:uppercase;font-family:var(--font-title);letter-spacing:.05em;font-size:16px}
.zone-pick{display:block;margin:12px 0 0}
.routes .legend{color:#aab3c5;margin:12px 0 4px;gap:10px 18px}
.routes .legend i{display:inline-block;vertical-align:-2px;margin-right:6px}
.legend i.ramp{width:90px;height:11px;background:linear-gradient(90deg,#2d2470,#7b3fa0,#c8507a,#f08c3c,#ffe08a)}
.legend i.line{width:24px;height:2px;background:#efe3c6;vertical-align:4px}
.legend i.st{width:10px;height:10px;border:2px solid #fff;border-radius:50%}
.legend i.dot{width:11px;height:11px;border-radius:50%;margin-left:6px}
.legend i.hot{width:40px;height:11px;border-radius:6px;background:linear-gradient(90deg,#8a94a6,#e0452f)}
.routes[data-kind=history] .forecast-only,.routes[data-kind=forecast] .history-only{display:none}
details{margin:6px 0 10px}
details summary{cursor:pointer;font:600 15px/1.3 var(--font-title);text-transform:uppercase;letter-spacing:.06em;color:var(--accent)}
ol.steps{list-style:none;counter-reset:step;padding:0;margin:18px 0 0}
ol.steps>li{counter-increment:step;position:relative;padding:0 0 0 52px;margin:0 0 20px}
ol.steps>li::before{content:counter(step);position:absolute;left:0;top:-2px;width:36px;height:36px;display:grid;place-items:center;border:2px solid var(--accent);color:var(--accent);font:700 20px/1 var(--font-data)}
ol.steps h3{margin:4px 0 6px}
ol.steps p{margin:0}
@media (max-width:820px){.stage{grid-template-columns:1fr}.panel{max-height:none}.controls .play{margin-left:0}}
"""

# The map script. It reads the JSON block, draws land, the expected passage and the flow lines once per mode on
# the bottom canvas, animates particles along the same field on the middle one and keeps the clickable wind zones
# and radars on the top one. With «reduce motion» it starts paused: the lines alone carry the map.
JS = r"""
(function(){
var D=JSON.parse(document.getElementById('routes-data').textContent),G=D.grid,E=D.extent,LG=D.log,T=D.text;
var sec=document.querySelector('.routes'),wrap=document.getElementById('map'),cb=document.getElementById('map-base'),
cf=document.getElementById('map-fx'),ct=document.getElementById('map-top'),panel=document.getElementById('map-panel'),
cap=document.getElementById('map-cap'),nightSel=document.getElementById('map-night'),
zoneSel=document.getElementById('map-zone'),playBtn=document.getElementById('map-play');
var reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
var playing=!reduce,visible=true,raf=0,M=null,W=0,H=0,S=1,OX=0,KX=Math.cos((E[2]+E[3])/360*Math.PI),sel=null,P=[];
var ZB={};D.zones.forEach(function(z){ZB[z[0]]=z});
var RAMP=[[0,[45,36,112]],[.35,[123,63,160]],[.6,[200,80,122]],[.8,[240,140,60]],[1,[255,224,138]]];
function ramp(t){t=t<0?0:t>1?1:t;for(var k=1;k<RAMP.length;k++){if(t<=RAMP[k][0]){var a=RAMP[k-1],b=RAMP[k],
f=(t-a[0])/(b[0]-a[0]);return [0,1,2].map(function(i){return Math.round(a[1][i]+(b[1][i]-a[1][i])*f)})}}
return RAMP[RAMP.length-1][1]}
var LUT=[];for(var q=0;q<=32;q++)LUT.push(ramp(.45+.55*q/32).join(','));
function px(lon){return OX+(lon-E[0])*KX*S}
function py(lat){return (E[3]-lat)*S}
function sample(lon,lat){
var gx=(lon-G.lon0)/G.step,gy=(lat-G.lat0)/G.step;
if(gx<0||gy<0||gx>G.nx-1||gy>G.ny-1)return null;
var i=Math.min(Math.floor(gx),G.nx-2),j=Math.min(Math.floor(gy),G.ny-2),fx=gx-i,fy=gy-j,n=G.nx,k=j*n+i,
w0=(1-fx)*(1-fy),w1=fx*(1-fy),w2=(1-fx)*fy,w3=fx*fy;
function b(a){return (a[k]*w0+a[k+1]*w1+a[k+n]*w2+a[k+n+1]*w3)/100}
return [b(M.u),b(M.v),b(M.a),b(M.i),b(M.ia)]}
function inten(s){return s[4]*Math.max(0,Math.min(1,(s[3]-LG[0])/(LG[1]-LG[0])))}
function rng(seed){return function(){seed|=0;seed=seed+0x6D2B79F5|0;var t=Math.imul(seed^seed>>>15,1|seed);
t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function landPath(c){c.beginPath();D.land.forEach(function(r){c.moveTo(px(r[0]/100),py(r[1]/100));
for(var k=2;k<r.length;k+=2)c.lineTo(px(r[k]/100),py(r[k+1]/100));c.closePath()})}
function arrow(c,x,y,ang,len){c.beginPath();c.moveTo(x-len*Math.cos(ang-.5),y-len*Math.sin(ang-.5));c.lineTo(x,y);
c.lineTo(x-len*Math.cos(ang+.5),y-len*Math.sin(ang+.5));c.stroke()}
var OCC=.42;
function cell(lo,la){return Math.round(lo/OCC)+','+Math.round(la/OCC)}
function trace(lo,la,dir,id,occ){var out=[],h=.07;for(var n=0;n<55;n++){var s=sample(lo,la);if(!s)break;
var m=Math.hypot(s[0],s[1]);if(s[2]<.12||m<.16)break;lo+=dir*s[0]/m*h/KX;la+=dir*s[1]/m*h;
var o=occ[cell(lo,la)];if(o&&o!==id)break;out.push([lo,la,s[2]*Math.min(1,m*1.15)])}return out}
function drawBase(){
var c=cb.getContext('2d');c.fillStyle='#0a1322';c.fillRect(0,0,W,H);landPath(c);c.fillStyle='#1a2b45';c.fill();
var o=document.createElement('canvas');o.width=G.nx;o.height=G.ny;var oc=o.getContext('2d'),img=oc.createImageData(G.nx,G.ny);
for(var j=0;j<G.ny;j++)for(var i=0;i<G.nx;i++){var k=j*G.nx+i,ia=M.ia[k]/100,t=(M.i[k]/100-LG[0])/(LG[1]-LG[0]);
if(ia<=0||t<=0)continue;var col=ramp(t),p=((G.ny-1-j)*G.nx+i)*4;img.data[p]=col[0];img.data[p+1]=col[1];
var edge=Math.min(1,Math.min(i,j,G.nx-1-i,G.ny-1-j)/4);
img.data[p+2]=col[2];img.data[p+3]=Math.round(255*ia*edge*(.3+.55*Math.min(1,t)))}
oc.putImageData(img,0,0);c.save();c.imageSmoothingEnabled=true;c.globalCompositeOperation='screen';
var x0=px(G.lon0-G.step/2),x1=px(G.lon0+(G.nx-.5)*G.step),y0=py(G.lat0+(G.ny-.5)*G.step),y1=py(G.lat0-G.step/2);
c.drawImage(o,x0,y0,x1-x0,y1-y0);c.restore();
var r=rng(11),seeds=[],occ={},id=0;
for(var la=E[2]+.2;la<E[3];la+=.55)for(var lo=E[0]+.2;lo<E[1];lo+=.55)seeds.push([lo+(r()-.5)*.35,la+(r()-.5)*.35]);
for(var a=seeds.length-1;a>0;a--){var b=Math.floor(r()*(a+1)),tmp=seeds[a];seeds[a]=seeds[b];seeds[b]=tmp}
c.lineCap='round';c.lineJoin='round';
seeds.forEach(function(sd){var s=sample(sd[0],sd[1]);if(!s||s[2]<.2||Math.hypot(s[0],s[1])<.22||occ[cell(sd[0],sd[1])])return;
id++;var fw=trace(sd[0],sd[1],1,id,occ),bw=trace(sd[0],sd[1],-1,id,occ),line=bw.reverse().concat([[sd[0],sd[1],s[2]]],fw);
if(line.length<9)return;line.forEach(function(p){occ[cell(p[0],p[1])]=id});
for(var k=1;k<line.length;k++){var p=line[k-1],q=line[k];c.strokeStyle='rgba(239,227,198,'+(.12+.5*q[2]).toFixed(3)+')';
c.lineWidth=1.15;c.beginPath();c.moveTo(px(p[0]),py(p[1]));c.lineTo(px(q[0]),py(q[1]));c.stroke()}
var e=line[line.length-1],f=line[line.length-3];c.strokeStyle='rgba(239,227,198,'+(.2+.6*e[2]).toFixed(3)+')';
arrow(c,px(e[0]),py(e[1]),Math.atan2(py(e[1])-py(f[1]),px(e[0])-px(f[0])),6)});
// coast and borders last, so the lines do not hide where the land is
landPath(c);c.strokeStyle='rgba(176,196,228,.6)';c.lineWidth=.9;c.stroke()}
function zr(z){return (2.5+Math.sqrt(z[4])/3.2)*Math.min(1,.55+W/1400)}
function heat(e){var a=[138,148,166],b=[224,69,47],t=Math.pow(e,2);return 'rgb('+[0,1,2].map(function(i){return Math.round(a[i]+(b[i]-a[i])*t)}).join(',')+')'}
function zoneColor(z){if(M.kind==='forecast'){var s=M.zs[z[0]];return s?D.advice[s[0]]:null}
var e=M.season==='autumn'?z[5]:z[6];return e==null?null:heat(e)}
function drawTop(){var c=ct.getContext('2d');c.clearRect(0,0,W,H);
var zs=D.zones.slice().sort(function(a,b){return b[4]-a[4]});
zs.forEach(function(z){var col=zoneColor(z);if(!col)return;var x=px(z[2]),y=py(z[3]),r=zr(z);
c.beginPath();c.arc(x,y,r,0,7);c.globalAlpha=.88;c.fillStyle=col;c.fill();c.globalAlpha=1;c.lineWidth=1;
c.strokeStyle='#0a1322';c.stroke();if(sel&&sel[0]==='z'&&sel[1]===z[0]){c.beginPath();c.arc(x,y,r+4,0,7);
c.strokeStyle='#fff';c.lineWidth=2;c.stroke()}});
c.lineCap='round';M.st.forEach(function(s){var x=px(s[1]),y=py(s[2]),h=s[3]*Math.PI/180,L=(9+22*s[4])*Math.min(1,.45+W/1200),
dx=Math.sin(h),dy=-Math.cos(h);c.strokeStyle='rgba(10,19,34,.85)';c.lineWidth=4.5;c.beginPath();c.moveTo(x,y);
c.lineTo(x+dx*L,y+dy*L);c.stroke();c.strokeStyle='#fff';c.fillStyle='#fff';c.lineWidth=2;c.beginPath();
c.moveTo(x,y);c.lineTo(x+dx*L,y+dy*L);c.stroke();arrow(c,x+dx*L,y+dy*L,Math.atan2(dy,dx),6);c.beginPath();
c.arc(x,y,3.6,0,7);c.fill();if(sel&&sel[0]==='s'&&sel[1]===s[0]){c.beginPath();c.arc(x,y,8,0,7);c.stroke()}})}
function spawn(p){p.lo=null;p.life=120+Math.random()*200;p.age=0;for(var t=0;t<25;t++){
var lo=E[0]+Math.random()*(E[1]-E[0]),la=E[2]+Math.random()*(E[3]-E[2]),s=sample(lo,la);if(!s||s[2]<.05)continue;
if(Math.random()<s[2]*(.18+.82*inten(s))*Math.min(1,Math.hypot(s[0],s[1])*1.5)){p.lo=lo;p.la=la;return}}}
function seed(){var n=W<600?700:1600;P=[];for(var k=0;k<n;k++){var p={};spawn(p);p.age=Math.random()*p.life;P.push(p)}
cf.getContext('2d').clearRect(0,0,W,H)}
function frame(){raf=0;if(!playing||!visible||!M)return;var c=cf.getContext('2d');
c.globalCompositeOperation='destination-out';c.fillStyle='rgba(0,0,0,.04)';c.fillRect(0,0,W,H);
c.globalCompositeOperation='source-over';c.lineWidth=1.4;c.lineCap='round';var st=.55/S;
for(var k=0;k<P.length;k++){var p=P[k];if(p.lo===null||p.age++>p.life){spawn(p);continue}
var s=sample(p.lo,p.la);if(!s||s[2]<.04){p.lo=null;continue}var m=Math.hypot(s[0],s[1]);if(m<.05){p.age+=3;continue}
var f=st*(.45+m),lo=p.lo+s[0]/m*f/KX,la=p.la+s[1]/m*f,t=inten(s);
c.strokeStyle='rgba('+LUT[Math.round(t*32)]+','+(s[2]*(.3+.7*Math.min(1,m*1.4))).toFixed(3)+')';
c.beginPath();c.moveTo(px(p.lo),py(p.la));c.lineTo(px(lo),py(la));c.stroke();p.lo=lo;p.la=la}
raf=requestAnimationFrame(frame)}
function kick(){if(!raf&&playing&&visible)raf=requestAnimationFrame(frame)}
function fill(t,o){return t.replace(/\{(\w+)\}/g,function(m,k){return o[k]==null?m:o[k]})}
function show(){if(!sel){panel.innerHTML='<p class="hint">'+T.hint+'</p>';zoneSel.value='';return}
if(sel[0]==='z'){var z=ZB[sel[1]],night='';if(M.kind==='forecast'&&M.zs[z[0]]){var s=M.zs[z[0]];
night='<div class="tonight" style="--c:'+D.advice[s[0]]+'">'+fill(T.zone_night,{night:M.night,level:s[1],rel:s[2],
wind:s[3],frac:s[4],cost:s[5],advice:T.advice[s[0]],why:T.why[s[0]]})+'</div>'}
panel.innerHTML=z[7].replace('@@N@@',night);zoneSel.value=z[0];return}
var row=null;M.st.forEach(function(r){if(r[0]===sel[1])row=r});zoneSel.value='';
if(row){var o=row[5];o.name=row[0];panel.innerHTML=fill(T.station_html,o)}else{sel=null;show()}}
function setMode(k){if(!D.modes[k])return;M=D.modes[k];if(M.kind==='forecast'&&D.fdir){M.u=D.fdir.u;M.v=D.fdir.v;
M.a=D.fdir.a;M.st=D.fdir.st}sec.setAttribute('data-kind',M.kind);cap.innerHTML=M.cap;
document.querySelectorAll('.controls [data-mode]').forEach(function(b){var m=b.getAttribute('data-mode');
b.setAttribute('aria-pressed',String(m===k||(m==='forecast'&&M.kind==='forecast')))});
if(nightSel){nightSel.disabled=M.kind!=='forecast';if(M.kind==='forecast')nightSel.value=k}
drawBase();drawTop();seed();show();kick()}
function resize(){var dpr=Math.min(window.devicePixelRatio||1,2);W=wrap.clientWidth;
var maxH=Math.max(380,Math.min(window.innerHeight*.86,980)),dx=(E[1]-E[0])*KX,dy=E[3]-E[2];
S=Math.min(W/dx,maxH/dy);H=Math.round(dy*S);OX=(W-dx*S)/2;wrap.style.height=H+'px';
[cb,cf,ct].forEach(function(c){c.width=Math.round(W*dpr);c.height=Math.round(H*dpr);c.style.width=W+'px';
c.style.height=H+'px';c.getContext('2d').setTransform(dpr,0,0,dpr,0,0)});if(M){drawBase();drawTop();seed()}}
document.querySelectorAll('.controls [data-mode]').forEach(function(b){b.addEventListener('click',function(){
var m=b.getAttribute('data-mode');setMode(m==='forecast'?nightSel.value:m)})});
if(nightSel)nightSel.addEventListener('change',function(){setMode(nightSel.value)});
zoneSel.addEventListener('change',function(){sel=zoneSel.value?['z',zoneSel.value]:null;show();drawTop()});
playBtn.addEventListener('click',function(){playing=!playing;playBtn.textContent=playing?T.pause:T.play;
if(!playing)cf.getContext('2d').clearRect(0,0,W,H);kick()});
playBtn.textContent=playing?T.pause:T.play;
ct.addEventListener('click',function(ev){var b=ct.getBoundingClientRect(),x=ev.clientX-b.left,y=ev.clientY-b.top,best=null,bd=9;
D.zones.forEach(function(z){if(!zoneColor(z))return;var d=Math.hypot(px(z[2])-x,py(z[3])-y)-zr(z);if(d<bd){bd=d;best=['z',z[0]]}});
M.st.forEach(function(s){var d=Math.hypot(px(s[1])-x,py(s[2])-y)-4;if(d<bd){bd=d;best=['s',s[0]]}});
sel=best;show();drawTop()});
if('IntersectionObserver' in window)new IntersectionObserver(function(es){visible=es[0].isIntersecting;kick()}).observe(wrap);
document.addEventListener('visibilitychange',function(){visible=!document.hidden;kick()});
var rt=0;window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(function(){if(wrap.clientWidth!==W)resize()},150)});
resize();setMode(D.modes[FIRST]?FIRST:Object.keys(D.modes)[0]);
})();
"""


# ---------------------------------------------------------------- the prose, in both languages

COPY: dict[str, dict] = {
    "es": {
        "title": "Sub Nocte · rutas de la migración nocturna",
        "description": "Por dónde vuela de noche la migración de aves sobre la península ibérica y Francia, medido "
                       "por los radares meteorológicos, y qué parques eólicos quedan en su camino las próximas noches.",
        "kicker": "Rutas de la migración nocturna",
        "claim": "Por dónde vuelan de noche las aves que cruzan la península y Francia, según lo que miden los "
                 "radares meteorológicos desde 2016, y qué parques eólicos quedan en su camino las próximas "
                 "noches. Las líneas son medidas, no un dibujo: donde no hay radar, el mapa se apaga.",
        "fig_nights": "noches de radar con vector de vuelo",
        "fig_stations": "estaciones de radar en el mapa",
        "fig_top": "del paso cae en el 10 % de noches más fuertes",
        "fig_lift": "más noches fuertes cuando la regla dice parar que al azar",
        "h_map": "El mapa",
        "controls": "Qué mostrar",
        "mode_forecast": "Próximas noches",
        "mode_autumn": "Otoño · histórico",
        "mode_spring": "Primavera · histórico",
        "pick_night": "Noche",
        "pick_zone": "O elige un parque",
        "pause": "Pausa",
        "play": "Animar",
        "hint": "Pulsa un parque eólico (círculo) para ver por qué parar o no, o un radar (flecha blanca) para "
                "ver qué mide.",
        "map_alt": "Mapa animado de la península ibérica y Francia con las líneas de vuelo de la migración "
                   "nocturna, el paso esperado y los parques eólicos.",
        "cap_history": "<b>Histórico de {season}.</b> Líneas: la dirección media del paso en {n} estaciones de "
                       "radar ({nights} noches con vector; un radar renovado en el mismo sitio cuenta como una sola "
                       "estación, y las Azores y Canarias quedan fuera del mapa). Color: el paso medio de la temporada que calcula el "
                       "modelo en cada parque y ciudad. Círculos: parques, más rojos cuanto más paso medio reciben.",
        "cap_forecast": "<b>Noche del {night}.</b> Color: el paso previsto por Sub Nocte. Líneas: la dirección "
                        "habitual para estas fechas (noches de ±{window} días, todos los años), no una previsión de "
                        "rumbo. <b>{stop}</b> zonas eólicas con sugerencia de parar ({mw} MW).",
        "legend_ramp": "paso de aves: poco → mucho",
        "legend_line": "dirección de vuelo (más nítida, más constante)",
        "legend_station": "radar y su dirección media",
        "legend_size": "tamaño = MW",
        "legend_exposure": "parque: paso medio de la temporada",
        "read": "Cómo leerlo: las líneas y las partículas van hacia donde vuelan las aves y son más nítidas "
                "cuanto más se repite la dirección noche tras noche. Las partículas se juntan donde se espera "
                "más paso. Los círculos son las zonas eólicas de OpenStreetMap (celdas de medio grado, unos "
                "55 × 42 km).",
        "noscript": "El mapa necesita JavaScript. La tabla de rutas y el método de abajo se leen sin él.",
        "in_season": "En {season}",
        "around": "En torno a esta fecha",
        "station_html": "<h3>{name}</h3><p><small>radar · {radars}</small></p><p><b>{when}</b> las aves vuelan "
                        "hacia el <b>{dir}</b> ({heading}°), {word} ({r}), a {speed} m/s sobre el suelo y a unos "
                        "{alt} m de altitud media.</p><p>{nights} noches con vector, {years}. El 10 % de noches "
                        "más fuertes lleva el {top} del paso. Una noche fuerte (percentil 90: la que solo supera "
                        "una de cada diez) son unas {p90} aves "
                        "por kilómetro de frente <small>(orientativo: depende de la calibración del radar)</small>."
                        "</p>",
        "country": {"ES": "España", "PT": "Portugal", "FR": "Francia"},
        "zone_head": "<h3>{place}</h3><p><small>{zone} · {country}</small><br>{turbines} aerogeneradores · {mw} MW "
                     "en OpenStreetMap</p>@@N@@",
        "zone_route": "<b>Ruta en {season}:</b> hacia el {dir}, {word} ({r}); el radar con vector más cercano es "
                      "{station}, a {km} km.",
        "zone_no_route": "<b>Ruta en {season}:</b> ningún radar con vector lo bastante cerca; sin dato.",
        "zone_rank": "Por paso medio previsto, es la zona {rank} de {n}.",
        "zone_check": "<b>¿Acierta aquí?</b> Con el radar de {radar} (a {km} km), en {nights} noches, la previsión "
                      "y la medida ordenan las noches con una correlación de {rho}.",
        "zone_check_vh": " En las noches de nivel muy alto, el radar midió paso fuerte el {busy} de las veces (al "
                         "azar, el {chance}).",
        "zone_no_check": "<b>¿Acierta aquí?</b> No hay radar a menos de 75 km para comprobarlo.",
        "above": "por encima del percentil {p} de su propio registro",
        "below": "por debajo de la mediana de su propio registro",
        "zone_night": "<p><b>{night}:</b> paso {level}, {rel}. Viento a 100 m: {wind} m/s; la zona produciría el "
                      "{frac} de su potencia, así que parar es {cost}.</p><p class='advice'>Sugerencia: <b>{advice}"
                      "</b>. {why}</p>",
        "cost": {"cheap": "barato", "moderate": "moderado", "expensive": "caro"},
        "why": {"stop": "Mucho paso y poco viento: parar cuesta poco y protege una de las pocas noches que "
                        "concentran la migración.",
                "stop at peak hours": "Mucho paso, pero con viento parar toda la noche ya cuesta: basta con "
                                      "las horas de más paso.",
                "watch": "Paso alto, o muy alto con mucho viento: vigilar (radar, observación), sin parar por "
                         "defecto.",
                "run": "Paso normal para la fecha: nada que hacer."},
        "h_why": "Por qué parar estos parques, y solo unas noches",
        "sub_why": "Cuatro cifras, todas calculadas con los datos de esta página.",
        "why_front_h": "Un frente ancho que cruza todo",
        "why_front": "En otoño, {sw} de las {n} estaciones de radar del mapa ven el paso entre el sur y el "
                     "suroeste, y {steady} con una constancia de 0,7 o más. No es un pasillo estrecho: es un río "
                     "de aves de cientos de kilómetros de ancho que barre Francia y la península hacia el "
                     "Estrecho. Cualquier parque del recorrido queda en su camino.",
        "why_few_h": "Pocas noches lo deciden",
        "why_few": "En la estación mediana, el 10 % de las noches más fuertes lleva el {top} de todo el paso de "
                   "la temporada. Parar esas noches protege mucho; parar las demás, poco.",
        "why_cheap_h": "Y suelen ser noches de poco viento",
        "why_cheap": "Probada sobre 2021-2026 en las {zones} zonas de España y Portugal, la regla habría parado {nights} noches por "
                     "temporada y zona, con un {lost} de la producción nocturna; parar todas las noches de paso "
                     "muy alto costaría el {all}. Medida con la propia previsión, que aplana los picos, cubre el "
                     "{covered} del paso previsto.",
        "why_right_h": "El radar confirma las noches elegidas",
        "why_right": "En las noches en que la regla dice parar, el radar más cercano midió paso fuerte el {busy} "
                     "de las veces; al azar sería el {chance}. Son {lift} veces más.",
        "why_more": "La previsión por zona, noche a noche, en tabla y con la regla explicada: "
                    "<a href='{wind}'>parques eólicos</a>; la regla probada desde 2021: "
                    "<a href='{check}'>verificación</a> (en inglés).",
        "h_table": "Las rutas, estación por estación",
        "sub_table": "Lo mismo que dibujan las flechas blancas, con todas sus cifras.",
        "table_summary": "Ver la tabla: dirección, constancia, velocidad, altitud y concentración",
        "table_cols": ["estación", "temporada", "años", "noches", "dirección", "constancia", "m/s", "altitud (m)",
                       "10 % más fuerte"],
        "table_note": "Constancia: 1 si todas las noches vuelan en la misma dirección, 0 si se anulan. Velocidad "
                      "sobre el suelo (incluye el viento). Altitud media sobre el nivel del mar, ponderada por el "
                      "tráfico. Última columna: parte del paso que llevan las noches del 10 % más fuerte.",
        "h_method": "Cómo se calcula",
        "method": [
            ("Del eco al vector de vuelo",
             "Cada perfil de radar (calculado con vol2bird, el programa que separa los ecos de aves de los "
             "de lluvia e insectos, cada 5 a 15 minutos, y publicado en abierto por Aloft) da, por capas de 200 m entre 200 m y 3 km, la "
             "densidad de aves y su velocidad sobre el suelo hacia el este y hacia el norte. Densidad × velocidad "
             "× grosor de la capa × tiempo, sumado sobre la noche, es el <b>tráfico</b>: cuántas aves cruzan cada "
             "kilómetro de un frente perpendicular a su vuelo. Su dirección es la de esa noche."),
            ("Qué noches cuentan",
             "Meses de paso (marzo a mayo, agosto a noviembre) en los que el radar publicó vectores. Una noche "
             "cuenta si al menos el {vec} de su densidad lleva vector, si el radar la vio {mins} minutos o más y "
             "si la velocidad sobre el suelo no pasa de {speed} m/s: más rápido suele ser lluvia o un eco "
             "arrastrado por el viento, no aves."),
            ("De noches a ruta",
             "Por estación y temporada se suman los vectores de tráfico de todas sus noches. La dirección de la "
             "suma es la ruta; su <b>constancia</b> (largo de la suma ÷ suma de los largos, de 0 a 1) dice si las "
             "noches coinciden. Para la dirección ninguna noche pesa más que el percentil {cap} de su estación, "
             "para que una sola noche enorme no gire la flecha. Hacen falta {min_n} noches. Los radares viejos y "
             "renovados del mismo sitio son una estación, cada uno en su propia escala."),
            ("Del radar al mapa",
             "Las líneas no salen de un modelo: son un suavizado entre radares (núcleo gaussiano de {sigma} km "
             "sobre una malla de {grid}°), que se dibuja entero hasta {fade0} km del radar más cercano y se "
             "apaga a {fade1} km. Donde no hay radar, no hay línea."),
            ("Las próximas noches",
             "En «Próximas noches» la dirección es la habitual para esa fecha (noches de ±{window} días alrededor, "
             "todos los años) y el color es la previsión de Sub Nocte para cada zona eólica y ciudad. En el "
             "histórico, el color es la media de la temporada que el mismo modelo calcula con la meteorología de "
             "2021-2026."),
            ("Por qué parar aquí",
             "Al pulsar un parque: el nivel de la noche (relativo a su propio registro), el viento previsto a "
             "100 m y lo que costaría parar, la ruta que pasa por encima, su puesto entre las zonas por paso "
             "medio y cómo acierta el modelo con el radar más cercano."),
        ],
        "h_limits": "Qué no dice este mapa",
        "limits": [
            "<b>Altura.</b> El radar mide de unos 200 m a 3 km; las palas barren de 30 a 200 m sobre el suelo. La "
            "ruta es la de la columna de aire, no la de la altura del rotor; en las sierras, donde los parques "
            "están a 800-1.500 m, las dos bandas se acercan.",
            "<b>Dirección sobre el suelo, no rumbo.</b> Incluye la deriva del viento: es por donde pasan, no hacia "
            "donde apuntan.",
            "<b>Frente ancho, no pasillos.</b> La migración nocturna de paseriformes no va por un corredor "
            "estrecho; las líneas dan el sentido general del flujo, no una frontera fuera de la cual no pasan aves.",
            "<b>Huecos en el tiempo.</b> Los radares renovados de AEMET y los franceses desde 2021 apenas publican "
            "vector en Aloft: la ruta española se apoya sobre todo en 2018-2020 y la francesa en 2016-2022. "
            "Portugal, 2019-2026.",
            "<b>Huecos en el espacio.</b> Lejos de los radares no hay dato y el mapa se apaga en vez de inventar. "
            "Azores y Canarias quedan fuera del mapa.",
            "<b>La cantidad es orientativa.</b> El número de aves depende de la calibración de cada radar y se "
            "compara mal entre radares; la dirección no depende de ella.",
            "<b>No son todas las víctimas.</b> La mortalidad documentada en los parques españoles es sobre todo de "
            "rapaces y planeadoras diurnas y de murciélagos; esto es la migración nocturna.",
        ],
        "h_sources": "Fuentes",
        "sources": "Perfiles verticales de aves y vectores de vuelo: <a href='https://aloftdata.eu'>Aloft</a> "
                   "(CC0), el archivo abierto europeo de perfiles de aves, calculados con vol2bird sobre los radares "
                   "de AEMET, IPMA y Météo-France (red OPERA, la que reúne los radares meteorológicos europeos). "
                   "Parques: © colaboradores de <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap"
                   "</a> (ODbL). Meteorología: <a href='https://open-meteo.com'>Open-Meteo</a> (CC BY 4.0) y ERA5 "
                   "de Copernicus (la reconstrucción hora a hora del tiempo pasado). Costas y fronteras: <a href='https://www.naturalearthdata.com'>Natural Earth</a> "
                   "(dominio público). Método: Dokter y col. (2011) para vol2bird; Horton y col. (2021) para la "
                   "concentración del paso en pocas noches.",
        "code": "Todo el código y los datos derivados (el tráfico de cada noche en "
                "<code>data/routes/flight_nights.parquet</code>) están en el <a href='{repo}'>repositorio</a>.",
    },
    "en": {
        "title": "Sub Nocte · nocturnal migration routes",
        "description": "Where the nocturnal bird migration flies over Iberia and France, as the weather radars "
                       "measure it, and which wind farms lie in its way over the coming nights.",
        "kicker": "Nocturnal migration routes",
        "claim": "Where the birds crossing Iberia and France fly at night, from what the weather radars have "
                 "measured since 2016, and which wind farms lie in their way over the coming nights. The lines "
                 "are measured, not drawn: where there is no radar, the map fades out.",
        "fig_nights": "radar nights with a flight vector",
        "fig_stations": "radar stations on the map",
        "fig_top": "of the passage falls on the heaviest 10% of nights",
        "fig_lift": "more heavy nights when the rule says stop than by chance",
        "h_map": "The map",
        "controls": "What to show",
        "mode_forecast": "Coming nights",
        "mode_autumn": "Autumn · record",
        "mode_spring": "Spring · record",
        "pick_night": "Night",
        "pick_zone": "Or pick a wind farm",
        "pause": "Pause",
        "play": "Animate",
        "hint": "Tap a wind farm (circle) to see why it should stop or not, or a radar (white arrow) to see what "
                "it measures.",
        "map_alt": "Animated map of Iberia and France with the flight lines of the nocturnal migration, the "
                   "expected passage and the wind farms.",
        "cap_history": "<b>Record, {season}.</b> Lines: the mean direction of the passage at {n} radar stations "
                       "({nights} nights with a vector; a radar renewed on the same site counts as one station, and the "
                       "Azores and the Canaries are off the map). Colour: the season's mean passage the model computes at "
                       "each wind zone and city. Circles: wind farms, redder the more passage they get on average.",
        "cap_forecast": "<b>Night of {night}.</b> Colour: the passage Sub Nocte forecasts. Lines: the usual "
                        "direction for these dates (nights within ±{window} days, every year), not a heading forecast. "
                        "<b>{stop}</b> wind zones where stopping is suggested ({mw} MW).",
        "legend_ramp": "bird passage: little → much",
        "legend_line": "flight direction (sharper, steadier)",
        "legend_station": "radar and its mean direction",
        "legend_size": "size = MW",
        "legend_exposure": "wind farm: mean passage of the season",
        "read": "How to read it: lines and particles go where the birds fly, and are sharper the more the "
                "direction repeats night after night. Particles gather where more passage is expected. Circles "
                "are the OpenStreetMap wind zones (half-degree cells, about 55 × 42 km).",
        "noscript": "The map needs JavaScript. The routes table and the method below read without it.",
        "in_season": "In {season}",
        "around": "Around this date",
        "station_html": "<h3>{name}</h3><p><small>radar · {radars}</small></p><p><b>{when}</b> the birds fly "
                        "<b>{dir}</b> ({heading}°), {word} ({r}), at {speed} m/s over the ground and about {alt} m "
                        "above sea level on average.</p><p>{nights} nights with a vector, {years}. The heaviest 10% "
                        "of nights carry {top} of the passage. A heavy night (90th percentile: one only one night in "
                        "ten exceeds) is about {p90} birds "
                        "per kilometre of front <small>(indicative: it depends on the radar calibration)</small>.</p>",
        "country": {"ES": "Spain", "PT": "Portugal", "FR": "France"},
        "zone_head": "<h3>{place}</h3><p><small>{zone} · {country}</small><br>{turbines} turbines · {mw} MW in "
                     "OpenStreetMap</p>@@N@@",
        "zone_route": "<b>Route in {season}:</b> towards {dir}, {word} ({r}); the nearest radar with a vector is "
                      "{station}, {km} km away.",
        "zone_no_route": "<b>Route in {season}:</b> no radar with a vector close enough; no data.",
        "zone_rank": "By mean forecast passage, it is zone {rank} of {n}.",
        "zone_check": "<b>Does it work here?</b> Against the {radar} radar ({km} km away), over {nights} nights, "
                      "forecast and measurement rank the nights with a correlation of {rho}.",
        "zone_check_vh": " On very high nights the radar measured heavy passage {busy} of the time (by chance, "
                         "{chance}).",
        "zone_no_check": "<b>Does it work here?</b> No radar within 75 km to check it.",
        "above": "above the {p}th percentile of its own record",
        "below": "below the median of its own record",
        "zone_night": "<p><b>{night}:</b> {level} passage, {rel}. Wind at 100 m: {wind} m/s; the zone would "
                      "produce {frac} of its capacity, so stopping is {cost}.</p><p class='advice'>Suggestion: "
                      "<b>{advice}</b>. {why}</p>",
        "cost": {"cheap": "cheap", "moderate": "moderate", "expensive": "expensive"},
        "why": {"stop": "Heavy passage and little wind: stopping costs little and protects one of the few nights "
                        "that carry the migration.",
                "stop at peak hours": "Heavy passage, but with this wind stopping all night costs: the busiest "
                                      "hours are enough.",
                "watch": "High passage, or very high with strong wind: watch (radar, observers), without stopping "
                         "by default.",
                "run": "Normal passage for the date: nothing to do."},
        "h_why": "Why stop these wind farms, and only on a few nights",
        "sub_why": "Four figures, all computed from the data on this page.",
        "why_front_h": "A broad front that crosses everything",
        "why_front": "In autumn, {sw} of the {n} radar stations on the map see the passage heading between south "
                     "and south-west, {steady} of them with a steadiness of 0.7 or more. It is not a narrow "
                     "corridor: it is a river of birds hundreds of kilometres wide sweeping France and Iberia "
                     "towards the Strait. Every wind farm along it is in its way.",
        "why_few_h": "A few nights decide it",
        "why_few": "At the median station, the heaviest 10% of nights carry {top} of the whole season's passage. "
                   "Stopping on those nights protects a lot; stopping on the rest, little.",
        "why_cheap_h": "And they tend to be calm nights",
        "why_cheap": "Tested on 2021-2026 at the {zones} zones in Spain and Portugal, the rule would have stopped {nights} nights per season "
                     "and zone, for {lost} of the night output; stopping on every very high night would cost "
                     "{all}. Measured with the forecast itself, which flattens the peaks, it covers {covered} of the "
                     "predicted passage.",
        "why_right_h": "The radar confirms the chosen nights",
        "why_right": "On the nights the rule says stop, the nearest radar measured heavy passage {busy} of the "
                     "time; by chance it would be {chance}. That is {lift} times more.",
        "why_more": "The forecast per zone, night by night, in a table and with the rule explained: "
                    "<a href='{wind}'>wind farms</a>; the rule tested since 2021: <a href='{check}'>verification</a>.",
        "h_table": "The routes, station by station",
        "sub_table": "What the white arrows draw, with all their figures.",
        "table_summary": "Show the table: direction, steadiness, speed, altitude and concentration",
        "table_cols": ["station", "season", "years", "nights", "direction", "steadiness", "m/s", "altitude (m)",
                       "heaviest 10%"],
        "table_note": "Steadiness: 1 if every night flies the same way, 0 if they cancel out. Speed over the "
                      "ground (wind included). Mean altitude above sea level, weighted by traffic. Last column: "
                      "share of the passage carried by the heaviest 10% of nights.",
        "h_method": "How it is computed",
        "method": [
            ("From echo to flight vector",
             "Each radar profile (computed with vol2bird, the program that sorts bird echoes from rain and "
             "insects, every 5 to 15 minutes, and published openly by Aloft) gives, in 200 m layers from 200 m to 3 km, the "
             "density of birds and their ground speed towards the east and the north. Density × speed × layer "
             "depth × time, summed over the night, is the <b>traffic</b>: how many birds cross each kilometre of "
             "a front across their flight. Its direction is that night's."),
            ("Which nights count",
             "Passage months (March to May, August to November) in which the radar published vectors. A night "
             "counts if at least {vec} of its density carries a vector, if the radar saw {mins} minutes or more "
             "of it and if the ground speed stays under {speed} m/s: faster is usually rain or an echo carried by "
             "the wind, not birds."),
            ("From nights to a route",
             "Per station and season, the traffic vectors of all its nights are added. The direction of the sum is "
             "the route; its <b>steadiness</b> (length of the sum ÷ sum of the lengths, 0 to 1) says whether the "
             "nights agree. For the direction no night weighs more than the {cap}th percentile of its station, so "
             "a single huge night cannot turn the arrow. It takes {min_n} nights. Old and renewed radars on one "
             "site are one station, each on its own scale."),
            ("From radar to map",
             "The lines do not come from a model: they are a smoothing between radars (a {sigma} km Gaussian "
             "kernel on a {grid}° grid), drawn fully up to {fade0} km from the nearest radar and gone at {fade1} "
             "km. Where there is no radar, there is no line."),
            ("The coming nights",
             "In «Coming nights» the direction is the usual one for the date (nights within ±{window} days, every "
             "year) and the colour is the Sub Nocte forecast at each wind zone and city. In the record, the "
             "colour is the season mean the same model computes from the 2021-2026 weather."),
            ("Why stop here",
             "Tap a wind farm: the night's level (relative to its own record), the forecast wind at 100 m and what "
             "stopping would cost, the route overhead, its rank among the zones by mean passage, and how well the "
             "model does against the nearest radar."),
        ],
        "h_limits": "What this map does not say",
        "limits": [
            "<b>Height.</b> The radar measures from about 200 m to 3 km; the blades sweep 30 to 200 m above the "
            "ground. The route is the air column's, not the rotor height's; on ridges, where the farms stand at "
            "800-1,500 m, the two bands come closer.",
            "<b>Track, not heading.</b> It includes wind drift: it is where they pass, not where they point.",
            "<b>A broad front, not corridors.</b> Nocturnal passerine migration does not follow a narrow "
            "corridor; the lines give the overall sense of the flow, not a border outside which no bird passes.",
            "<b>Gaps in time.</b> The renewed AEMET radars and the French ones since 2021 hardly publish a vector "
            "on Aloft: the Spanish route rests mostly on 2018-2020 and the French one on 2016-2022. Portugal, "
            "2019-2026.",
            "<b>Gaps in space.</b> Far from the radars there is no data and the map fades out instead of making "
            "it up. The Azores and the Canaries are off the map.",
            "<b>The amount is indicative.</b> Bird numbers depend on each radar's calibration and compare poorly "
            "between radars; the direction does not depend on it.",
            "<b>Not all the victims.</b> The documented mortality at Spanish wind farms is mostly diurnal raptors "
            "and soaring birds, and bats; this is the nocturnal migration.",
        ],
        "h_sources": "Sources",
        "sources": "Bird vertical profiles and flight vectors: <a href='https://aloftdata.eu'>Aloft</a> (CC0), "
                   "the open European archive of bird profiles, computed with vol2bird on the AEMET, IPMA and "
                   "Météo-France radars (OPERA, the network that pools Europe's weather radars). Wind farms: "
                   "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors (ODbL). "
                   "Weather: <a href='https://open-meteo.com'>Open-Meteo</a> (CC BY 4.0) and Copernicus ERA5 (the "
                   "hour-by-hour reconstruction of past weather). "
                   "Coasts and borders: <a href='https://www.naturalearthdata.com'>Natural Earth</a> (public "
                   "domain). Method: Dokter et al. (2011) for vol2bird; Horton et al. (2021) for the concentration "
                   "of the passage on a few nights.",
        "code": "All the code and derived data (each night's traffic in "
                "<code>data/routes/flight_nights.parquet</code>) live in the <a href='{repo}'>repository</a>.",
    },
}
