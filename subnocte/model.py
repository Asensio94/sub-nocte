"""Phase 2: forecast model for the nightly bird density (VID, birds/km²) from the weather.

It follows Van Doren & Horton (2018): boosted trees over the night's weather variables plus the annual cycle;
the target is cube-root transformed to tame the tail. LightGBM is used here.

Two questions the evaluation answers:
  1. How much does the weather explain on top of what the calendar already explains? (compare with climatology)
  2. Does it catch the high-alert nights (>= local seasonal P90) without firing too many false alarms?

Honest validation along two axes: by year (leave a whole year out) and by radar (leave whole radars out, in
particular the new Spanish ones, which are the destination of the service).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .history import COVERAGE_MIN, SEASONS, season_mask
from .weather import night_features

TARGET = "vid_night"
META = ["radar", "night", "season", "year", TARGET, "y", "clim_p50", "clim_p90", "alert_obs"]


def build_dataset(nightly: pd.DataFrame, weather_dir: Path, clim: pd.DataFrame, log=print,
                  levels_dir: Path | None = None) -> pd.DataFrame:
    """Join nights, weather and climatology into one row per radar-night inside the migration windows."""
    n = nightly[(nightly["coverage"] >= COVERAGE_MIN) & nightly[TARGET].notna()].copy()
    n["night"] = pd.to_datetime(n["night"])
    n["season"] = np.where(season_mask(n["night"], "spring"), "spring",
                           np.where(season_mask(n["night"], "autumn"), "autumn", ""))
    n = n[n["season"] != ""]
    c = clim[clim["metric"] == TARGET][["radar", "doy", "p50", "p90"]].rename(
        columns={"p50": "clim_p50", "p90": "clim_p90"})
    parts = []
    for radar, g in n.groupby("radar"):
        f = weather_dir / f"{radar}.parquet"
        if not f.exists():
            log(f"  {radar}: no weather")
            continue
        fv = levels_dir / f"{radar}.parquet" if levels_dir else None
        lv = pd.read_parquet(fv) if fv and fv.exists() else None
        feats = night_features(pd.read_parquet(f), g, levels=lv)
        if feats.empty:
            continue
        d = g.merge(feats, on=["radar", "night"], how="inner")
        parts.append(d)
        alt = f", {d['ws_850hPa'].notna().sum()} with wind aloft" if "ws_850hPa" in d else ""
        log(f"  {radar}: {len(d)} nights with weather{alt}")
    ds = pd.concat(parts, ignore_index=True)
    ds["doy"] = ds["night"].dt.dayofyear
    ds["year"] = ds["night"].dt.year
    ds["doy_sin"] = np.sin(2 * np.pi * ds["doy"] / 365.25)
    ds["doy_cos"] = np.cos(2 * np.pi * ds["doy"] / 365.25)
    ds = ds.merge(c, on=["radar", "doy"], how="left")
    ds["y"] = np.cbrt(ds[TARGET])
    # observed alert: the night is above the local historical P90 of its season
    th = (n.groupby(["radar", "season"])[TARGET].quantile(0.9).rename("p90_season").reset_index())
    ds = ds.merge(th, on=["radar", "season"], how="left")
    ds["alert_obs"] = ds[TARGET] >= ds["p90_season"]
    return ds


def mark_alerts(ds: pd.DataFrame) -> pd.DataFrame:
    """Recompute the heavy-passage threshold (local P90 per radar and season) over the nights fed to the model.

    It has to be recomputed every time the set is filtered, for example down to the years with wind at flight
    altitude. With the P90 of the full archive, the subset from 2021 leaves the French radars with 0.3 % of
    nights above the threshold and some Spanish ones with 23 %, instead of the 10 % that defines the event; with
    that, neither the hit rate nor the false-alarm rate is comparable to what chance would give.
    """
    th = ds.groupby(["radar", "season"])[TARGET].quantile(0.9).rename("p90_season").reset_index()
    ds = ds.drop(columns=["p90_season"], errors="ignore").merge(th, on=["radar", "season"], how="left")
    ds["alert_obs"] = ds[TARGET] >= ds["p90_season"]
    return ds


SURFACE = {"t2m", "rh2m", "pmsl", "precip", "precip_h", "cloud", "dp24", "dt24"}
UPPER_AIR = {"t850", "gh850", "dt850_24"}


def feature_columns(ds: pd.DataFrame, levels: bool = True) -> list[str]:
    """Features: the night's weather, annual cycle, local climatology and position. Nothing from the radar that night.

    With `levels=False` everything coming from pressure levels is excluded, to measure how much knowing the wind
    at the altitude the birds fly at adds over knowing only the surface wind.
    """
    wx = [c for c in ds.columns if c.split("_")[0] in {"ws", "tail", "cross", "tail0"}
          or c in SURFACE | UPPER_AIR]
    if not levels:
        wx = [c for c in wx if "hPa" not in c and c not in UPPER_AIR]
    return wx + ["doy_sin", "doy_cos", "clim_p50", "clim_p90", "lat", "lon"]


PARAMS = dict(learning_rate=0.03, num_leaves=31, min_child_samples=40, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, reg_lambda=1.0, verbose=-1)
ROUNDS = 600


def _fit(train: pd.DataFrame, cols: list[str], seed: int = 0):
    """Intensity model: regression on the cube root of the VID."""
    import lightgbm as lgb
    return lgb.train(dict(PARAMS, objective="regression", seed=seed),
                     lgb.Dataset(train[cols], train["y"]), num_boost_round=ROUNDS)


def _fit_alert(train: pd.DataFrame, cols: list[str], seed: int = 0):
    """Alert model: classifies the heavy-passage night directly (VID >= local seasonal P90).

    The operational decision is binary, and a classifier trained on that event separates the tail better than
    a mean regression, which shrinks the predictions towards the centre.
    """
    import lightgbm as lgb
    return lgb.train(dict(PARAMS, objective="binary", seed=seed),
                     lgb.Dataset(train[cols], train["alert_obs"].astype(int)), num_boost_round=ROUNDS)


MIN_NIGHTS_RADAR = 100
ALERT_Q = 0.9  # alerts fire on the 10 % of nights with the highest prediction, the observed P90 rate


def alert_flags(d: pd.DataFrame, pred: np.ndarray, q: float = ALERT_Q) -> np.ndarray:
    """Alert = prediction in the top decile of that radar and season's predictions.

    A mean model shrinks towards the centre and almost never crosses the observed 90th percentile, so an
    absolute threshold cannot decide. The threshold is calibrated on the distribution of predictions, which in
    operation comes from running the model over ten years of reanalysis at that point: no radar in the city is
    needed. By issuing as many alerts as there are alert nights, the hits are directly comparable to the 10 %
    that chance would give.
    """
    out = np.zeros(len(d), dtype=bool)
    g = d.assign(_p=pred).groupby(["radar", "season"])["_p"]
    thr = g.transform(lambda s: s.quantile(q) if len(s) >= 20 else np.inf).to_numpy()
    np.greater_equal(pred, thr, out=out)
    return out


CLIM_WINDOW = 7   # days on each side for the moving climatology
MIN_CLIM = 5      # minimum nights in the window to give a percentile


def clim_window(df: pd.DataFrame, doys: pd.DataFrame, window: int = CLIM_WINDOW) -> pd.DataFrame:
    """P50 and P90 of the VID per radar and day of year with a circular moving window, from `df` alone.

    It is recomputed inside each fold: the climatology in the file was built with every year, including the one
    left out, and using it as is would leak the answer to the model.
    """
    rows = []
    targets = doys.groupby("radar")["doy"].unique().to_dict()
    for radar, g in df.groupby("radar"):
        doy = g["doy"].to_numpy(); v = g[TARGET].to_numpy()
        for d in targets.get(radar, []):
            dist = np.abs(doy - d)
            dist = np.minimum(dist, 365 - dist)
            sel = v[dist <= window]
            if len(sel) >= MIN_CLIM:
                rows.append((radar, d, float(np.quantile(sel, 0.5)), float(np.quantile(sel, 0.9))))
    return pd.DataFrame(rows, columns=["radar", "doy", "clim_p50", "clim_p90"])


def _with_clim(d: pd.DataFrame, cl: pd.DataFrame) -> pd.DataFrame:
    return d.drop(columns=["clim_p50", "clim_p90"]).merge(cl, on=["radar", "doy"], how="left")


def evaluate(ds: pd.DataFrame, cols: list[str], log=print, years_only: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cross-validation by year and by radar. Returns (metrics table, out-of-sample predictions).

    Every fold uses only the information that would have been available:
      - leaving a year out, the local climatology is recomputed with the remaining years;
      - leaving a radar out, the local climatology disappears from the features, because in a city without a
        radar it does not exist. That is the hardest scenario and the one the service faces.
    """
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score

    def metrics(d: pd.DataFrame, pred: np.ndarray, palert: np.ndarray, label: str) -> dict:
        obs = d["y"].to_numpy()
        clim = np.cbrt(d["clim_p50"].fillna(d["clim_p50"].median())).to_numpy()
        ss = np.sum((obs - obs.mean()) ** 2)
        r2 = 1 - np.sum((obs - pred) ** 2) / ss if ss > 0 else np.nan
        r2_clim = 1 - np.sum((obs - clim) ** 2) / ss if ss > 0 else np.nan
        a_obs = d["alert_obs"].to_numpy()
        a_pred = alert_flags(d, palert)
        tp = np.sum(a_pred & a_obs)
        both = 0 < a_obs.sum() < len(a_obs)
        return {"split": label, "n": len(d), "spearman": spearmanr(obs, pred).correlation, "r2": r2,
                "r2_clim": r2_clim,
                "auc": roc_auc_score(a_obs, palert) if both else np.nan,
                "auc_intensity": roc_auc_score(a_obs, pred) if both else np.nan,
                "alerts_obs": int(a_obs.sum()), "alerts_pred": int(a_pred.sum()),
                "hit_rate": tp / max(a_obs.sum(), 1), "false_alarm": 1 - tp / max(a_pred.sum(), 1)}

    no_clim = [c for c in cols if not c.startswith("clim_")]

    def fold(tr: pd.DataFrame, te: pd.DataFrame, label: str, kind: str) -> None:
        if kind == "radar":
            c = no_clim  # the excluded radar has no climatology of its own available
        else:
            c = cols
            cl = clim_window(tr, ds[["radar", "doy"]])
            tr, te = _with_clim(tr, cl), _with_clim(te, cl)
        p = _fit(tr, c).predict(te[c])
        pa = _fit_alert(tr, c).predict(te[c])
        rows.append(metrics(te, p, pa, label))
        preds.append(te[["radar", "night", "season", "y"]].assign(pred=p, p_alert=pa, split=kind))
        m = rows[-1]
        log(f"  {label}: spearman {m['spearman']:.2f}, R² {m['r2']:.2f} (clim {m['r2_clim']:.2f}), "
            f"area under the curve {m['auc']:.2f}, heavy passage captured {m['hit_rate']:.0%}")

    rows, preds = [], []
    # 1) by year: train on the remaining years
    for y in sorted(ds["year"].unique()):
        tr, te = ds[ds["year"] != y], ds[ds["year"] == y]
        if len(te) < 100 or len(tr) < 1000:
            continue
        fold(tr, te, f"year {y}", "year")
    # 2) by radar: leave out every radar with at least MIN_NIGHTS_RADAR nights. The limit is set at 100 so the
    # renewed Spanish radars (122-130 nights, a single season) get their own validation: they are precisely the
    # use case, a city where the model has never seen radar data.
    for r, te in ds.groupby("radar"):
        if years_only or len(te) < MIN_NIGHTS_RADAR:
            continue
        fold(ds[ds["radar"] != r], te, f"radar {r}", "radar")
    return pd.DataFrame(rows), pd.concat(preds, ignore_index=True)


def importance(ds: pd.DataFrame, cols: list[str]) -> pd.DataFrame:  # noqa: D401
    """Relative gain of each feature in both models, as a percentage."""
    out = {}
    for name, f in (("intensity", _fit), ("alert", _fit_alert)):
        g = pd.Series(f(ds, cols).feature_importance("gain"), index=cols)
        out[name] = g / g.sum() * 100
    return pd.DataFrame(out).sort_values("alert", ascending=False)


def fit_final(ds: pd.DataFrame, cols: list[str], out_dir: Path, prefix: str = "model") -> list[Path]:
    """Train on everything and save both models ready to operate."""
    paths = []
    for name, f in (("vid", _fit), ("alert", _fit_alert)):
        p = out_dir / f"{prefix}_{name}.txt"
        f(ds, cols).save_model(str(p))
        paths.append(p)
    return paths
