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


def build_dataset(nightly: pd.DataFrame, meteo_dir: Path, clim: pd.DataFrame, log=print,
                  niveles_dir: Path | None = None) -> pd.DataFrame:
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
        fv = niveles_dir / f"{radar}.parquet" if niveles_dir else None
        niv = pd.read_parquet(fv) if fv and fv.exists() else None
        feats = night_features(pd.read_parquet(f), g, niveles=niv)
        if feats.empty:
            continue
        d = g.merge(feats, on=["radar", "night"], how="inner")
        parts.append(d)
        alt = f", {d['ws_850hPa'].notna().sum()} con viento en altura" if "ws_850hPa" in d else ""
        log(f"  {radar}: {len(d)} noches con meteorología{alt}")
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


def marcar_alertas(ds: pd.DataFrame) -> pd.DataFrame:
    """Recalcula el umbral de paso fuerte (P90 local por radar y temporada) sobre las noches que entran al modelo.

    Hay que recalcularlo cada vez que se filtra el conjunto, por ejemplo a los años con viento en altura de vuelo.
    Con el P90 del histórico completo, el subconjunto desde 2021 deja a los radares franceses con un 0,3 % de
    noches por encima del umbral y a algunos españoles con un 23 %, en vez del 10 % que define el suceso; con eso
    ni la tasa de acierto ni la de falsa alarma son comparables con el 10 % que daría el azar.
    """
    th = ds.groupby(["radar", "season"])[TARGET].quantile(0.9).rename("p90_temporada").reset_index()
    ds = ds.drop(columns=["p90_temporada"], errors="ignore").merge(th, on=["radar", "season"], how="left")
    ds["alerta_obs"] = ds[TARGET] >= ds["p90_temporada"]
    return ds


SUPERFICIE = {"t2m", "rh2m", "pmsl", "precip", "precip_h", "cloud", "dp24", "dt24"}
ALTURA = {"t850", "gh850", "dt850_24"}


def feature_columns(ds: pd.DataFrame, niveles: bool = True) -> list[str]:
    """Rasgos: meteorología de la noche, ciclo anual, climatología local y posición. Nada derivado del radar esa noche.

    Con `niveles=False` se excluye todo lo que venga de niveles de presión, para medir cuánto aporta conocer el
    viento a la altura a la que vuelan las aves frente a conocer solo el de superficie.
    """
    meteo = [c for c in ds.columns if c.split("_")[0] in {"ws", "tail", "cross", "tail0"}
             or c in SUPERFICIE | ALTURA]
    if not niveles:
        meteo = [c for c in meteo if "hPa" not in c and c not in ALTURA]
    return meteo + ["doy_sin", "doy_cos", "clim_p50", "clim_p90", "lat", "lon"]


PARAMS = dict(learning_rate=0.03, num_leaves=31, min_child_samples=40, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, reg_lambda=1.0, verbose=-1)
ROUNDS = 600


def _fit(train: pd.DataFrame, cols: list[str], seed: int = 0):
    """Modelo de intensidad: regresión sobre la raíz cúbica del VID."""
    import lightgbm as lgb
    return lgb.train(dict(PARAMS, objective="regression", seed=seed),
                     lgb.Dataset(train[cols], train["y"]), num_boost_round=ROUNDS)


def _fit_alerta(train: pd.DataFrame, cols: list[str], seed: int = 0):
    """Modelo de alerta: clasifica directamente la noche de paso fuerte (VID ≥ P90 local de la temporada).

    La decisión operativa es binaria, y un clasificador entrenado sobre ese suceso separa mejor la cola que
    una regresión de media, que encoge las predicciones hacia el centro.
    """
    import lightgbm as lgb
    return lgb.train(dict(PARAMS, objective="binary", seed=seed),
                     lgb.Dataset(train[cols], train["alerta_obs"].astype(int)), num_boost_round=ROUNDS)


MIN_NOCHES_RADAR = 100
ALERT_Q = 0.9  # se alerta en el 10 % de noches con mayor predicción, la misma tasa que el P90 observado


def alert_flags(d: pd.DataFrame, pred: np.ndarray, q: float = ALERT_Q) -> np.ndarray:
    """Alerta = predicción en el decil superior de las predicciones de ese radar y temporada.

    Un modelo de media encoge hacia el centro y casi nunca cruza el percentil 90 observado, así que un umbral
    absoluto no sirve para decidir. El umbral se calibra sobre la distribución de predicciones, que en operación
    se obtiene corriendo el modelo sobre diez años de reanálisis en ese punto: no hace falta radar en la ciudad.
    Al emitir tantas alertas como noches de alerta hay, los aciertos son directamente comparables con el 10 %
    que daría el azar.
    """
    out = np.zeros(len(d), dtype=bool)
    g = d.assign(_p=pred).groupby(["radar", "season"])["_p"]
    thr = g.transform(lambda s: s.quantile(q) if len(s) >= 20 else np.inf).to_numpy()
    np.greater_equal(pred, thr, out=out)
    return out


VENTANA_CLIM = 7   # dias a cada lado para la climatologia movil
MIN_CLIM = 5       # noches minimas en la ventana para dar un percentil


def clim_ventana(df: pd.DataFrame, doys: pd.DataFrame, ventana: int = VENTANA_CLIM) -> pd.DataFrame:
    """P50 y P90 del VID por radar y dia del ano con ventana movil circular, calculados solo con `df`.

    Se recalcula dentro de cada pliegue: la climatologia del fichero se hizo con todos los anos, incluido el
    que se deja fuera, y usarla tal cual seria filtrar la respuesta al modelo.
    """
    filas = []
    objetivo = doys.groupby("radar")["doy"].unique().to_dict()
    for radar, g in df.groupby("radar"):
        doy = g["doy"].to_numpy(); v = g[TARGET].to_numpy()
        for d in objetivo.get(radar, []):
            dist = np.abs(doy - d)
            dist = np.minimum(dist, 365 - dist)
            sel = v[dist <= ventana]
            if len(sel) >= MIN_CLIM:
                filas.append((radar, d, float(np.quantile(sel, 0.5)), float(np.quantile(sel, 0.9))))
    return pd.DataFrame(filas, columns=["radar", "doy", "clim_p50", "clim_p90"])


def _con_clim(d: pd.DataFrame, cl: pd.DataFrame) -> pd.DataFrame:
    return d.drop(columns=["clim_p50", "clim_p90"]).merge(cl, on=["radar", "doy"], how="left")


def evaluate(ds: pd.DataFrame, cols: list[str], log=print, solo_anos: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validación cruzada por año y por radar. Devuelve (tabla de métricas, predicciones fuera de muestra).

    Cada pliegue usa solo la información que habría estado disponible:
      - dejando fuera un año, la climatología local se recalcula con los años restantes;
      - dejando fuera un radar, la climatología local desaparece de los rasgos, porque en una ciudad sin radar
        no existe. Es el escenario más exigente y el que corresponde al servicio.
    """
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score

    def metrics(d: pd.DataFrame, pred: np.ndarray, palerta: np.ndarray, label: str) -> dict:
        obs = d["y"].to_numpy()
        clim = np.cbrt(d["clim_p50"].fillna(d["clim_p50"].median())).to_numpy()
        ss = np.sum((obs - obs.mean()) ** 2)
        r2 = 1 - np.sum((obs - pred) ** 2) / ss if ss > 0 else np.nan
        r2_clim = 1 - np.sum((obs - clim) ** 2) / ss if ss > 0 else np.nan
        a_obs = d["alerta_obs"].to_numpy()
        a_pred = alert_flags(d, palerta)
        tp = np.sum(a_pred & a_obs)
        hay_ambos = 0 < a_obs.sum() < len(a_obs)
        return {"split": label, "n": len(d), "spearman": spearmanr(obs, pred).correlation, "r2": r2, "r2_clim": r2_clim,
                "auc": roc_auc_score(a_obs, palerta) if hay_ambos else np.nan,
                "auc_intensidad": roc_auc_score(a_obs, pred) if hay_ambos else np.nan,
                "alertas_obs": int(a_obs.sum()), "alertas_pred": int(a_pred.sum()),
                "acierto": tp / max(a_obs.sum(), 1), "falsa_alarma": 1 - tp / max(a_pred.sum(), 1)}

    sin_clim = [c for c in cols if not c.startswith("clim_")]

    def fold(tr: pd.DataFrame, te: pd.DataFrame, label: str, kind: str) -> None:
        if kind == "radar":
            c = sin_clim  # el radar excluido no tiene climatologia propia disponible
        else:
            c = cols
            cl = clim_ventana(tr, ds[["radar", "doy"]])
            tr, te = _con_clim(tr, cl), _con_clim(te, cl)
        p = _fit(tr, c).predict(te[c])
        pa = _fit_alerta(tr, c).predict(te[c])
        rows.append(metrics(te, p, pa, label))
        preds.append(te[["radar", "night", "season", "y"]].assign(pred=p, p_alerta=pa, split=kind))
        m = rows[-1]
        log(f"  {label}: spearman {m['spearman']:.2f}, R² {m['r2']:.2f} (clim {m['r2_clim']:.2f}), "
            f"área bajo la curva {m['auc']:.2f}, paso fuerte capturado {m['acierto']:.0%}")

    rows, preds = [], []
    # 1) por año: entrenar con el resto de años
    for y in sorted(ds["year"].unique()):
        tr, te = ds[ds["year"] != y], ds[ds["year"] == y]
        if len(te) < 100 or len(tr) < 1000:
            continue
        fold(tr, te, f"año {y}", "año")
    # 2) por radar: dejar fuera cada radar con al menos MIN_NOCHES_RADAR noches. El límite se fija en 100 para
    # que los radares españoles renovados (122-130 noches, una sola temporada) tengan validación propia: son
    # justamente el caso de uso, una ciudad donde el modelo no ha visto nunca datos de radar.
    for r, te in ds.groupby("radar"):
        if solo_anos or len(te) < MIN_NOCHES_RADAR:
            continue
        fold(ds[ds["radar"] != r], te, f"radar {r}", "radar")
    return pd.DataFrame(rows), pd.concat(preds, ignore_index=True)


def importance(ds: pd.DataFrame, cols: list[str]) -> pd.DataFrame:  # noqa: D401
    """Ganancia relativa de cada rasgo en los dos modelos, en porcentaje."""
    out = {}
    for nombre, f in (("intensidad", _fit), ("alerta", _fit_alerta)):
        g = pd.Series(f(ds, cols).feature_importance("gain"), index=cols)
        out[nombre] = g / g.sum() * 100
    return pd.DataFrame(out).sort_values("alerta", ascending=False)


def fit_final(ds: pd.DataFrame, cols: list[str], out_dir: Path, prefijo: str = "modelo") -> list[Path]:
    """Entrena con todo y guarda los dos modelos listos para operar."""
    paths = []
    for nombre, f in (("vid", _fit), ("alerta", _fit_alerta)):
        p = out_dir / f"{prefijo}_{nombre}.txt"
        f(ds, cols).save_model(str(p))
        paths.append(p)
    return paths
