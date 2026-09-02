"""Fase 1: tabla radar × noche para todo el histórico de Aloft (2012-hoy) y climatologías por radar.

El histórico completo en CSV ocupa decenas de GB; aquí se procesa radar a radar y año a año, se guarda solo la
tabla nocturna (unos KB por radar-año) y, si se pide, se borra la caché de descargas al terminar cada año.
"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from . import aloft
from .nightly import build_nightly

# Ventanas migratorias para los umbrales de alerta (Iberia y Europa occidental)
SEASONS = {
    "primavera": ((2, 15), (5, 31)),
    "otoño": ((8, 15), (11, 30)),
}
COVERAGE_MIN = 0.6
WINDOW_DAYS = 15  # ±15 días alrededor de cada día del año para la climatología


def build_history(radar: str, years: list[int], cache: Path, out_dir: Path, purge: bool = True, log=print) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{radar}.parquet"
    existing = pd.read_parquet(dest) if dest.exists() else pd.DataFrame()
    frames = [existing] if not existing.empty else []
    today = dt.datetime.now(dt.timezone.utc).date()
    for y in years:
        end = min(dt.date(y, 12, 31), today - dt.timedelta(days=1))
        if end < dt.date(y, 1, 1):
            continue
        try:
            df = aloft.fetch_radar(radar, dt.date(y, 1, 1), end, cache, log=lambda *_: None)
        except Exception as e:  # red, fichero corrupto…: se anota y se sigue
            log(f"  {radar} {y}: error {e}")
            continue
        if df.empty:
            log(f"  {radar} {y}: sin datos")
        else:
            _, n = build_nightly(df, radar)
            frames.append(n)
            log(f"  {radar} {y}: {len(n)} noches, MTR mediana {n['mtr_night'].median():,.0f}")
        if purge:
            for sub in ("monthly", "daily"):
                shutil.rmtree(cache / "baltrad" / sub / radar / str(y), ignore_errors=True)
    if not frames:
        return pd.DataFrame()
    hist = pd.concat(frames, ignore_index=True)
    hist = hist.drop_duplicates(subset=["radar", "night"], keep="last").sort_values("night").reset_index(drop=True)
    hist.to_parquet(dest, index=False)
    return hist


def load_all_nightly(nightly_dir: Path) -> pd.DataFrame:
    files = [p for p in nightly_dir.glob("*.parquet") if not p.name.endswith("_profiles.parquet")]
    if not files:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
    df["night"] = pd.to_datetime(df["night"])
    return df


def climatology_doy(nightly: pd.DataFrame, window: int = WINDOW_DAYS, min_n: int = 20) -> pd.DataFrame:
    """Cuantiles del MTR nocturno por radar y día del año, agrupando todos los años en una ventana circular."""
    rows = []
    n = nightly[nightly["coverage"] >= COVERAGE_MIN]
    for radar, g in n.groupby("radar"):
        doy = g["night"].dt.dayofyear.to_numpy()
        val = g["mtr_night"].to_numpy()
        years = g["night"].dt.year.nunique()
        for d in range(1, 367):
            dist = np.abs(doy - d)
            dist = np.minimum(dist, 366 - dist)
            v = val[dist <= window]
            if len(v) < min_n:
                continue
            q = np.quantile(v, [0.5, 0.7, 0.9])
            rows.append({"radar": radar, "doy": d, "n": len(v), "years": years, "p50": q[0], "p70": q[1], "p90": q[2]})
    return pd.DataFrame(rows)


def season_mask(night: pd.Series, season: str) -> pd.Series:
    (m1, d1), (m2, d2) = SEASONS[season]
    md = night.dt.month * 100 + night.dt.day
    return (md >= m1 * 100 + d1) & (md <= m2 * 100 + d2)


def thresholds(nightly: pd.DataFrame, min_nights: int = 60) -> pd.DataFrame:
    """Umbrales de alerta por radar y temporada: P70 (medio) y P90 (alto) del MTR nocturno histórico."""
    rows = []
    n = nightly[nightly["coverage"] >= COVERAGE_MIN]
    for radar, g in n.groupby("radar"):
        for season in SEASONS:
            s = g[season_mask(g["night"], season)]
            if len(s) < min_nights:
                continue
            v = s["mtr_night"]
            rows.append({
                "radar": radar, "season": season, "nights": len(v), "years": s["night"].dt.year.nunique(),
                "first": s["night"].min().date(), "last": s["night"].max().date(),
                "p50": v.median(), "p70": v.quantile(0.7), "p90": v.quantile(0.9), "max": v.max(),
                # fracción del paso estacional que ocurre en el 10 % de noches más intensas (Horton 2021: ~54 % en EE. UU.)
                "share_top10": v.nlargest(max(1, len(v) // 10)).sum() / max(v.sum(), 1e-9),
                "lat": s["lat"].iloc[0], "lon": s["lon"].iloc[0],
            })
    return pd.DataFrame(rows)
