"""De perfiles verticales (5-10 min × capas de 200 m) a una tabla radar × noche.

Definiciones (siguen a bioRad / Dokter et al. 2011):
  dens  : densidad de aves (aves/km³) por capa, ya derivada por vol2bird con RCS = 11 cm²
  ff    : velocidad terrestre (m/s) por capa
  VID   : densidad integrada verticalmente = Σ dens × espesor (aves/km²)
  MTR   : tasa de tráfico = Σ dens × ff × espesor (aves/km/h)
  MTR noche : ∫ MTR dt entre crepúsculo y amanecer (aves/km/noche), la unidad de las alertas de BirdCast
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .solar import sun_elevation

LAYER_KM = 0.2          # espesor de capa de vol2bird
H_MIN, H_MAX = 200, 3000  # capas útiles: por debajo de 200 m hay clutter; por encima de 3 km apenas hay aves
SD_VVP_MIN = 2.0        # umbral de desviación radial (m/s) bajo el cual vol2bird no considera aves (banda C)
NIGHT_ELEV = -6.0       # crepúsculo civil
DAY_ELEV = 6.0


def clean(df: pd.DataFrame, h_min: int = H_MIN, h_max: int = H_MAX, sd_vvp_min: float = SD_VVP_MIN) -> pd.DataFrame:
    """Filtra capas y normaliza la densidad.

    En VPTS `dens` viene NaN cuando vol2bird no pudo estimar (pocos ecos, sd_vvp bajo el umbral, lluvia).
    Tratamos como 0 las capas con sd_vvp por debajo del umbral (no hay movimiento de aves) y dejamos NaN
    el resto, que se interpreta como dato ausente.
    """
    d = df[(df["height"] >= h_min) & (df["height"] < h_max)].copy()
    dens = d["dens"].to_numpy(dtype=float)
    sd = d["sd_vvp"].to_numpy(dtype=float)
    low = np.isfinite(sd) & (sd < sd_vvp_min)
    dens = np.where(low, 0.0, dens)
    d["dens_clean"] = dens
    d["ff"] = d["ff"].where(np.isfinite(d["ff"]), 0.0)
    return d


def profiles(df: pd.DataFrame) -> pd.DataFrame:
    """Un registro por instante: VID, MTR, altitud media, capas válidas."""
    d = df.copy()
    d["valid"] = np.isfinite(d["dens_clean"])
    d["dens0"] = d["dens_clean"].fillna(0.0)
    d["mtr_layer"] = d["dens0"] * d["ff"] * 3.6 * LAYER_KM   # aves/km/h
    d["vid_layer"] = d["dens0"] * LAYER_KM                      # aves/km²
    d["h_w"] = d["dens0"] * d["height"]
    g = d.groupby("datetime", sort=True)
    out = pd.DataFrame({
        "n_layers": g["valid"].sum(),
        "vid": g["vid_layer"].sum(),
        "mtr": g["mtr_layer"].sum(),
        "h_w": g["h_w"].sum(),
        "dens_sum": g["dens0"].sum(),
        "dens_mean": g["dens0"].mean(),
    })
    out["alt_mean"] = np.where(out["dens_sum"] > 0, out["h_w"] / out["dens_sum"], np.nan)
    out = out.drop(columns=["h_w", "dens_sum"]).reset_index()
    return out


def add_night(p: pd.DataFrame, lat: float, lon: float) -> pd.DataFrame:
    p = p.copy()
    p["sun_elev"] = sun_elevation(lat, lon, p["datetime"])
    p["is_night"] = p["sun_elev"] < NIGHT_ELEV
    p["is_day"] = p["sun_elev"] > DAY_ELEV
    # la noche se etiqueta con la fecha de su atardecer: instantes antes del mediodía UTC pertenecen al día anterior
    p["night"] = (p["datetime"] - pd.Timedelta(hours=12)).dt.date
    return p


def nightly(p: pd.DataFrame, radar: str) -> pd.DataFrame:
    """Tabla radar × noche a partir de los perfiles con etiqueta de noche."""
    if p.empty:
        return pd.DataFrame()
    step_h = p["datetime"].diff().dt.total_seconds().median() / 3600.0
    night = p[p["is_night"]]
    day = p[p["is_day"]]
    if night.empty:  # radares con solo barridos diurnos (p. ej. esgrm en 2026)
        return pd.DataFrame()
    gn = night.groupby("night")
    gd = day.groupby("night")
    out = pd.DataFrame({
        "n_profiles": gn.size(),
        "mtr_night": gn["mtr"].sum() * step_h,             # aves/km/noche
        "mtr_peak": gn["mtr"].max(),                       # aves/km/h máximo
        "vid_mean": gn["vid"].mean(),
        "alt_mean": gn.apply(lambda x: np.average(x["alt_mean"].fillna(0), weights=x["vid"] + 1e-9)),
        "dens_night": gn["dens_mean"].mean(),
        "first": gn["datetime"].min(),
        "last": gn["datetime"].max(),
    })
    out["dens_day"] = gd["dens_mean"].mean()
    out["hours_night"] = out["n_profiles"] * step_h
    # noches teóricas: duración entre el primer y último perfil nocturno más un paso
    dur = (out["last"] - out["first"]).dt.total_seconds() / 3600.0 + step_h
    out["coverage"] = (out["hours_night"] / dur).clip(upper=1.0)
    out.insert(0, "radar", radar)
    out = out.reset_index().rename(columns={"night": "night"})
    out["night"] = pd.to_datetime(out["night"])
    out["step_min"] = round(step_h * 60)
    return out


def radar_position(df: pd.DataFrame) -> tuple[float, float]:
    return float(df["radar_latitude"].dropna().iloc[0]), float(df["radar_longitude"].dropna().iloc[0])


def build_nightly(df: pd.DataFrame, radar: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (perfiles con etiqueta de noche, tabla nocturna)."""
    lat, lon = radar_position(df)
    p = add_night(profiles(clean(df)), lat, lon)
    n = nightly(p, radar)
    n["lat"], n["lon"] = lat, lon
    return p, n
