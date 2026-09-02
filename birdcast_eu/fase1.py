"""Fase 1: informe de climatologías y umbrales (output/fase1.html)."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .historico import SEASONS


def fig_climatology(doy: pd.DataFrame, radars: list[str], path: Path, ncols: int = 3) -> None:
    radars = [r for r in radars if r in set(doy["radar"])]
    if not radars:
        return
    nrows = int(np.ceil(len(radars) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 2.6 * nrows), sharex=True, squeeze=False)
    for ax, r in zip(axes.flat, radars):
        g = doy[doy["radar"] == r].sort_values("doy")
        ax.fill_between(g["doy"], g["p50"], g["p90"], color="#1E6B72", alpha=.25, label="P50-P90")
        ax.plot(g["doy"], g["p50"], color="#1E6B72", lw=1.6, label="mediana")
        ax.plot(g["doy"], g["p90"], color="#B8720C", lw=1.2, label="P90")
        for (m1, d1), (m2, d2) in SEASONS.values():
            a = pd.Timestamp(2001, m1, d1).dayofyear
            b = pd.Timestamp(2001, m2, d2).dayofyear
            ax.axvspan(a, b, color="#ccc", alpha=.25, lw=0)
        ax.set_title(f"{r} ({g['years'].iloc[0]} años, n={g['n'].median():.0f}/día)", fontsize=9)
        ax.set_yscale("symlog", linthresh=100)
        ax.grid(alpha=.3)
        ax.set_xticks([1, 60, 121, 182, 244, 305])
        ax.set_xticklabels(["ene", "mar", "may", "jul", "sep", "nov"], fontsize=8)
    for ax in axes.flat[len(radars):]:
        ax.axis("off")
    axes.flat[0].legend(fontsize=7, loc="upper left")
    fig.suptitle("Climatología del MTR nocturno (aves/km/noche) por día del año; sombreado: ventanas de alerta", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_thresholds_map(th: pd.DataFrame, path: Path, season: str = "primavera") -> None:
    s = th[th["season"] == season]
    if s.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 6))
    sc = ax.scatter(s["lon"], s["lat"], c=np.log10(s["p90"].clip(lower=1)), s=40 + 400 * s["share_top10"],
                    cmap="viridis", edgecolor="k", lw=.4)
    for _, r in s.iterrows():
        ax.annotate(r["radar"], (r["lon"], r["lat"]), fontsize=6, xytext=(3, 3), textcoords="offset points")
    fig.colorbar(sc, ax=ax, label="log10 P90 MTR nocturno")
    ax.set_title(f"Umbral de alerta alta (P90) en {season}; tamaño = fracción del paso en el 10 % de noches punta", fontsize=9)
    ax.set_xlabel("lon"); ax.set_ylabel("lat"); ax.grid(alpha=.3); ax.set_aspect(1.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def write_report(th: pd.DataFrame, doy: pd.DataFrame, nightly: pd.DataFrame, figures: list[Path], out: Path) -> None:
    t = th.copy()
    for c in ("p50", "p70", "p90", "max"):
        t[c] = t[c].map("{:,.0f}".format)
    t["share_top10"] = t["share_top10"].map("{:.0%}".format)
    t[["lat", "lon"]] = t[["lat", "lon"]].round(2)
    cov = nightly.groupby("radar").agg(noches=("night", "size"), desde=("night", "min"), hasta=("night", "max"),
                                       cobertura_media=("coverage", "mean")).reset_index()
    cov["desde"] = cov["desde"].dt.date; cov["hasta"] = cov["hasta"].dt.date
    cov["cobertura_media"] = cov["cobertura_media"].map("{:.0%}".format)
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Fase 1 · climatologías y umbrales</title>",
        "<style>body{font-family:system-ui;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#16202B}"
        "table{border-collapse:collapse;font-size:.8rem}th,td{padding:.3rem .5rem;border-bottom:1px solid #ddd;text-align:right}"
        "th:first-child,td:first-child,td:nth-child(2),th:nth-child(2){text-align:left}img{max-width:100%;margin:1rem 0}"
        ".note{background:#F8EBD3;border-left:3px solid #B8720C;padding:.6rem 1rem;margin:1rem 0}</style>",
        "<h1>Fase 1 · climatologías y umbrales de alerta por radar</h1>",
        f"<p>Generado el {pd.Timestamp.utcnow():%Y-%m-%d %H:%M} UTC. {nightly['radar'].nunique()} radares, "
        f"{len(nightly):,} noches ({nightly['night'].min():%Y-%m-%d} → {nightly['night'].max():%Y-%m-%d}). "
        "Solo noches con cobertura ≥ 60 %.</p>",
        "<div class='note'>Umbrales relativos: «alta» = MTR nocturno ≥ P90 histórico del radar en la temporada; «media» = P70-P90. "
        "share_top10 = fracción del paso estacional concentrado en el 10 % de noches más intensas (BirdCast EE. UU.: ~54 %). "
        "Sin filtro de insectos: los radares del sur y los veranos están inflados.</div>",
        "<h2>Umbrales por radar y temporada</h2>", t.to_html(index=False, escape=True),
        "<h2>Cobertura del histórico</h2>", cov.to_html(index=False, escape=True),
    ]
    for f in figures:
        if f.exists():
            parts.append(f"<img src='{f.name}' alt='{f.stem}'>")
    out.write_text("\n".join(parts), encoding="utf-8")
