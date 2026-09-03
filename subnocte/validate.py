"""Phase 0: do the profiles of the renewed Spanish radars contain birds?

Radar by radar, it compares four signatures every nocturnal migration series must show:
  1. daily cycle: density far higher at night than by day in season (insects do the opposite)
  2. seasonality: high night MTR in March-May and September-November, low in high summer and winter
  3. night course: MTR peaking 1-3 h after twilight and falling towards dawn
  4. vertical profile: density maximum at 200-1500 m
"""

from __future__ import annotations

import html
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .nightly import clean

SPRING = (3, 4, 5)
AUTUMN = (9, 10, 11)


def _season(month: pd.Series) -> pd.Series:
    return np.select([month.isin(SPRING), month.isin(AUTUMN), month.isin((6, 7, 8))],
                     ["spring", "autumn", "summer"], "winter")


def summary_table(nightly: pd.DataFrame) -> pd.DataFrame:
    n = nightly.copy()
    n["season"] = _season(n["night"].dt.month)
    rows = []
    for (radar, season), g in n.groupby(["radar", "season"]):
        g = g[g["coverage"] >= 0.6]
        if g.empty:
            continue
        rows.append({
            "radar": radar, "season": season, "nights": len(g),
            "mtr_median": g["mtr_night"].median(),
            "mtr_p90": g["mtr_night"].quantile(0.9),
            "mtr_max": g["mtr_night"].max(),
            "dens_night": g["dens_night"].mean(),
            "dens_day": g["dens_day"].mean(),
            "night_day_ratio": g["dens_night"].mean() / max(g["dens_day"].mean(), 1e-6),
            "alt_mean_m": np.average(g["alt_mean"].fillna(0), weights=g["vid_mean"] + 1e-9),
            "coverage": g["coverage"].mean(),
        })
    return pd.DataFrame(rows)


def fig_timeseries(nightly: pd.DataFrame, path: Path) -> None:
    radars = list(nightly["radar"].unique())
    fig, axes = plt.subplots(len(radars), 1, figsize=(12, 2.2 * len(radars)), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, r in zip(axes, radars):
        g = nightly[nightly["radar"] == r].sort_values("night")
        ok = g["coverage"] >= 0.6
        ax.bar(g.loc[ok, "night"], g.loc[ok, "mtr_night"].clip(lower=1), width=1, color="#1E6B72")
        ax.bar(g.loc[~ok, "night"], g.loc[~ok, "mtr_night"].clip(lower=1), width=1, color="#B8720C", alpha=.6)
        ax.set_yscale("log")
        ax.set_ylabel(f"{r}\nbirds/km/night", fontsize=8)
        ax.grid(axis="y", alpha=.3)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    fig.suptitle("Night MTR per radar (orange: night coverage < 60 %)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_daycycle(profiles: dict[str, pd.DataFrame], path: Path, months=SPRING) -> None:
    """Mean density per hour of the day (UTC) in the given months."""
    fig, ax = plt.subplots(figsize=(10, 4))
    for r, p in profiles.items():
        q = p[p["datetime"].dt.month.isin(months)]
        if q.empty:
            continue
        hour = q["datetime"].dt.hour + q["datetime"].dt.minute / 60
        prof = q.groupby(np.floor(hour * 2) / 2)["dens_mean"].mean()
        ax.plot(prof.index, prof.values, label=r, lw=1.8)
    ax.set_xlabel("hour UTC")
    ax.set_ylabel("mean density 200-3000 m (birds/km³)")
    ax.set_title(f"Daily cycle, months {months}: migration is nocturnal; insects fly by day and at dusk", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_nightcourse(profiles: dict[str, pd.DataFrame], path: Path, months=SPRING) -> None:
    """Mean MTR as a function of the hours since civil twilight."""
    fig, ax = plt.subplots(figsize=(10, 4))
    for r, p in profiles.items():
        q = p[p["is_night"] & p["datetime"].dt.month.isin(months)].copy()
        if q.empty:
            continue
        start = q.groupby("night")["datetime"].transform("min")
        q["h_since"] = (q["datetime"] - start).dt.total_seconds() / 3600
        prof = q.groupby(np.floor(q["h_since"] * 2) / 2)["mtr"].mean()
        ax.plot(prof.index, prof.values, label=r, lw=1.8)
    ax.set_xlabel("hours since civil twilight")
    ax.set_ylabel("mean MTR (birds/km/h)")
    ax.set_title(f"Night course, months {months}: a peak 1-3 h after twilight is expected", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_vertical(raw: dict[str, pd.DataFrame], positions: dict[str, tuple[float, float]], path: Path, months=SPRING) -> None:
    from .solar import sun_elevation
    fig, ax = plt.subplots(figsize=(6, 5))
    for r, df in raw.items():
        d = clean(df, h_min=0, h_max=5000)
        d = d[d["datetime"].dt.month.isin(months)]
        if d.empty:
            continue
        lat, lon = positions[r]
        night = sun_elevation(lat, lon, d["datetime"]) < -6
        prof = d[night].groupby("height")["dens_clean"].mean()
        ax.plot(prof.values, prof.index, label=r, lw=1.8)
    ax.set_xlabel("mean night density (birds/km³)")
    ax.set_ylabel("height above the radar (m)")
    ax.set_title(f"Nocturnal vertical profile, months {months}", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


SECTORS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def direction_table(raw: dict[str, pd.DataFrame], positions: dict[str, tuple[float, float]], months=SPRING) -> pd.DataFrame:
    """Traffic direction and speed, by night and by day, weighted by density.

    Spring migration over Iberia heads N-NE at a ground speed of 8-15 m/s and is very concentrated; insects
    drift with the wind, slower and scattered. `concentration` is the modulus of the mean vector (1 = all the
    traffic in the same direction).
    """
    from .solar import sun_elevation
    rows = []
    for r, df in raw.items():
        d = clean(df, h_min=0, h_max=5000)
        d = d[d["datetime"].dt.month.isin(months)]
        if d.empty:
            continue
        lat, lon = positions[r]
        el = sun_elevation(lat, lon, d["datetime"])
        layers = d[d["dens_clean"].notna()].groupby("height").size()
        hs = layers[layers > 0.05 * layers.max()].index
        for label, mask in (("night", el < -6), ("day", el > 6)):
            x = d[mask & (d["dens_clean"] > 0) & d["dd"].notna()]
            if x.empty:
                continue
            w = x["dens_clean"].to_numpy()
            ang = np.deg2rad(x["dd"].to_numpy())
            conc = float(np.hypot(np.average(np.sin(ang), weights=w), np.average(np.cos(ang), weights=w)))
            sec = np.floor(((x["dd"].to_numpy() + 22.5) % 360) / 45).astype(int)
            hist = np.bincount(sec, weights=w, minlength=8) / w.sum() * 100
            row = {"radar": r, "period": label, "layers_m": f"{int(hs.min())}-{int(hs.max())}",
                   "ff_mean_ms": float(np.average(x["ff"], weights=w)), "concentration": conc}
            row.update({s: h for s, h in zip(SECTORS, hist)})
            rows.append(row)
    return pd.DataFrame(rows)


def correlation_table(nightly: pd.DataFrame, months=SPRING) -> pd.DataFrame:
    n = nightly[(nightly["coverage"] >= 0.6) & nightly["night"].dt.month.isin(months)]
    wide = n.pivot_table(index="night", columns="radar", values="mtr_night")
    return np.log1p(wide).corr(min_periods=20).round(2)


def write_report(summary: pd.DataFrame, corr: pd.DataFrame, figures: list[Path], out: Path, notes: list[str],
                 directions: pd.DataFrame | None = None) -> None:
    fmt = {"mtr_median": "{:,.0f}", "mtr_p90": "{:,.0f}", "mtr_max": "{:,.0f}", "dens_night": "{:.2f}",
           "dens_day": "{:.2f}", "night_day_ratio": "{:.1f}", "alt_mean_m": "{:.0f}", "coverage": "{:.0%}"}
    s = summary.copy()
    for c, f in fmt.items():
        s[c] = s[c].map(lambda v: f.format(v) if pd.notna(v) else "")
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Phase 0 · radar validation</title>",
        "<style>body{font-family:system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#16202B}"
        "table{border-collapse:collapse;font-size:.85rem}th,td{padding:.35rem .6rem;border-bottom:1px solid #ddd;text-align:right}"
        "th:first-child,td:first-child,td:nth-child(2),th:nth-child(2){text-align:left}img{max-width:100%;margin:1rem 0}"
        ".note{background:#F8EBD3;border-left:3px solid #B8720C;padding:.6rem 1rem;margin:1rem 0}</style>",
        "<h1>Phase 0 · do the renewed Spanish radars see birds?</h1>",
        f"<p>Generated on {pd.Timestamp.utcnow():%Y-%m-%d %H:%M} UTC from the public Aloft bucket. "
        "Only nights with coverage &ge; 60 % are counted.</p>",
    ]
    for n in notes:
        parts.append(f"<div class='note'>{html.escape(n)}</div>")
    parts.append("<h2>Summary per radar and season</h2>")
    parts.append(s.to_html(index=False, escape=True))
    if directions is not None and not directions.empty:
        dd = directions.copy()
        dd["ff_mean_ms"] = dd["ff_mean_ms"].map("{:.1f}".format)
        dd["concentration"] = dd["concentration"].map("{:.2f}".format)
        for c in SECTORS:
            dd[c] = dd[c].map("{:.0f} %".format)
        parts.append("<h2>Traffic direction and speed in spring (density-weighted)</h2>")
        parts.append("<p>Migration = concentrated nocturnal flow towards N-NE at 8-15 m/s. "
                     "Insects = scattered, slow drift.</p>")
        parts.append(dd.to_html(index=False, escape=True))
    parts.append("<h2>Correlation between radars (log night MTR, spring)</h2>")
    parts.append(corr.to_html(escape=True, na_rep=""))
    for f in figures:
        parts.append(f"<img src='{f.name}' alt='{f.stem}'>")
    out.write_text("\n".join(parts), encoding="utf-8")
