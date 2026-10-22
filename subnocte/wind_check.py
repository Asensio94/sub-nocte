"""Hindcast of the wind-farm rule and its check against the nearest weather radar.

Two questions, both on the 2021-2026 ERA5 archive of each zone:

1. **What would the rule have cost?** The model is run over every past night, the level comes from the zone's own
   thresholds and the advice from the same decision table as the daily forecast. Per season and zone: nights the
   rule says to stop, share of the night output lost and share of the predicted migration on those nights.
2. **Were those nights really heavy?** The radar does not measure at the wind farm, but the nearest one says
   whether the night was busy in that region. Each zone within `MAX_KM` of a radar is paired with it and the
   night is placed in that radar's own record of the same years, as the city scorecard does.

The radar check uses reanalysis weather, not the forecast that would have been published, so it measures the
model and the rule, not the forecast error of the days ahead.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import scorecard as S
from . import wind as W

MAX_KM = 75      # beyond this the radar describes another stretch of sky
BUSY = 0.75      # top quarter of the radar's own record for the season, as in the scorecard
SEASONS = ("spring", "autumn")


def _km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin((p2 - p1) / 2) ** 2
         + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def levels(pred: pd.DataFrame, thresholds: pd.DataFrame) -> pd.DataFrame:
    """Level, cost and advice for every past zone-night, exactly as the daily forecast would give them."""
    from . import forecast as P

    x = P.apply_thresholds(pred, thresholds.rename(columns={"zone": "city"})).rename(columns={"radar": "zone"})
    x = x[x["season"].isin(SEASONS) & x["power_frac"].notna()].drop(columns=["city"])
    x["cost"] = x["power_frac"].map(W.stop_cost)
    x["advice"] = [W.advice(lv, c) for lv, c in zip(x["level"], x["cost"])]
    x["year"] = pd.to_datetime(x["night"]).dt.year
    return x


def hindcast(x: pd.DataFrame) -> pd.DataFrame:
    """Per year and season, averaged over zones: what stopping as the rule says would have meant."""
    rows = []
    for (year, season), g in x.groupby(["year", "season"]):
        zones = g["zone"].nunique()
        for rule, mask in (("stop", g["advice"] == "stop"),
                           ("stop + peak hours", g["advice"].isin(["stop", "stop at peak hours"])),
                           ("every very high night", g["level"] == "very high")):
            rows.append({"year": year, "season": season, "rule": rule, "zones": zones,
                         "nights_per_zone": mask.sum() / zones,
                         "output_lost": g.loc[mask, "power_frac"].sum() / g["power_frac"].sum(),
                         "migration_covered": g.loc[mask, "pred"].sum() / g["pred"].sum()})
    return pd.DataFrame(rows)


def overall(h: pd.DataFrame) -> pd.DataFrame:
    """The whole archive in one row per rule: nights are summed per season and zone, shares weighted by year."""
    return (h.groupby("rule", sort=False)
            .agg(seasons=("year", "size"), nights_per_zone=("nights_per_zone", "mean"),
                 output_lost=("output_lost", "mean"), migration_covered=("migration_covered", "mean"))
            .reset_index())


def pair_radars(zones: pd.DataFrame, nightly: pd.DataFrame) -> pd.DataFrame:
    """Nearest radar of each zone and its distance; zones farther than `MAX_KM` are left out."""
    radars = nightly.groupby("radar")[["lat", "lon"]].median().reset_index()
    rows = []
    for z in zones.itertuples():
        d = _km(z.lat, z.lon, radars["lat"].to_numpy(), radars["lon"].to_numpy())
        i = int(np.argmin(d))
        rows.append({"zone": z.zone, "radar": radars["radar"].iloc[i], "dist_km": float(d[i])})
    p = pd.DataFrame(rows)
    return p[p["dist_km"] <= MAX_KM]


def radar_check(x: pd.DataFrame, pairs: pd.DataFrame, nightly: pd.DataFrame) -> pd.DataFrame:
    """Every paired zone-night with where the radar's measured night sits in that radar's own record.

    The record is limited to the years of the hindcast: several radars measured on another scale before 2020
    (the median night of 2016 is five times today's), and against those years a recent night looks busier than
    it was. Within the same years a busy night is, by construction, one in four.
    """
    obs = nightly.copy()
    obs["night"] = pd.to_datetime(obs["night"])
    obs = obs[(obs["night"].dt.year >= int(x["year"].min())) & obs["radar"].isin(set(pairs["radar"]))]
    ref = obs[obs["coverage"] >= S.MIN_COVERAGE].copy()
    ref["doy"] = ref["night"].dt.dayofyear
    ref["season"] = S._season(ref["night"])
    ref = ref[ref["season"] != "off season"]
    measured = S.add_percentile(obs[["radar", "night", "vid_night", "coverage"]], ref)
    m = (x.merge(pairs, on="zone")
         .assign(night=lambda d: pd.to_datetime(d["night"]))
         .merge(measured[["radar", "night", "vid_night", "obs_pct", "ref_n"]], on=["radar", "night"]))
    return m[(m["ref_n"] >= S.MIN_REF) & m["obs_pct"].notna()]


def check_summary(m: pd.DataFrame) -> pd.DataFrame:
    """How often each level and each piece of advice fell on a night the radar found busy, against chance."""
    busy = m["obs_pct"] >= BUSY
    rows = [{"group": "all nights", "zone_nights": len(m), "busy": busy.mean()}]
    for lv in ("low", "moderate", "high", "very high"):
        k = m["level"] == lv
        rows.append({"group": f"level {lv}", "zone_nights": int(k.sum()), "busy": busy[k].mean()})
    for adv in ("stop", "stop at peak hours"):
        k = m["advice"] == adv
        rows.append({"group": f"advice {adv}", "zone_nights": int(k.sum()), "busy": busy[k].mean()})
    out = pd.DataFrame(rows)
    out["lift"] = out["busy"] / busy.mean()
    return out


def by_zone(m: pd.DataFrame) -> pd.DataFrame:
    """Per zone: its radar, how many nights the two share, and the rank correlation of forecast and measure."""
    rows = []
    for (zone, radar), g in m.groupby(["zone", "radar"]):
        vh = g["level"] == "very high"
        rows.append({"zone": zone, "radar": radar, "dist_km": g["dist_km"].iloc[0], "nights": len(g),
                     "rho": g["pred"].corr(g["vid_night"], method="spearman"),
                     "very_high_busy": (g.loc[vh, "obs_pct"] >= BUSY).mean() if vh.any() else np.nan})
    return pd.DataFrame(rows).sort_values("dist_km")


def _pct(v) -> str:
    return "—" if pd.isna(v) else f"{v:.1%}"


def figure(cs: pd.DataFrame, out_dir: Path) -> Path:
    """Share of busy radar nights per alert level, against the share by chance."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    from .phase3 import LEVEL_COLOR

    lv = cs[cs["group"].str.startswith("level ")]
    names = [g.removeprefix("level ") for g in lv["group"]]
    base = cs.loc[cs["group"] == "all nights", "busy"].iat[0]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(names, lv["busy"], color=[LEVEL_COLOR[n] for n in names], edgecolor="#555")
    ax.axhline(base, color="#333", ls="--", lw=1)
    ax.text(-0.4, base + 0.01, f"chance {base:.0%}", fontsize=9)
    for i, v in enumerate(lv["busy"]):
        ax.text(i, v + 0.01, f"{v:.0%}", ha="center", fontsize=9)
    ax.set_ylabel("nights the radar found busy")
    ax.set_ylim(0, max(0.8, lv["busy"].max() + 0.08))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("Alert level of the zone vs the nearest radar's night", fontsize=11)
    fig.tight_layout()
    f = out_dir / "wind_check_levels.png"
    fig.savefig(f, dpi=120)
    plt.close(fig)
    return f


def write_report(x: pd.DataFrame, h: pd.DataFrame, ov: pd.DataFrame, cs: pd.DataFrame, bz: pd.DataFrame,
                 zones: int, out: Path) -> None:
    from .phase3 import STYLE
    from .report import embed_images

    out.parent.mkdir(parents=True, exist_ok=True)
    fig = figure(cs, out.parent)
    nights = pd.to_datetime(x["night"])
    base = cs.loc[cs["group"] == "all nights", "busy"].iat[0]
    o = ov.set_index("rule")
    lo, hi = bz["dist_km"].min(), bz["dist_km"].max()
    summary = {
        "zones in the hindcast": f"{x['zone'].nunique()}",
        "zone-nights in season": f"{len(x):,}",
        "nights": f"{nights.min():%d/%m/%Y} – {nights.max():%d/%m/%Y}",
        "suggested stops per season and zone": f"{o.loc['stop', 'nights_per_zone']:.1f}",
        "night output lost": _pct(o.loc["stop", "output_lost"]),
        "predicted migration on those nights": _pct(o.loc["stop", "migration_covered"]),
        f"zones with a radar within {MAX_KM} km": f"{bz['zone'].nunique()} of {zones}",
        "very high nights the radar found busy": f"{_pct(cs.set_index('group').loc['level very high', 'busy'])} "
                                                 f"(chance {base:.0%})",
    }
    rules = list(ov["rule"])
    rows_h = []
    for (y, s), g in h.groupby(["year", "season"], sort=False):
        r = g.set_index("rule")
        rows_h.append(f"<tr><td>{y} {s}</td><td>{int(g['zones'].iat[0])}</td>"
                      + "".join(f"<td>{r.loc[k, 'nights_per_zone']:.1f}</td><td>{_pct(r.loc[k, 'output_lost'])}</td>"
                                for k in rules) + "</tr>")
    rows_o = "".join(f"<tr><td>{r.rule}</td><td>{r.nights_per_zone:.1f}</td><td>{_pct(r.output_lost)}</td>"
                     f"<td>{_pct(r.migration_covered)}</td></tr>" for r in ov.itertuples())
    rows_c = "".join(f"<tr><td>{r.group}</td><td>{r.zone_nights:,}</td><td>{_pct(r.busy)}</td>"
                     f"<td>×{r.lift:.2f}</td></tr>" for r in cs.itertuples())
    rows_z = "".join(f"<tr><td>{r.zone}</td><td>{r.radar}</td><td>{r.dist_km:.0f}</td><td>{r.nights}</td>"
                     f"<td>{r.rho:+.2f}</td><td>{_pct(r.very_high_busy)}</td></tr>" for r in bz.itertuples())
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Wind farms · hindcast and radar check</title>", STYLE,
        "<h1>Wind farms · what the rule would have done, and whether the radar agreed</h1>",
        "<p>The daily wind-farm forecast suggests stopping only when the passage is very high and stopping is "
        "cheap. Before anyone relies on it, it has to answer two questions on the past: <b>what would it have "
        "cost</b>, and <b>were the nights it picked really heavy?</b> Both are answered here on the ERA5 "
        "reanalysis (Copernicus) at each zone's point from 2021, the archive the zone thresholds are cut on.</p>",
        "<div class='k'>" + "".join(f"<div>{k}<b>{v}</b></div>" for k, v in summary.items()) + "</div>",
        "<h2>1. What stopping would have cost</h2>",
        "<p>The model is run over every past night of every zone. The level comes from the zone's own thresholds "
        "(percentiles over the nights around the same date) and the advice from the same table as the forecast. "
        "<i>Nights</i> are counted per season and zone; <i>output lost</i> is the share of the zone's night "
        "output (generic power curve, ERA5 wind at 100 m) that falls on the nights the rule picks; "
        "<i>migration covered</i> is the share of the predicted density that passes on them.</p>",
        "<table><tr><th>rule</th><th>nights per season and zone</th><th>night output lost</th>"
        "<th>predicted migration covered</th></tr>" + rows_o + "</table>",
        "<p>Stopping on every very high night would cover a little more migration at about four times the cost: "
        "the extra nights are windy ones. Stopping only on the calm ones keeps most of the protection for a "
        "small share of the output, because heavy passage tends to come on nights with little wind.</p>",
        "<details><summary>Per season</summary><table><tr><th>season</th><th>zones</th>"
        + "".join(f"<th>{k}: nights</th><th>{k}: output</th>" for k in rules) + "</tr>" + "".join(rows_h)
        + "</table></details>",
        "<h2>2. Were those nights heavy? The nearest radar</h2>",
        f"<p>No radar measures at a wind farm, but the nearest one says whether the night was busy in that "
        f"region. Each zone within {MAX_KM} km of a radar of the European network is paired with it, and the "
        "radar's measured night is placed in that radar's own record for the same season and the same years. "
        "A <b>busy</b> night is one in the top quarter of that record, as in the city verification, so by "
        f"chance about a quarter of the nights are busy ({base:.1%} here).</p>",
        f"<p><img src='{fig.name}'></p>",
        "<table><tr><th>nights</th><th>zone-nights</th><th>busy at the radar</th><th>against chance</th></tr>"
        + rows_c + "</table>",
        "<p>The levels sort the nights the right way: a <b>low</b> night is busy about half as often as chance "
        "and a <b>very high</b> one more than twice as often. The nights the rule says to stop are the busiest "
        f"of all. Per zone, the median rank correlation between predicted and measured density is "
        f"{bz['rho'].median():+.2f}.</p>",
        "<details><summary>Per zone</summary><p>Rank correlation (Spearman) between the predicted density and "
        "the density the radar measured, and how many of the zone's very high nights the radar found busy.</p>"
        "<table><tr><th>zone</th><th>radar</th><th>km</th><th>nights</th><th>ρ</th>"
        "<th>very high nights busy</th></tr>" + rows_z + "</table></details>",
        "<h2>What this does and does not show</h2><ul>"
        "<li><b>Reanalysis, not forecast.</b> The weather is ERA5, the best estimate of what happened, not the "
        "forecast that would have been published days before. It measures the model and the rule; the error of "
        "the forecast itself is measured by the city verification since publication started.</li>"
        f"<li><b>The radar is not at the farm.</b> Pairs are {lo:.0f} to {hi:.0f} km apart and the radar sees "
        "the whole column from about 200 m to 3 km, not the rotor layer. A busy night at the radar says the "
        "region was busy.</li>"
        f"<li><b>Left out.</b> Zones farther than {MAX_KM} km from any radar, nights with less than "
        f"{S.MIN_COVERAGE:.0%} radar coverage, radar-nights with fewer than {S.MIN_REF} reference nights, and the "
        "radar record before the hindcast years: several radars measured on another scale before 2020 (the "
        "median night of 2016 is five times today's), which would make every recent night look quiet.</li>"
        "<li><b>Not independent of the model.</b> The model was trained on these radars. It was validated leaving "
        "whole radars out, but a zone near a training radar is not a fully new place.</li></ul>",
        "<p><small>Weather: ERA5 hourly reanalysis, Copernicus Climate Change Service. Radar profiles: ENRAM / "
        "Aloft (CC0). Turbines © OpenStreetMap contributors (ODbL).</small></p>",
    ]
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    embed_images(out)
