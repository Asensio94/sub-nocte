"""Report of the wind-farm forecast: which zones, which nights, and what stopping would cost."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .phase3 import COUNTRY, LEVEL_COLOR, LEVEL_ORDER, STYLE
from .report import embed_images
from .wind import CELL_DEG, CHEAP, CUT_IN, CUT_OUT, EXPENSIVE, MIN_TURBINES, RATED

ADVICE_ORDER = ["run", "watch", "stop at peak hours", "stop"]
ADVICE_COLOR = {"run": "#e8eaed", "watch": "#ffd98e", "stop at peak hours": "#f08c1e", "stop": "#b32d1f"}


def _zone_label(r) -> str:
    return f"{r.place or r.zone} ({r.turbines})"


def figures(fc: pd.DataFrame, out_dir: Path) -> list[Path]:
    figs = []
    nights = sorted(fc["night"].unique())
    weight = {a: i for i, a in enumerate(ADVICE_ORDER)}
    worst = (fc.assign(w=fc["advice"].map(weight)).groupby("zone")
             .agg(w=("w", "max"), turbines=("turbines", "first"), lat=("lat", "first"), lon=("lon", "first"),
                  place=("place", "first")))

    # 1) map: one circle per zone, sized by its turbines and coloured by the strongest suggestion of the week
    p = out_dir / "wind_map.png"
    fig, ax = plt.subplots(figsize=(8, 6.5))
    for a in ADVICE_ORDER:
        g = worst[worst["w"] == weight[a]]
        ax.scatter(g["lon"], g["lat"], s=g["turbines"] * 0.9 + 8, c=ADVICE_COLOR[a], edgecolors="#555",
                   linewidths=0.5, label=a, alpha=0.9)
    ax.set_xlim(-10, 4.5); ax.set_ylim(35.8, 44); ax.set_aspect(1 / np.cos(np.radians(40)))
    ax.set_title("Wind zones: strongest suggestion over the forecast nights\n(circle size = turbines in OSM)")
    ax.legend(loc="lower right", fontsize=9, frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(p, dpi=130, bbox_inches="tight"); plt.close(fig); figs.append(p)

    # 2) calendar of the zones with any suggestion above "run", or the 25 largest if none
    hot = worst[worst["w"] > 0].sort_values(["w", "turbines"], ascending=False)
    show = (hot if len(hot) else worst.sort_values("turbines", ascending=False)).head(30)
    p = out_dir / "wind_calendar.png"
    m = np.full((len(show), len(nights)), -1)
    for i, z in enumerate(show.index):
        g = fc[fc["zone"] == z].set_index("night")
        for j, n in enumerate(nights):
            if n in g.index:
                m[i, j] = weight[g.loc[n, "advice"]]
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch
    cmap = ListedColormap(["#ffffff"] + [ADVICE_COLOR[a] for a in ADVICE_ORDER])
    fig, ax = plt.subplots(figsize=(1.1 * len(nights) + 4, 0.34 * len(show) + 1.6))
    ax.pcolormesh(m, cmap=cmap, norm=BoundaryNorm(range(-1, 5), cmap.N), edgecolors="w", linewidth=1.2)
    ax.set_yticks(np.arange(len(show)) + 0.5, [_zone_label(r) for r in show.itertuples()], fontsize=9)
    ax.set_xticks(np.arange(len(nights)) + 0.5, [pd.Timestamp(n).strftime("%a %d/%m") for n in nights], fontsize=9)
    ax.invert_yaxis(); ax.set_title("Suggestion per wind zone and night")
    ax.legend(handles=[Patch(facecolor=ADVICE_COLOR[a], edgecolor="#bbb", label=a) for a in ADVICE_ORDER],
              loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=4, frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(p, dpi=130, bbox_inches="tight"); plt.close(fig); figs.append(p)

    # 3) the two halves of the decision: alert percentile against the night output
    p = out_dir / "wind_tradeoff.png"
    fig, ax = plt.subplots(figsize=(7.5, 5))
    for a in ADVICE_ORDER:
        g = fc[fc["advice"] == a]
        jitter = np.random.default_rng(0).uniform(-0.03, 0.03, len(g))
        ax.scatter(g["power_frac"], g["percentile"].fillna(0) + jitter, s=14, c=ADVICE_COLOR[a],
                   edgecolors="#666", linewidths=0.3, label=a)
    for x in (CHEAP, EXPENSIVE):
        ax.axvline(x, color="#999", ls=":", lw=1)
    ax.set_xlabel("Share of rated power the zone would produce that night (generic curve)")
    ax.set_ylabel("Alert percentile in the zone's own record")
    ax.set_yticks([0, 0.5, 0.75, 0.9], ["<P50", "P50", "P75", "P90"])
    ax.set_title("Each dot is a zone-night: migration against the cost of stopping")
    ax.legend(fontsize=9, frameon=False, loc="lower right")
    fig.tight_layout(); fig.savefig(p, dpi=130, bbox_inches="tight"); plt.close(fig); figs.append(p)
    return figs


def _table(fc: pd.DataFrame) -> str:
    rows = ["<table><tr><th>Zone</th><th>Country</th><th>Turbines</th><th>MW in OSM</th><th>Night</th>"
            "<th>Level</th><th>Wind 100 m (m/s)</th><th>Night output</th><th>Cost of stopping</th>"
            "<th>Suggestion</th></tr>"]
    for r in fc.itertuples():
        lv, ad = LEVEL_COLOR.get(r.level, "#fff"), ADVICE_COLOR.get(r.advice, "#fff")
        rows.append(
            f"<tr><td>{r.place or ''} <small>{r.zone}</small></td><td>{COUNTRY.get(r.country, r.country)}</td>"
            f"<td>{r.turbines}</td><td>{r.power_mw:,.0f}</td><td>{pd.Timestamp(r.night):%a %d/%m}</td>"
            f"<td><span class='n' style='background:{lv}'>{r.level}</span></td>"
            f"<td>{r.wind100_mean:.1f}</td><td>{r.power_frac:.0%}</td><td>{r.cost}</td>"
            f"<td><span class='n' style='background:{ad}'>{r.advice}</span></td></tr>")
    return "".join(rows) + "</table>"


def write_report(fc: pd.DataFrame, thresholds: pd.DataFrame, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    figs = figures(fc, out.parent)
    nights = sorted(fc["night"].unique())
    stop = fc[fc["advice"].isin(["stop", "stop at peak hours"])]
    summary = {
        "wind zones": fc["zone"].nunique(),
        "turbines covered": f"{fc.groupby('zone')['turbines'].first().sum():,}",
        "nights forecast": f"{pd.Timestamp(nights[0]):%d/%m} – {pd.Timestamp(nights[-1]):%d/%m}",
        "zone-nights with high or very high alert": int(fc["level"].isin(["high", "very high"]).sum()),
        "of them cheap to stop": int((fc["level"].isin(["high", "very high"]) & (fc["cost"] == "cheap")).sum()),
        "zone-nights where stopping is suggested": len(stop),
    }
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Wind farms · nightly migration forecast</title>", STYLE,
        "<h1>Wind farms · nightly migration forecast</h1>",
        "<p>In the Netherlands the offshore wind farms are stopped on the nights of heavy migration, with a forecast "
        "built on the weather radars. In Spain and Portugal nothing like it is in place. This page points the "
        "per-city forecast of phase 3, which works at any point without a radar, at the <b>wind turbines</b>, and "
        "adds the other half of the decision: <b>what stopping would cost</b> that night.</p>",
        f"<p><b>Zones.</b> The turbines mapped in OpenStreetMap are grouped into cells of {CELL_DEG}° "
        f"(about 55 × 42 km); a cell with at least {MIN_TURBINES} turbines is a wind zone, with its forecast point at "
        "the centroid of its turbines. The alert level is cut, as for the cities, on the percentiles of the zone's own "
        "record around the same date: <b>high</b> is above its 75th percentile and <b>very high</b> above its 90th.</p>",
        f"<p><b>Cost of stopping.</b> The forecast wind at 100 m over the night hours, through a generic power curve "
        f"(nothing below {CUT_IN:.0f} m/s, rated power from {RATED:.0f} m/s, cut-out at {CUT_OUT:.0f} m/s), gives the "
        f"share of rated power the zone would produce. Below {CHEAP:.0%} stopping is <i>cheap</i>; from "
        f"{EXPENSIVE:.0%} it is <i>expensive</i>. The two halves cross in a fixed table: very high and cheap → stop; very "
        "high and moderate → stop at the peak hours; very high and expensive, or high → watch; anything below → run. "
        "It is a way of ranking nights, not an operating order.</p>",
        "<p><b>Why so strict.</b> Over the 2021-2026 seasons, stopping from the 75th percentile would have meant 21 "
        "nights per season and zone and 13.5 % of the night output. With this table it is about 7 nights and 2 % of "
        "the output, which still covers about 11 % of the migration the model predicts. It comes out this cheap "
        "because the heavy nights tend to be calm ones.</p>",
        "<div class='k'>" + "".join(f"<div>{k}<b>{v}</b></div>" for k, v in summary.items()) + "</div>",
    ]
    parts += [f"<p><img src='{f.name}'></p>" for f in figs]
    parts += [
        "<h2>Zone-nights where stopping is suggested</h2>",
        _table(stop.sort_values(["night", "turbines"], ascending=[True, False])) if len(stop) else
        "<p>No zone reaches a suggestion to stop in this period.</p>",
        "<h2>Full forecast</h2>",
        _table(fc.sort_values(["zone", "night"])),
        "<h2>Limitations</h2><ul>"
        "<li><b>Not at rotor height.</b> The forecast is the density of the whole air column the radars see, from "
        "about 200 m to 3 km. Turbines sweep from about 30 to 200 m above the ground, a layer weather radars hardly "
        "see. On ridges the turbines stand 800–1500 m above sea level, inside the band the radars do cover; that is the "
        "next step (altitude per zone), not yet done.</li>"
        "<li><b>Not the main known victims.</b> The documented wind-farm mortality in Spain is mostly diurnal soaring "
        "birds (vultures, raptors) and bats. Neither is covered here: this is nocturnal passerine migration.</li>"
        "<li><b>The radars behind the model.</b> The model was validated leaving whole radars out (AUC 0.77 across "
        "Europe, 0.74 in Spain), but the renovated AEMET radars do worse (0.55–0.66). Off the migration seasons there "
        "is no threshold and no suggestion.</li>"
        "<li><b>Generic curve, OSM inventory.</b> The night output comes from a generic curve and the forecast wind at "
        "100 m, not from the real machines. Rated power and rotor size are only tagged on part of the turbines, and "
        "the inventory is what OpenStreetMap contributors have mapped.</li></ul>",
        "<p><small>Turbines © OpenStreetMap contributors (ODbL). Weather: Open-Meteo. Radar profiles: ENRAM / Aloft "
        "(CC0).</small></p>",
    ]
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    embed_images(out)
