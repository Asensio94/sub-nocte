"""Fase 2: meteorología histórica por radar y rasgos por noche.

Dos fuentes, ambas de Open-Meteo (CC BY 4.0, sin clave para uso no comercial):

1. **Reanálisis ERA5** (`archive-api`), desde 1940: solo superficie y 100 m. El archivo acepta variables en
   niveles de presión pero las devuelve vacías, así que no sirve para el viento a altura de vuelo.
2. **Archivo de pronósticos** (`historical-forecast-api`), desde 2021: sí sirve niveles de presión (925, 850 y
   700 hectopascales, es decir unos 750, 1.500 y 3.000 m), que es donde vuelan las aves. Son los análisis y
   pronósticos a corto plazo de los modelos operativos, no un reanálisis, lo que además hace el entrenamiento
   coherente con la operación: en producción también se predice con pronósticos.

El viento en la capa de vuelo es el predictor más importante de la migración nocturna, así que el modelo
principal usa los niveles de presión y se limita a 2021-hoy; el de superficie cubre 2016-hoy y sirve de
referencia para medir cuánto aporta la altura.
"""

from __future__ import annotations

import datetime as dt
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
ARCHIVE_LEVELS = "https://historical-forecast-api.open-meteo.com/v1/forecast"
HOURLY = [
    "temperature_2m", "relative_humidity_2m", "surface_pressure", "pressure_msl", "precipitation", "cloud_cover",
    "wind_speed_10m", "wind_direction_10m", "wind_speed_100m", "wind_direction_100m",
]
LEVEL_HPA = (925, 850, 700)
HOURLY_LEVELS = [f"{v}_{h}hPa" for h in LEVEL_HPA for v in ("wind_speed", "wind_direction")] + \
                ["temperature_850hPa", "geopotential_height_850hPa"]
LEVELS_YEAR0 = 2021  # el archivo de pronósticos no tiene niveles de presión antes de 2021
PAUSE_S = 1.0        # cortesía con el servicio gratuito
RETRIES = 8
BACKOFF_S = 90       # la cuota gratuita se renueva por minuto y por hora

# Dirección hacia la que migra el grueso de las aves en Europa occidental (grados, hacia dónde)
HEADING = {"primavera": 30.0, "otoño": 210.0}


def fetch_hourly(lat: float, lon: float, start: dt.date, end: dt.date, url: str = ARCHIVE,
                 hourly: list[str] | None = None, log=print) -> pd.DataFrame:
    params = {"latitude": lat, "longitude": lon, "start_date": start.isoformat(), "end_date": end.isoformat(),
              "hourly": ",".join(hourly or HOURLY), "timezone": "UTC", "wind_speed_unit": "ms"}
    for intento in range(RETRIES):
        try:
            r = requests.get(url, params=params, timeout=300)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.RequestException(f"HTTP {r.status_code}")
            r.raise_for_status()
            j = r.json()
            if "hourly" in j:
                break
            # cuota agotada u otro error lógico: llega con 200 y {"error": true, "reason": "..."}
            raise requests.RequestException(j.get("reason", "respuesta sin 'hourly'"))
        except requests.RequestException as e:
            if intento == RETRIES - 1:
                raise
            espera = BACKOFF_S * (intento + 1)
            log(f"  Open-Meteo: {e}; reintento en {espera} s")
            time.sleep(espera)
    df = pd.DataFrame(j["hourly"])
    df["time"] = pd.to_datetime(df.pop("time"), utc=True)
    return df


def fetch_radar_meteo(radar: str, lat: float, lon: float, years: list[int], out_dir: Path, log=print,
                      url: str = ARCHIVE, hourly: list[str] | None = None, retraso_dias: int = 6) -> pd.DataFrame:
    """Descarga año a año (unas 9.000 horas por año) y guarda `{out_dir}/{radar}.parquet`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{radar}.parquet"
    frames = [pd.read_parquet(dest)] if dest.exists() else []
    tengo = set(frames[0]["time"].dt.year) if frames else set()
    hoy = dt.datetime.now(dt.timezone.utc).date()
    for y in years:
        if y in tengo:
            continue
        end = min(dt.date(y, 12, 31), hoy - dt.timedelta(days=retraso_dias))
        if end < dt.date(y, 1, 1):
            continue
        df = fetch_hourly(lat, lon, dt.date(y, 1, 1), end, url=url, hourly=hourly, log=log)
        df.insert(0, "radar", radar)
        frames.append(df)
        log(f"  {radar} {y}: {len(df):,} horas")
        m = pd.concat(frames, ignore_index=True).drop_duplicates("time").sort_values("time").reset_index(drop=True)
        m.to_parquet(dest, index=False)  # tras cada año, para no perder el avance si el proceso muere
        time.sleep(PAUSE_S)
    return pd.read_parquet(dest) if dest.exists() else pd.DataFrame()


def fetch_radar_niveles(radar: str, lat: float, lon: float, years: list[int], out_dir: Path, log=print) -> pd.DataFrame:
    """Viento y temperatura en niveles de presión (altura de vuelo), disponibles desde 2021."""
    years = [y for y in years if y >= LEVELS_YEAR0]
    return fetch_radar_meteo(radar, lat, lon, years, out_dir, log=log, url=ARCHIVE_LEVELS, hourly=HOURLY_LEVELS,
                             retraso_dias=1)


def _wind_components(speed: pd.Series, direction_from: pd.Series, heading_to: float) -> tuple[pd.Series, pd.Series]:
    """Componente de viento a favor (positiva = empuja hacia `heading_to`) y lateral, en m/s.

    La dirección meteorológica indica de dónde viene el viento; el vector de movimiento del aire va al contrario.
    """
    to = np.deg2rad((direction_from + 180.0) % 360.0)
    h = np.deg2rad(heading_to)
    tail = speed * np.cos(to - h)
    cross = speed * np.sin(to - h)
    return tail, cross


def niveles_disponibles(columns) -> list[str]:
    """Niveles con viento en la tabla: '10m', '100m', '850hPa'… en el orden en que aparecen."""
    return [m.group(1) for c in columns if (m := re.fullmatch(r"wind_speed_(\w+)", str(c)))]


def night_features(meteo: pd.DataFrame, nights: pd.DataFrame, niveles: pd.DataFrame | None = None) -> pd.DataFrame:
    """Un registro por noche con la meteorología de la ventana nocturna y del día anterior.

    nights: tabla nocturna del radar con `night`, `first`, `last` (instantes UTC del primer y último perfil).
    Se resume la ventana [first, last] con la media, más el valor al inicio (crepúsculo + 1 h), y se añaden
    tendencias de 24 h de presión y temperatura (paso de frentes), que son los predictores clásicos de BirdCast.
    """
    m = meteo.set_index("time").sort_index()
    if niveles is not None and not niveles.empty:
        m = m.join(niveles.set_index("time").sort_index().drop(columns=["radar"], errors="ignore"), how="left")
    lvls = niveles_disponibles(m.columns)
    rows = []
    for r in nights.itertuples(index=False):
        first, last = pd.Timestamp(r.first), pd.Timestamp(r.last)
        if pd.isna(first) or pd.isna(last):
            continue
        w = m.loc[first.floor("h"): last.ceil("h")]
        if len(w) < 3:
            continue
        early = m.loc[first.floor("h") + pd.Timedelta(hours=1): first.floor("h") + pd.Timedelta(hours=3)]
        prev = m.loc[first.floor("h") - pd.Timedelta(hours=24): first.floor("h") - pd.Timedelta(hours=22)]
        night = pd.Timestamp(r.night)
        season = "primavera" if night.month <= 7 else "otoño"
        f = {"radar": r.radar, "night": night}
        for lvl in lvls:
            sp, di = w[f"wind_speed_{lvl}"], w[f"wind_direction_{lvl}"]
            if sp.isna().all():
                continue
            tail, cross = _wind_components(sp, di, HEADING[season])
            f[f"ws_{lvl}"] = sp.mean()
            f[f"tail_{lvl}"] = tail.mean()
            f[f"cross_{lvl}"] = cross.abs().mean()
            if not early.empty and not early[f"wind_speed_{lvl}"].isna().all():
                t0, _ = _wind_components(early[f"wind_speed_{lvl}"], early[f"wind_direction_{lvl}"], HEADING[season])
                f[f"tail0_{lvl}"] = t0.mean()
        f["t2m"] = w["temperature_2m"].mean()
        f["rh2m"] = w["relative_humidity_2m"].mean()
        f["pmsl"] = w["pressure_msl"].mean()
        f["precip"] = w["precipitation"].sum()
        f["precip_h"] = (w["precipitation"] > 0.1).mean()
        f["cloud"] = w["cloud_cover"].mean()
        if "temperature_850hPa" in w and not w["temperature_850hPa"].isna().all():
            f["t850"] = w["temperature_850hPa"].mean()
            f["gh850"] = w["geopotential_height_850hPa"].mean()
            if not prev.empty and not prev["temperature_850hPa"].isna().all():
                f["dt850_24"] = f["t850"] - prev["temperature_850hPa"].mean()
        if not prev.empty:
            f["dp24"] = w["pressure_msl"].iloc[:3].mean() - prev["pressure_msl"].mean()
            f["dt24"] = w["temperature_2m"].iloc[:3].mean() - prev["temperature_2m"].mean()
        rows.append(f)
    return pd.DataFrame(rows)
