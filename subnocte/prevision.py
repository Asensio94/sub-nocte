"""Fase 3: previsión operativa por ciudad.

La fase 2 dejó demostrado que la meteorología predice la intensidad del paso nocturno en un punto **sin radar**:
dejando fuera radares enteros, el modelo capturaba un 34 % de las noches de paso fuerte frente al 10 % del azar.
Aquí se convierte eso en un servicio: en vez de reanálisis del pasado se le da al modelo el **pronóstico** de los
próximos días en las coordenadas de cada ciudad.

Tres piezas:

1. **Ventana nocturna teórica.** Sin radar no hay perfiles que digan cuándo empieza y acaba la noche, así que se
   calcula con la elevación del sol: la noche es el tramo con el sol por debajo del crepúsculo civil (-6°), la
   misma definición con la que se construyeron las noches de radar.
2. **Modelo operativo.** Los dos modelos de la fase 2 reentrenados sin los rasgos de climatología local, que en
   una ciudad sin radar no existen. Es exactamente la configuración que se validó dejando radares fuera.
3. **Umbral propio de cada ciudad.** El modelo da un número continuo; para encender el aviso hace falta saber qué
   es mucho *ahí*. Se corre el modelo sobre el archivo meteorológico de 2021 en adelante en el punto de la ciudad
   y se toman los percentiles de sus propias predicciones. Así el aviso significa lo mismo en Sevilla y en Bilbao.

La fuente es la misma familia de datos en el entrenamiento y en la operación (el modelo operativo de Open-Meteo),
que es lo que hace que los umbrales calculados sobre el archivo valgan para el pronóstico.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from .historico import SEASONS, season_mask
from .meteo import (ARCHIVE_LEVELS, HOURLY, HOURLY_LEVELS, LEVELS_YEAR0, fetch_hourly, fetch_radar_meteo,
                    night_features)
from .nightly import NIGHT_ELEV
from .solar import sun_elevation

FORECAST = "https://api.open-meteo.com/v1/forecast"
HOURLY_TODO = HOURLY + HOURLY_LEVELS  # superficie y niveles de presión en una sola petición
DIAS_PREVISION = 7

# Percentiles de la distribución de predicciones de cada ciudad que separan los cuatro niveles de aviso.
NIVELES = [(0.90, "muy alto"), (0.75, "alto"), (0.50, "moderado"), (0.0, "bajo")]


def ventanas_nocturnas(nombre: str, lat: float, lon: float, horas: pd.DatetimeIndex) -> pd.DataFrame:
    """Una fila por noche con el primer y último instante nocturno, al estilo de la tabla de radar.

    `horas` son los instantes UTC disponibles (archivo o pronóstico). Se etiqueta cada noche con la fecha de su
    atardecer, igual que en las noches de radar, y se descartan las noches cortadas por el borde de la descarga.
    """
    h = pd.DatetimeIndex(horas).sort_values()
    noche = h[sun_elevation(lat, lon, h) < NIGHT_ELEV]
    if len(noche) == 0:
        return pd.DataFrame()
    etiqueta = (noche - pd.Timedelta(hours=12)).date
    g = pd.DataFrame({"night": pd.to_datetime(etiqueta), "t": noche}).groupby("night")["t"]
    out = pd.DataFrame({"first": g.min(), "last": g.max(), "horas": g.size()}).reset_index()
    # las noches de los dos extremos están cortadas por el borde de la descarga y darían medias sesgadas
    out = out[(out["horas"] >= 5) & (out["first"] > h[0]) & (out["last"] < h[-1])]
    out.insert(0, "radar", nombre)  # el modelo llama "radar" a la unidad espacial; aquí es la ciudad
    return out.reset_index(drop=True)


def rasgos(nombre: str, lat: float, lon: float, horario: pd.DataFrame) -> pd.DataFrame:
    """Rasgos por noche a partir de una tabla horaria en el punto de la ciudad."""
    horario = horario.copy()
    horario["time"] = pd.to_datetime(horario["time"], utc=True)
    noches = ventanas_nocturnas(nombre, lat, lon, pd.DatetimeIndex(horario["time"]))
    if noches.empty:
        return pd.DataFrame()
    f = night_features(horario.assign(radar=nombre), noches)
    if f.empty:
        return f
    f["doy"] = f["night"].dt.dayofyear
    f["year"] = f["night"].dt.year
    f["doy_sin"] = np.sin(2 * np.pi * f["doy"] / 365.25)
    f["doy_cos"] = np.cos(2 * np.pi * f["doy"] / 365.25)
    f["lat"], f["lon"] = lat, lon
    f["season"] = np.where(season_mask(f["night"], "primavera"), "primavera",
                           np.where(season_mask(f["night"], "otoño"), "otoño", "fuera de temporada"))
    return f


def descargar_archivo(nombre: str, lat: float, lon: float, years: list[int], out_dir: Path, log=print) -> pd.DataFrame:
    """Archivo meteorológico de la ciudad (superficie y altura de vuelo) en las ventanas migratorias."""
    return fetch_radar_meteo(nombre, lat, lon, [y for y in years if y >= LEVELS_YEAR0], out_dir, log=log,
                             url=ARCHIVE_LEVELS, hourly=HOURLY_TODO, retraso_dias=1, solo_temporadas=True)


def descargar_prevision(lat: float, lon: float, dias: int = DIAS_PREVISION, log=print) -> pd.DataFrame:
    """Pronóstico horario de los próximos días en el punto de la ciudad.

    Se pide un día hacia atrás porque las tendencias de 24 h de presión y temperatura necesitan el día anterior
    a la primera noche.
    """
    hoy = dt.datetime.now(dt.timezone.utc).date()
    return fetch_hourly(lat, lon, hoy - dt.timedelta(days=1), hoy + dt.timedelta(days=dias),
                        url=FORECAST, hourly=HOURLY_TODO, log=log)


def cargar_modelos(data_dir: Path) -> tuple:
    """Los dos modelos operativos y la lista de rasgos con la que se entrenaron."""
    import lightgbm as lgb
    vid = lgb.Booster(model_file=str(data_dir / "modelo_op_vid.txt"))
    alerta = lgb.Booster(model_file=str(data_dir / "modelo_op_alerta.txt"))
    return vid, alerta, vid.feature_name()


def predecir(f: pd.DataFrame, modelos: tuple) -> pd.DataFrame:
    vid, alerta, cols = modelos
    f = f.copy()
    for c in [c for c in cols if c not in f.columns]:
        f[c] = np.nan  # una variable que el pronóstico no traiga se deja ausente: los árboles la manejan
    return f.assign(pred=vid.predict(f[cols]), p_alerta=alerta.predict(f[cols]))


def calcular_umbrales(pred: pd.DataFrame) -> pd.DataFrame:
    """Percentiles de las predicciones de cada ciudad y temporada, que definen los niveles de aviso.

    Se guardan los dos: el del modelo de intensidad, que ordena las noches, y el del clasificador de paso fuerte,
    que es el que decide el aviso.
    """
    q = [p for p, _ in NIVELES if p > 0]
    filas = []
    for (ciudad, temporada), g in pred[pred["season"] != "fuera de temporada"].groupby(["radar", "season"]):
        if len(g) < 100:
            continue
        fila = {"ciudad": ciudad, "season": temporada, "noches": len(g),
                "pred_media": g["pred"].mean(), "p_alerta_media": g["p_alerta"].mean()}
        for p in q:
            fila[f"pred_q{int(p * 100)}"] = g["pred"].quantile(p)
            fila[f"alerta_q{int(p * 100)}"] = g["p_alerta"].quantile(p)
        filas.append(fila)
    return pd.DataFrame(filas)


def nivel_aviso(p_alerta: float, umbral: pd.Series) -> str:
    for q, nombre in NIVELES:
        if q == 0 or p_alerta >= umbral.get(f"alerta_q{int(q * 100)}", np.inf):
            return nombre
    return "bajo"


def aplicar_umbrales(pred: pd.DataFrame, umbrales: pd.DataFrame) -> pd.DataFrame:
    """Añade el nivel de aviso y el percentil de la noche dentro del historial de la propia ciudad."""
    u = umbrales.set_index(["ciudad", "season"])
    qs = sorted(q for q, _ in NIVELES if q > 0)
    filas = []
    for r in pred.itertuples(index=False):
        clave = (r.radar, r.season)
        if clave not in u.index:
            filas.append({"nivel": "sin umbral", "percentil": np.nan})
            continue
        fila = u.loc[clave]
        pct = 0.0
        for q in qs:
            if r.p_alerta >= fila[f"alerta_q{int(q * 100)}"]:
                pct = q
        filas.append({"nivel": nivel_aviso(r.p_alerta, fila), "percentil": pct})
    out = pd.concat([pred.reset_index(drop=True), pd.DataFrame(filas)], axis=1)
    return out.assign(ciudad=out["radar"])


def temporada_activa(dia: dt.date | None = None) -> str | None:
    dia = dia or dt.datetime.now(dt.timezone.utc).date()
    md = dia.month * 100 + dia.day
    for nombre, ((m1, d1), (m2, d2)) in SEASONS.items():
        if m1 * 100 + d1 <= md <= m2 * 100 + d2:
            return nombre
    return None
