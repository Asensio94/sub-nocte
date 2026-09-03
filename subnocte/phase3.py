"""Phase 3: reports of the per-city forecast and of the light-exposure ranking."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .report import embed_images

LEVEL_COLOR = {"low": "#e8eaed", "moderate": "#ffd98e", "high": "#f08c1e", "very high": "#b32d1f",
               "no threshold": "#ffffff"}
LEVEL_ORDER = ["low", "moderate", "high", "very high"]
COUNTRY = {"ES": "Spain", "PT": "Portugal", "FR": "France"}
STYLE = ("<style>body{font:15px/1.55 system-ui;max-width:1100px;margin:2em auto;padding:0 1em;color:#222}"
         "table{border-collapse:collapse;font-size:13px}td,th{border:1px solid #ddd;padding:3px 8px;text-align:right}"
         "th{background:#f4f4f4}td:first-child,th:first-child{text-align:left}img{max-width:100%}"
         ".k{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px;margin:1em 0}"
         ".k div{background:#f7f7f7;padding:8px 12px;border-radius:6px}.k b{display:block;font-size:20px}"
         ".n{display:inline-block;padding:1px 7px;border-radius:4px;font-size:12px}</style>")


def _city_order(fc: pd.DataFrame) -> list[str]:
    """Cities from most to least alert, so the calendar reads from top to bottom."""
    weight = {n: i for i, n in enumerate(LEVEL_ORDER)}
    s = fc.assign(w=fc["level"].map(weight).fillna(0)).groupby("city")["w"].mean()
    return list(s.sort_values(ascending=False).index)


def figures(fc: pd.DataFrame, thresholds: pd.DataFrame, out_dir: Path) -> list[Path]:
    figs = []
    cities = _city_order(fc)
    nights = sorted(fc["night"].unique())

    # 1) alert calendar: one row per city, one column per night
    p = out_dir / "phase3_calendar.png"
    m = np.full((len(cities), len(nights)), -1)
    for i, c in enumerate(cities):
        g = fc[fc["city"] == c].set_index("night")
        for j, n in enumerate(nights):
            if n in g.index:
                m[i, j] = LEVEL_ORDER.index(g.loc[n, "level"]) if g.loc[n, "level"] in LEVEL_ORDER else -1
    from matplotlib.colors import BoundaryNorm, ListedColormap
    cmap = ListedColormap(["#ffffff"] + [LEVEL_COLOR[n] for n in LEVEL_ORDER])
    fig, ax = plt.subplots(figsize=(1.1 * len(nights) + 3.5, 0.34 * len(cities) + 1.6))
    ax.pcolormesh(m, cmap=cmap, norm=BoundaryNorm(range(-1, 5), cmap.N), edgecolors="w", linewidth=1.2)
    ax.set_yticks(np.arange(len(cities)) + 0.5, cities, fontsize=9)
    ax.set_xticks(np.arange(len(nights)) + 0.5, [pd.Timestamp(n).strftime("%a %d/%m") for n in nights], fontsize=9)
    ax.invert_yaxis(); ax.set_title("Alert per city and night (level relative to each city's own record)")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor=LEVEL_COLOR[n], edgecolor="#bbb", label=n) for n in LEVEL_ORDER],
              loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=4, frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(p, dpi=130, bbox_inches="tight"); plt.close(fig); figs.append(p)

    # 2) forecast intensity night by night in the cities with the most alert, with their own thresholds
    p = out_dir / "phase3_series.png"
    ex = cities[:6]
    fig, axes = plt.subplots(len(ex), 1, figsize=(9, 1.7 * len(ex)), squeeze=False, sharex=True)
    u = thresholds.set_index(["city", "season"])
    for ax, c in zip(axes.flat, ex):
        g = fc[fc["city"] == c].sort_values("night")
        ax.plot(g["night"], g["pred"].clip(lower=0) ** 3, color="#333", marker="o", ms=4, lw=1.4)
        key = (c, g["season"].mode().iat[0])
        if key in u.index:
            for q, col, txt in ((75, "#f08c1e", "high"), (90, "#b32d1f", "very high")):
                ax.axhline(max(u.loc[key, f"pred_q{q}"], 0) ** 3, color=col, ls=":", lw=1, label=txt)
            ax.legend(fontsize=7, loc="upper right", ncol=2)
        ax.set_ylabel("birds/km²", fontsize=8); ax.set_title(c, fontsize=10, loc="left")
        ax.tick_params(labelsize=8)
    fig.autofmt_xdate()
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)

    # 3) simple map: each city at its position, coloured by the highest alert of the coming days
    p = out_dir / "phase3_map.png"
    worst = (fc.assign(w=fc["level"].map({n: i for i, n in enumerate(LEVEL_ORDER)}).fillna(0))
             .sort_values("w").groupby("city").last().reset_index())
    fig, ax = plt.subplots(figsize=(7, 6.4))
    ax.scatter(worst["lon"], worst["lat"], s=170, c=[LEVEL_COLOR.get(n, "#eee") for n in worst["level"]],
               edgecolors="#555", linewidths=0.8, zorder=3)
    for r in worst.itertuples(index=False):
        ax.annotate(r.city, (r.lon, r.lat), fontsize=7.5, xytext=(0, 9), textcoords="offset points", ha="center")
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude"); ax.grid(alpha=0.25)
    ax.set_title("Highest alert forecast in the period")
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)
    return figs


def _forecast_table(fc: pd.DataFrame) -> str:
    t = pd.DataFrame({
        "city": fc["city"],
        "country": fc["country"].map(COUNTRY).fillna(fc["country"]),
        "date": fc["night"].dt.strftime("%a %d/%m"),
        "forecast birds/km²": (fc["pred"].clip(lower=0) ** 3).map("{:.0f}".format),
        "probability of heavy passage": fc["p_alert"].map("{:.2f}".format),
        "alert": [f"<span class='n' style='background:{LEVEL_COLOR.get(n, '#eee')}'>{n}</span>"
                  for n in fc["level"]],
    })
    return t.to_html(index=False, escape=False)


def write_report(fc: pd.DataFrame, thresholds: pd.DataFrame, figs: list[Path], out: Path) -> None:
    nights = sorted(fc["night"].unique())
    alerted = fc[fc["level"].isin(["high", "very high"])]
    summary = {
        "cities": fc["city"].nunique(),
        "nights forecast": len(nights),
        "first night": pd.Timestamp(nights[0]).strftime("%d/%m/%Y"),
        "last night": pd.Timestamp(nights[-1]).strftime("%d/%m/%Y"),
        "high or very high alerts": len(alerted),
        "cities with any alert": alerted["city"].nunique(),
    }
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Phase 3 · per-city forecast</title>", STYLE,
        "<h1>Phase 3 · nocturnal migration forecast per city</h1>",
        "<p>Forecast of the <b>density of birds in nocturnal flight</b> over each city for the coming nights, made "
        "from the weather forecast alone: there is no radar in any of these cities. Both models are the phase 2 ones "
        "retrained <b>without the local climatology</b>, which is the configuration validated by leaving whole radars "
        "out of the training: in that scenario they captured 34 % of the heavy-passage nights against the 10 % that "
        "chance would give, with a median area under the curve of 0.77.</p>",
        "<p><b>What the alert level means.</b> The model gives a continuous number, and what counts as a lot in "
        "Sevilla is not the same as in Bilbao. For each city the model has been run over the weather archive from "
        "2021 onwards at its own coordinates, and the levels are cut at the percentiles of <i>its</i> distribution: "
        "<b>moderate</b> above the median, <b>high</b> above the 75th percentile and <b>very high</b> above the 90th "
        "percentile, that is the busiest night in every ten. That way the alert means the same thing everywhere: "
        "«tonight far more is passing than is normal here».</p>",
        "<div class='k'>" + "".join(f"<div>{k}<b>{v}</b></div>" for k, v in summary.items()) + "</div>",
    ]
    for f in figs:
        parts.append(f"<p><img src='{f.name}'></p>")
    parts += [
        "<h2>Nights with a high or very high alert</h2>",
        _forecast_table(alerted.sort_values(["night", "city"])) if len(alerted) else
        "<p>No city goes above the 75th percentile of its own record in this period.</p>",
        "<h2>Full forecast</h2>", _forecast_table(fc.sort_values(["city", "night"])),
        "<h2>Each city's thresholds</h2>",
        "<p>Computed over the predictions of the 2021-today weather archive at each city's point. The birds/km² are "
        "the cuts of the intensity model; the probability is the cut of the heavy-passage classifier, which is what "
        "decides the alert.</p>",
        (thresholds.assign(**{"birds/km² high": (thresholds["pred_q75"].clip(lower=0) ** 3).map("{:.0f}".format),
                              "birds/km² very high": (thresholds["pred_q90"].clip(lower=0) ** 3).map("{:.0f}".format),
                              "prob. high": thresholds["alert_q75"].map("{:.2f}".format),
                              "prob. very high": thresholds["alert_q90"].map("{:.2f}".format)})
         [["city", "season", "nights", "birds/km² high", "birds/km² very high", "prob. high", "prob. very high"]]
         .to_html(index=False)),
        "<h2>Limitations</h2><ul>"
        "<li>The forecast degrades with the days: the first night runs on an almost closed analysis and the seventh "
        "on a six-day forecast. The model was trained on analyses and short-range forecasts, so the distant nights "
        "are worse than the validation figures suggest.</li>"
        "<li>None of these cities has a radar within useful range, so <b>there is nothing to compare the forecast "
        "against the next day</b>. The phase 2 validation is the only guarantee, and it was done precisely by "
        "leaving whole radars out to imitate this situation.</li>"
        "<li>The forecast density is that of the air volume over the city, not the number of birds that approach the "
        "lights. The exposure piece is missing, and that is the artificial-light ranking.</li>"
        "<li>Without the flight speed from the radar processor, part of the autumn density in the south may be insect "
        "and not bird. It is the same limitation as in phase 2.</li></ul>",
    ]
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    embed_images(out)


# ---------------------------------------------------------------- light-exposure ranking

def ranking_figures(rk: pd.DataFrame, out_dir: Path) -> list[Path]:
    p = out_dir / "exposure_ranking.png"
    seasons = list(rk["season"].unique())
    fig, axes = plt.subplots(1, len(seasons), figsize=(6.2 * len(seasons), 6.4), squeeze=False)
    col = {"ES": "#c0392b", "PT": "#27ae60", "FR": "#2980b9"}
    for ax, t in zip(axes.flat, seasons):
        g = rk[rk["season"] == t].nlargest(20, "exposure_peaks")[::-1]
        ax.barh(g["city"], g["exposure_peaks"], color=[col.get(p_, "#888") for p_ in g["country"]])
        ax.set_xlabel("exposure index (100 = maximum)"); ax.set_title(f"{t}", fontsize=11)
        ax.tick_params(labelsize=9)
    fig.suptitle("Exposure of the nocturnal passage to artificial light: city light × forecast birds on the peak nights",
                 fontsize=11)
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig)

    p2 = out_dir / "exposure_scatter.png"
    fig, ax = plt.subplots(figsize=(7, 6))
    g = rk[rk["season"] == seasons[0]]
    ax.scatter(g["light_mean"], g["vid_peaks"], s=60, c=[col.get(p_, "#888") for p_ in g["country"]],
               edgecolors="#444")
    for r in g.itertuples(index=False):
        ax.annotate(r.city, (r.light_mean, r.vid_peaks), fontsize=7.5, xytext=(0, 7),
                    textcoords="offset points", ha="center")
    ax.set_xscale("log"); ax.set_xlabel("artificial sky brightness (mcd/m², logarithmic scale)")
    ax.set_ylabel("forecast birds/km² on the ten busiest nights")
    ax.set_title(f"The two pieces of the risk ({seasons[0]})"); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(p2, dpi=130); plt.close(fig)
    return [p, p2]


def write_ranking(rk: pd.DataFrame, figs: list[Path], out: Path) -> None:
    from .lights import NATURAL_BRIGHTNESS, RADIUS_KM

    t = pd.DataFrame({
        "city": rk["city"],
        "country": rk["country"].map(COUNTRY).fillna(rk["country"]),
        "season": rk["season"],
        "artificial brightness (mcd/m²)": rk["light_mean"].map("{:.2f}".format),
        "times the natural sky": rk["times_natural"].map("{:.0f}".format),
        "mean birds/km²": rk["vid_mean"].map("{:.0f}".format),
        "birds/km² on peak nights": rk["vid_peaks"].map("{:.0f}".format),
        "exposure (mean)": rk["exposure_mean"].map("{:.1f}".format),
        "exposure (peaks)": rk["exposure_peaks"].map("{:.1f}".format),
        "_sort": rk["exposure_peaks"],
    })
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Light-exposure ranking</title>", STYLE,
        "<h1>Exposure ranking: where many birds and much light coincide</h1>",
        "<p>A lights-out alert is only useful where many birds pass <i>and</i> many lights are on. This ranking "
        "multiplies the two, following the method with which Horton et al. (2019) ranked the cities of the United "
        "States.</p>",
        "<p><b>The light</b> is the artificial component of the zenith night-sky brightness according to the New "
        f"World Atlas (Falchi et al., 2016), averaged over a disc of {RADIUS_KM:.0f} km around the city centre. The "
        f"natural sky sits at {NATURAL_BRIGHTNESS} mcd/m²: the «times the natural sky» column says how many times "
        "brighter that city's sky is than one without artificial light.</p>",
        "<p><b>The birds</b> come from the phase 3 model run over the weather archive from 2021 onwards at each "
        "city's coordinates: the mean density of the season and the mean of its ten busiest nights, which is when "
        "the alert matters. The index is normalised to 100 in the most exposed city.</p>",
    ]
    for f in figs:
        parts.append(f"<p><img src='{f.name}'></p>")
    for season in t["season"].unique():
        g = t[t["season"] == season].sort_values("_sort", ascending=False).drop(columns="_sort")
        parts += [f"<h2>{season.capitalize()}</h2>", g.to_html(index=False)]
    parts += [
        "<h2>How to read it and what it is not</h2><ul>"
        "<li>The atlas measures the brightness of the sky <b>seen from the ground</b>, which includes light "
        "scattered by the atmosphere and light arriving from neighbouring towns. What matters to a bird flying at a "
        "thousand metres is the radiance the city emits <b>upwards</b>, which the VIIRS satellites measure. For "
        "ranking cities the two measures go hand in hand, but they are not the same quantity.</li>"
        "<li>The light data are from <b>2015</b>. In ten years the switch to diode lighting has raised the blue "
        "component, to which birds are more sensitive, and changed the intensity in many cities.</li>"
        "<li>The 10 km disc is the same rule for every city, not the municipal boundary: in a large metropolitan "
        "area it clips, and in a small city it takes in dark countryside.</li>"
        "<li>The forecast densities are <b>compressed in the tail</b>: the intensity model is a mean regression, so "
        "its peak nights fall short of those observed by radar (predicted: 99th percentile of about 8 birds/km²; "
        "observed at the radars: about 30). For <i>ranking</i> cities it does not matter, because the bias is the "
        "same everywhere, but the figures must not be read as absolute densities.</li>"
        "<li><b>The light drives the order.</b> Between the brightest and the dimmest city of the pilot there is a "
        "factor of 3-4, whereas in forecast birds there is barely a factor of 2. The ranking is mostly saying where "
        "more light is on, qualified by the passage; they are not two factors of similar weight.</li>"
        "<li>The index is not a measure of mortality. It says where the passage and the light coincide, which is the "
        "necessary condition; what happens also depends on the flight altitude, the fog, the type of luminaire and "
        "the presence of tall glazed buildings.</li>"
        "<li>The atlas licence <b>forbids redistributing the files</b>. This report publishes derived results citing "
        "both mandatory references; the raster is not uploaded anywhere. For a public version it is better to "
        "replace it with the VIIRS radiance, which is public domain and annual.</li></ul>",
        "<h2>Citations</h2><p>Falchi F. et al. (2016). <i>The new world atlas of artificial night sky brightness</i>. "
        "Science Advances 2(6):e1600377. — Falchi F. et al. (2016). <i>Supplement to: The New World Atlas of "
        "Artificial Night Sky Brightness</i>. GFZ Data Services, doi:10.5880/GFZ.1.4.2016.001. — Horton K. G. et al. "
        "(2019). <i>Bright lights in the big cities: migratory birds' exposure to artificial light</i>. Frontiers in "
        "Ecology and the Environment 17(4):209-214.</p>",
    ]
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    embed_images(out)
