"""Fase 2: modelo de pronóstico de la densidad nocturna de aves (VID, aves/km²) a partir de la meteorología.

Sigue a Van Doren & Horton (2018): árboles potenciados sobre variables meteorológicas de la noche más el ciclo
anual; la variable objetivo se transforma con la raíz cúbica para domar la cola. Aquí se usa LightGBM.

Dos preguntas que responde la evaluación:
  1. ¿Cuánto explica la meteorología sobre lo que ya explica el calendario? (comparar con la climatología)
  2. ¿Detecta las noches de alerta alta (≥ P90 local de la temporada) sin disparar demasiadas falsas alarmas?

Validación honesta en dos ejes: por año (dejar fuera un año entero) y por radar (dejar fuera radares enteros,
en particular los españoles nuevos, que son el destino del servicio).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .historico import COVERAGE_MIN, SEASONS, season_mask
from .meteo import night_features

TARGET = "vid_night"
META = ["radar", "night", "season", "year", TARGET, "y", "clim_p50", "clim_p90", "alerta_obs"]


def build_dataset(nightly: pd.DataFrame, meteo_dir: Path, clim: pd.DataFrame, log=print) -> pd.DataFrame:
    """Une noches, meteorología y climatología en una fila por radar-noche dentro de las ventanas migratorias."""
    n = nightly[(nightly["coverage"] >= COVERAGE_MIN) & nightly[TARGET].notna()].copy()
    n["night"] = pd.to_datetime(n["night"])
    n["season"] = np.where(season_mask(n["night"], "primavera"), "primavera",
                           np.where(season_mask(n["night"], "otoño"), "otoño", ""))
    n = n[n["season"] != ""]
    c = clim[clim["metrica"] == TARGET][["radar", "doy", "p50", "p90"]].rename(columns={"p50": "clim_p50", "p90": "clim_p90"})
    parts = []
    for radar, g in n.groupby("radar"):
        f = meteo_dir / f"{radar}.parquet"
        if not f.exists():
            log(f"  {radar}: sin meteorología")
            continue
        feats = night_features(pd.read_parquet(f), g)
        if feats.empty:
            continue
        d = g.merge(feats, on=["radar", "night"], how="inner")
        parts.append(d)
        log(f"  {radar}: {len(d)} noches con meteorología")
    ds = pd.concat(parts, ignore_index=True)
    ds["doy"] = ds["night"].dt.dayofyear
    ds["year"] = ds["night"].dt.year
    ds["doy_sin"] = np.sin(2 * np.pi * ds["doy"] / 365.25)
    ds["doy_cos"] = np.cos(2 * np.pi * ds["doy"] / 365.25)
    ds = ds.merge(c, on=["radar", "doy"], how="left")
    ds["y"] = np.cbrt(ds[TARGET])
    # alerta observada: la noche supera el P90 histórico local de su temporada
    th = (n.groupby(["radar", "season"])[TARGET].quantile(0.9).rename("p90_temporada").reset_index())
    ds = ds.merge(th, on=["radar", "season"], how="left")
    ds["alerta_obs"] = ds[TARGET] >= ds["p90_temporada"]
    return ds


def feature_columns(ds: pd.DataFrame) -> list[str]:
    """Rasgos: meteorología de la noche, ciclo anual, climatología local y posición. Nada derivado del radar esa noche."""
    meteo = [c for c in ds.columns if c.split("_")[0] in {"ws", "tail", "cross", "tail0"}
             or c in {"t2m", "rh2m", "pmsl", "precip", "precip_h", "cloud", "dp24", "dt24"}]
    return meteo + ["doy_sin", "doy_cos", "clim_p50", "clim_p90", "lat", "lon"]


def _fit(train: pd.DataFrame, cols: list[str], seed: int = 0):
    import lightgbm as lgb
    params = dict(objective="regression", learning_rate=0.03, num_leaves=31, min_child_samples=40,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, seed=seed)
    return lgb.train(params, lgb.Dataset(train[cols], train["y"]), num_boost_round=600)


def evaluate(ds: pd.DataFrame, cols: list[str], log=print) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validación cruzada por año y por radar. Devuelve (tabla de métricas, predicciones fuera de muestra)."""
    from scipy.stats import spearmanr

    def metrics(d: pd.DataFrame, pred: np.ndarray, label: str) -> dict:
        obs = d["y"].to_numpy()
        clim = np.cbrt(d["clim_p50"].fillna(d["clim_p50"].median())).to_numpy()
        ss = np.sum((obs - obs.mean()) ** 2)
        r2 = 1 - np.sum((obs - pred) ** 2) / ss if ss > 0 else np.nan
        r2_clim = 1 - np.sum((obs - clim) ** 2) / ss if ss > 0 else np.nan
        # alerta predicha: la predicción supera el P90 local; se compara con la alerta observada
        thr = np.cbrt(d["p90_temporada"]).to_numpy()
        a_pred, a_obs = pred >= thr, d["alerta_obs"].to_numpy()
        tp = np.sum(a_pred & a_obs)
        return {"split": label, "n": len(d), "spearman": spearmanr(obs, pred).correlation, "r2": r2, "r2_clim": r2_clim,
                "alertas_obs": int(a_obs.sum()), "alertas_pred": int(a_pred.sum()),
                "acierto": tp / max(a_obs.sum(), 1), "falsa_alarma": 1 - tp / max(a_pred.sum(), 1)}

    rows, preds = [], []
    # 1) por año: entrenar con el resto de años
    for y in sorted(ds["year"].unique()):
        tr, te = ds[ds["year"] != y], ds[ds["year"] == y]
        if len(te) < 100 or len(tr) < 1000:
            continue
        p = _fit(tr, cols).predict(te[cols])
        rows.append(metrics(te, p, f"año {y}"))
        preds.append(te[["radar", "night", "y"]].assign(pred=p, split="año"))
        log(f"  año {y}: spearman {rows[-1]['spearman']:.2f}, R² {rows[-1]['r2']:.2f} (clim {rows[-1]['r2_clim']:.2f}), "
            f"acierto P90 {rows[-1]['acierto']:.0%}, falsa alarma {rows[-1]['falsa_alarma']:.0%}")
    # 2) por radar: dejar fuera cada radar con al menos 150 noches (los españoles nuevos son el objetivo)
    for r, te in ds.groupby("radar"):
        if len(te) < 150:
            continue
        tr = ds[ds["radar"] != r]
        p = _fit(tr, cols).predict(te[cols])
        rows.append(metrics(te, p, f"radar {r}"))
        preds.append(te[["radar", "night", "y"]].assign(pred=p, split="radar"))
    return pd.DataFrame(rows), pd.concat(preds, ignore_index=True)


def importance(ds: pd.DataFrame, cols: list[str]) -> pd.Series:
    m = _fit(ds, cols)
    return pd.Series(m.feature_importance("gain"), index=cols).sort_values(ascending=False)


def fit_final(ds: pd.DataFrame, cols: list[str], path: Path) -> None:
    m = _fit(ds, cols)
    m.save_model(str(path))
