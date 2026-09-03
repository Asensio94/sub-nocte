"""Fase 0: ¿contienen aves los perfiles de los radares españoles renovados?

Compara, radar a radar, cuatro firmas que toda serie de migración nocturna debe mostrar:
  1. ciclo diario: densidad de noche muy superior a la de día en temporada (los insectos hacen lo contrario)
  2. estacionalidad: MTR nocturno alto en marzo-mayo y septiembre-noviembre, bajo en pleno verano e invierno
  3. curso nocturno: pico de MTR en las 1-3 h tras el crepúsculo y descenso hacia el amanecer
  4. perfil vertical: máximo de densidad en 200-1500 m
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
    return np.select([month.isin(SPRING), month.isin(AUTUMN), month.isin((6, 7, 8))], ["primavera", "otoño", "verano"], "invierno")


def summary_table(nightly: pd.DataFrame) -> pd.DataFrame:
    n = nightly.copy()
    n["season"] = _season(n["night"].dt.month)
    rows = []
    for (radar, season), g in n.groupby(["radar", "season"]):
        g = g[g["coverage"] >= 0.6]
        if g.empty:
            continue
        rows.append({
            "radar": radar, "season": season, "noches": len(g),
            "mtr_mediana": g["mtr_night"].median(),
            "mtr_p90": g["mtr_night"].quantile(0.9),
            "mtr_max": g["mtr_night"].max(),
            "dens_noche": g["dens_night"].mean(),
            "dens_dia": g["dens_day"].mean(),
            "ratio_noche_dia": g["dens_night"].mean() / max(g["dens_day"].mean(), 1e-6),
            "alt_media_m": np.average(g["alt_mean"].fillna(0), weights=g["vid_mean"] + 1e-9),
            "cobertura": g["coverage"].mean(),
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
        ax.set_ylabel(f"{r}\naves/km/noche", fontsize=8)
        ax.grid(axis="y", alpha=.3)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    fig.suptitle("MTR nocturno por radar (naranja: cobertura de la noche < 60 %)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_daycycle(profiles: dict[str, pd.DataFrame], path: Path, months=SPRING) -> None:
    """Densidad media por hora del día (UTC) en los meses indicados."""
    fig, ax = plt.subplots(figsize=(10, 4))
    for r, p in profiles.items():
        q = p[p["datetime"].dt.month.isin(months)]
        if q.empty:
            continue
        hour = q["datetime"].dt.hour + q["datetime"].dt.minute / 60
        prof = q.groupby(np.floor(hour * 2) / 2)["dens_mean"].mean()
        ax.plot(prof.index, prof.values, label=r, lw=1.8)
    ax.set_xlabel("hora UTC")
    ax.set_ylabel("densidad media 200-3000 m (aves/km³)")
    ax.set_title(f"Ciclo diario, meses {months}: la migración es nocturna; los insectos, diurnos y vespertinos", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_nightcourse(profiles: dict[str, pd.DataFrame], path: Path, months=SPRING) -> None:
    """MTR medio en función de las horas desde el crepúsculo civil."""
    fig, ax = plt.subplots(figsize=(10, 4))
    for r, p in profiles.items():
        q = p[p["is_night"] & p["datetime"].dt.month.isin(months)].copy()
        if q.empty:
            continue
        start = q.groupby("night")["datetime"].transform("min")
        q["h_since"] = (q["datetime"] - start).dt.total_seconds() / 3600
        prof = q.groupby(np.floor(q["h_since"] * 2) / 2)["mtr"].mean()
        ax.plot(prof.index, prof.values, label=r, lw=1.8)
    ax.set_xlabel("horas desde el crepúsculo civil")
    ax.set_ylabel("MTR medio (aves/km/h)")
    ax.set_title(f"Curso nocturno, meses {months}: se espera un pico 1-3 h tras el crepúsculo", fontsize=10)
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
    ax.set_xlabel("densidad media nocturna (aves/km³)")
    ax.set_ylabel("altura sobre el radar (m)")
    ax.set_title(f"Perfil vertical nocturno, meses {months}", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


SECTORS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]


def direction_table(raw: dict[str, pd.DataFrame], positions: dict[str, tuple[float, float]], months=SPRING) -> pd.DataFrame:
    """Dirección y velocidad del tráfico, de noche y de día, ponderadas por densidad.

    La migración prenupcial en Iberia va hacia el N-NE con velocidad terrestre de 8-15 m/s y muy concentrada;
    los insectos derivan con el viento, más lentos y dispersos. `concentracion` es el módulo del vector medio
    (1 = todo el tráfico en la misma dirección).
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
        for label, mask in (("noche", el < -6), ("día", el > 6)):
            x = d[mask & (d["dens_clean"] > 0) & d["dd"].notna()]
            if x.empty:
                continue
            w = x["dens_clean"].to_numpy()
            ang = np.deg2rad(x["dd"].to_numpy())
            conc = float(np.hypot(np.average(np.sin(ang), weights=w), np.average(np.cos(ang), weights=w)))
            sec = np.floor(((x["dd"].to_numpy() + 22.5) % 360) / 45).astype(int)
            hist = np.bincount(sec, weights=w, minlength=8) / w.sum() * 100
            row = {"radar": r, "momento": label, "capas_m": f"{int(hs.min())}-{int(hs.max())}",
                   "ff_media_ms": float(np.average(x["ff"], weights=w)), "concentracion": conc}
            row.update({s: h for s, h in zip(SECTORS, hist)})
            rows.append(row)
    return pd.DataFrame(rows)


def correlation_table(nightly: pd.DataFrame, months=SPRING) -> pd.DataFrame:
    n = nightly[(nightly["coverage"] >= 0.6) & nightly["night"].dt.month.isin(months)]
    wide = n.pivot_table(index="night", columns="radar", values="mtr_night")
    return np.log1p(wide).corr(min_periods=20).round(2)


def write_report(summary: pd.DataFrame, corr: pd.DataFrame, figures: list[Path], out: Path, notes: list[str],
                 directions: pd.DataFrame | None = None) -> None:
    fmt = {"mtr_mediana": "{:,.0f}", "mtr_p90": "{:,.0f}", "mtr_max": "{:,.0f}", "dens_noche": "{:.2f}",
           "dens_dia": "{:.2f}", "ratio_noche_dia": "{:.1f}", "alt_media_m": "{:.0f}", "cobertura": "{:.0%}"}
    s = summary.copy()
    for c, f in fmt.items():
        s[c] = s[c].map(lambda v: f.format(v) if pd.notna(v) else "")
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Fase 0 · validación de radares</title>",
        "<style>body{font-family:system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#16202B}"
        "table{border-collapse:collapse;font-size:.85rem}th,td{padding:.35rem .6rem;border-bottom:1px solid #ddd;text-align:right}"
        "th:first-child,td:first-child,td:nth-child(2),th:nth-child(2){text-align:left}img{max-width:100%;margin:1rem 0}"
        ".note{background:#F8EBD3;border-left:3px solid #B8720C;padding:.6rem 1rem;margin:1rem 0}</style>",
        "<h1>Fase 0 · ¿ven aves los radares españoles renovados?</h1>",
        f"<p>Generado el {pd.Timestamp.utcnow():%Y-%m-%d %H:%M} UTC a partir del bucket público de Aloft. "
        "Solo se cuentan noches con cobertura ≥ 60 %.</p>",
    ]
    for n in notes:
        parts.append(f"<div class='note'>{html.escape(n)}</div>")
    parts.append("<h2>Resumen por radar y temporada</h2>")
    parts.append(s.to_html(index=False, escape=True))
    if directions is not None and not directions.empty:
        dd = directions.copy()
        dd["ff_media_ms"] = dd["ff_media_ms"].map("{:.1f}".format)
        dd["concentracion"] = dd["concentracion"].map("{:.2f}".format)
        for c in SECTORS:
            dd[c] = dd[c].map("{:.0f} %".format)
        parts.append("<h2>Dirección y velocidad del tráfico en primavera (ponderadas por densidad)</h2>")
        parts.append("<p>Migración = flujo nocturno concentrado hacia N-NE a 8-15 m/s. Insectos = deriva dispersa y lenta.</p>")
        parts.append(dd.to_html(index=False, escape=True))
    parts.append("<h2>Correlación entre radares (log MTR nocturno, primavera)</h2>")
    parts.append(corr.to_html(escape=True, na_rep=""))
    for f in figures:
        parts.append(f"<img src='{f.name}' alt='{f.stem}'>")
    out.write_text("\n".join(parts), encoding="utf-8")
