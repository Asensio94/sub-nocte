"""Phase 1: report of climatologies and thresholds (output/phase1.html)."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .history import SEASONS


LABEL = {"mtr_night": "night MTR (birds/km/night)", "vid_night": "night VID (birds/km²)"}


def fig_climatology(doy: pd.DataFrame, radars: list[str], path: Path, ncols: int = 3,
                    metric: str = "vid_night") -> None:
    doy = doy[doy["metric"] == metric]
    radars = [r for r in radars if r in set(doy["radar"])]
    if not radars:
        return
    nrows = int(np.ceil(len(radars) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 2.6 * nrows), sharex=True, squeeze=False)
    for ax, r in zip(axes.flat, radars):
        # reindex to every day of the year: days without data stay NaN and the line breaks instead of interpolating
        g = (doy[doy["radar"] == r].set_index("doy").reindex(range(1, 367))
             .assign(radar=r, years=lambda x: x["years"].ffill().bfill()).reset_index(names="doy"))
        ax.fill_between(g["doy"], g["p50"], g["p90"], color="#1E6B72", alpha=.25, label="P50-P90")
        ax.plot(g["doy"], g["p50"], color="#1E6B72", lw=1.6, label="median")
        ax.plot(g["doy"], g["p90"], color="#B8720C", lw=1.2, label="P90")
        for (m1, d1), (m2, d2) in SEASONS.values():
            a = pd.Timestamp(2001, m1, d1).dayofyear
            b = pd.Timestamp(2001, m2, d2).dayofyear
            ax.axvspan(a, b, color="#ccc", alpha=.25, lw=0)
        ax.set_title(f"{r} ({g['years'].iloc[0]:.0f} years, {int(g['n'].notna().sum())} days of the year with data)",
                     fontsize=9)
        ax.set_yscale("symlog", linthresh=1 if metric == "vid_night" else 100)
        ax.grid(alpha=.3)
        ax.set_xticks([1, 60, 121, 182, 244, 305])
        ax.set_xticklabels(["Jan", "Mar", "May", "Jul", "Sep", "Nov"], fontsize=8)
    for ax in axes.flat[len(radars):]:
        ax.axis("off")
    axes.flat[0].legend(fontsize=7, loc="upper left")
    fig.suptitle(f"Climatology of the {LABEL.get(metric, metric)} per day of the year; shaded: alert windows",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_thresholds_map(th: pd.DataFrame, path: Path, season: str = "spring",
                       metric: str = "vid_night") -> None:
    s = th[(th["season"] == season) & (th["metric"] == metric)]
    # the islands (Azores, Canaries) would flatten the map: they are left out and listed in the table
    s = s[(s["lon"] > -12) & (s["lat"] > 34)]
    if s.empty:
        return
    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    sc = ax.scatter(s["lon"], s["lat"], c=np.log10(s["p90"].clip(lower=1)), s=40 + 400 * s["share_top10"],
                    cmap="viridis", edgecolor="k", lw=.4)
    for _, r in s.iterrows():
        ax.annotate(r["radar"], (r["lon"], r["lat"]), fontsize=6, xytext=(3, 3), textcoords="offset points")
    fig.colorbar(sc, ax=ax, label=f"log10 P90 {LABEL.get(metric, metric)}")
    ax.set_title(f"High-alert threshold (P90 of the {LABEL.get(metric, metric)}) in {season}\n"
                 "size = share of the passage on the 10 % peak nights", fontsize=9)
    ax.set_xlabel("lon"); ax.set_ylabel("lat"); ax.grid(alpha=.3); ax.set_aspect(1.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def write_report(th: pd.DataFrame, doy: pd.DataFrame, nightly: pd.DataFrame, figures: list[Path], out: Path) -> None:
    t = th.copy()
    t["metric"] = t["metric"].map({"mtr_night": "MTR (birds/km/night)", "vid_night": "VID (birds/km²)"}).fillna(t["metric"])
    for c in ("p50", "p70", "p90", "max"):
        t[c] = t[c].map("{:,.0f}".format)
    t["share_top10"] = t["share_top10"].map("{:.0%}".format)
    t[["lat", "lon"]] = t[["lat", "lon"]].round(2)
    cov = nightly.groupby("radar").agg(nights=("night", "size"), first=("night", "min"), last=("night", "max"),
                                       mean_coverage=("coverage", "mean")).reset_index()
    cov["first"] = cov["first"].dt.date; cov["last"] = cov["last"].dt.date
    cov["mean_coverage"] = cov["mean_coverage"].map("{:.0%}".format)
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Phase 1 · climatologies and thresholds</title>",
        "<style>body{font-family:system-ui;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#16202B}"
        "table{border-collapse:collapse;font-size:.8rem}th,td{padding:.3rem .5rem;border-bottom:1px solid #ddd;text-align:right}"
        "th:first-child,td:first-child,td:nth-child(2),th:nth-child(2){text-align:left}img{max-width:100%;margin:1rem 0}"
        ".note{background:#F8EBD3;border-left:3px solid #B8720C;padding:.6rem 1rem;margin:1rem 0}</style>",
        "<h1>Phase 1 · climatologies and alert thresholds per radar</h1>",
        f"<p>Generated on {pd.Timestamp.utcnow():%Y-%m-%d %H:%M} UTC. {nightly['radar'].nunique()} radars, "
        f"{len(nightly):,} nights ({nightly['night'].min():%Y-%m-%d} → {nightly['night'].max():%Y-%m-%d}). "
        "Only nights with coverage &ge; 60 %.</p>",
        "<div class='note'>Relative thresholds: high = night MTR &ge; the radar's historical P90 for the season; "
        "medium = P70-P90. share_top10 = share of the seasonal passage concentrated on the 10 % busiest nights "
        "(BirdCast US: ~54 %). Two metrics: the MTR needs the speed from the wind fit, which many French radars "
        "stopped publishing in 2023; the VID (integrated density) only needs the density and is the only homogeneous "
        "2016-2026 series. No insect filter: the southern radars and the summers are inflated.</div>",
        "<h2>Thresholds per radar and season</h2>", t.to_html(index=False, escape=True),
        "<h2>Coverage of the archive</h2>", cov.to_html(index=False, escape=True),
    ]
    for f in figures:
        if f.exists():
            parts.append(f"<img src='{f.name}' alt='{f.stem}'>")
    out.write_text("\n".join(parts), encoding="utf-8")
