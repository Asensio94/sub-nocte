"""Phase 1: radar × night table for the whole Aloft archive (2012-today) plus per-radar climatologies.

The full archive as CSV runs into tens of GB; here it is processed radar by radar and year by year, only the
nightly table is kept (a few KB per radar-year) and, on request, the download cache is purged after each year.
"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from . import aloft
from .nightly import build_nightly

# Migration windows used for the alert thresholds (Iberia and western Europe)
SEASONS = {
    "spring": ((2, 15), (5, 31)),
    "autumn": ((8, 15), (11, 30)),
}
COVERAGE_MIN = 0.6
WINDOW_DAYS = 15  # ±15 days around each day of the year for the climatology


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
        except Exception as e:  # network, corrupt file…: noted and skipped
            log(f"  {radar} {y}: error {e}")
            continue
        if df.empty:
            log(f"  {radar} {y}: no data")
        else:
            try:
                _, n = build_nightly(df, radar)
            except Exception as e:  # one odd radar-year must not abort the whole sweep
                log(f"  {radar} {y}: error while summarising ({type(e).__name__}: {e})")
                n = pd.DataFrame()
            if n.empty:
                log(f"  {radar} {y}: no usable nights")
            else:
                frames.append(n)
                usable = n["mtr_night"].notna().mean()
                log(f"  {radar} {y}: {len(n)} nights, median MTR {n['mtr_night'].median():,.0f}"
                    f"{'' if usable > 0.9 else f' (only {usable:.0%} with measured speed)'}")
        if purge:
            for sub in ("monthly", "daily"):
                shutil.rmtree(cache / "baltrad" / sub / radar / str(y), ignore_errors=True)
    if not frames:
        _mark_without_nights(out_dir, radar, years)
        return pd.DataFrame()
    hist = pd.concat(frames, ignore_index=True)
    hist = hist.drop_duplicates(subset=["radar", "night"], keep="last").sort_values("night").reset_index(drop=True)
    hist.to_parquet(dest, index=False)
    return hist


def _mark_without_nights(out_dir: Path, radar: str, years: list[int]) -> None:
    """Record radar-years processed without usable nights so they are not retried on every verification."""
    mark = out_dir / "_without_nights.csv"
    prev = pd.read_csv(mark) if mark.exists() else pd.DataFrame(columns=["radar", "year"])
    new = pd.DataFrame({"radar": radar, "year": years})
    pd.concat([prev, new]).drop_duplicates().to_csv(mark, index=False)


def without_nights(out_dir: Path) -> set[tuple[str, int]]:
    mark = out_dir / "_without_nights.csv"
    if not mark.exists():
        return set()
    d = pd.read_csv(mark)
    return {(r.radar, int(r.year)) for r in d.itertuples()}


def load_all_nightly(nightly_dir: Path) -> pd.DataFrame:
    files = [p for p in nightly_dir.glob("*.parquet") if not p.name.endswith("_profiles.parquet")]
    if not files:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
    df["night"] = pd.to_datetime(df["night"])
    return df


def climatology_doy(nightly: pd.DataFrame, window: int = WINDOW_DAYS, min_n: int = 20,
                    metric: str = "mtr_night") -> pd.DataFrame:
    """Quantiles of the nightly metric per radar and day of year, pooling every year in a circular window."""
    rows = []
    n = nightly[(nightly["coverage"] >= COVERAGE_MIN) & nightly[metric].notna()]
    for radar, g in n.groupby("radar"):
        doy = g["night"].dt.dayofyear.to_numpy()
        val = g[metric].to_numpy()
        years = g["night"].dt.year.nunique()
        for d in range(1, 367):
            dist = np.abs(doy - d)
            dist = np.minimum(dist, 366 - dist)
            v = val[dist <= window]
            if len(v) < min_n:
                continue
            q = np.quantile(v, [0.5, 0.7, 0.9])
            rows.append({"radar": radar, "metric": metric, "doy": d, "n": len(v), "years": years,
                         "p50": q[0], "p70": q[1], "p90": q[2]})
    return pd.DataFrame(rows)


def season_mask(night: pd.Series, season: str) -> pd.Series:
    (m1, d1), (m2, d2) = SEASONS[season]
    md = night.dt.month * 100 + night.dt.day
    return (md >= m1 * 100 + d1) & (md <= m2 * 100 + d2)


def thresholds(nightly: pd.DataFrame, min_nights: int = 60, metric: str = "mtr_night") -> pd.DataFrame:
    """Alert thresholds per radar and season: P70 (medium) and P90 (high) of the historical nightly metric."""
    rows = []
    n = nightly[(nightly["coverage"] >= COVERAGE_MIN) & nightly[metric].notna()]
    for radar, g in n.groupby("radar"):
        for season in SEASONS:
            s = g[season_mask(g["night"], season)]
            if len(s) < min_nights:
                continue
            v = s[metric]
            rows.append({
                "radar": radar, "metric": metric, "season": season, "nights": len(v),
                "years": s["night"].dt.year.nunique(),
                "first": s["night"].min().date(), "last": s["night"].max().date(),
                "p50": v.median(), "p70": v.quantile(0.7), "p90": v.quantile(0.9), "max": v.max(),
                # share of the seasonal passage happening on the 10 % busiest nights (Horton 2021: ~54 % in the US)
                "share_top10": v.nlargest(max(1, len(v) // 10)).sum() / max(v.sum(), 1e-9),
                "lat": s["lat"].iloc[0], "lon": s["lon"].iloc[0],
            })
    return pd.DataFrame(rows)
