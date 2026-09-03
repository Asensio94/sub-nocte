"""From vertical profiles (5-10 min × 200 m layers) to a radar × night table.

Definitions (following bioRad / Dokter et al. 2011):
  dens  : bird density (birds/km³) per layer, already derived by vol2bird with RCS = 11 cm²
  ff    : ground speed (m/s) per layer
  VID   : vertically integrated density = Σ dens × thickness (birds/km²)
  MTR   : migration traffic rate = Σ dens × ff × thickness (birds/km/h)
  night MTR : ∫ MTR dt between twilight and dawn (birds/km/night), the unit of BirdCast's alerts
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .solar import sun_elevation

LAYER_KM = 0.2          # vol2bird layer thickness
H_MIN, H_MAX = 200, 3000  # usable layers: below 200 m there is clutter, above 3 km hardly any birds
SD_VVP_MIN = 2.0        # radial-deviation threshold (m/s) below which vol2bird sees no birds (C band)
NIGHT_ELEV = -6.0       # civil twilight
DAY_ELEV = 6.0
FF_FRAC_MIN = 0.5       # minimum share of night density with measured speed for the MTR to be trusted


def clean(df: pd.DataFrame, h_min: int = H_MIN, h_max: int = H_MAX, sd_vvp_min: float = SD_VVP_MIN) -> pd.DataFrame:
    """Filter layers and normalise density.

    In VPTS, `dens` is NaN when vol2bird could not estimate it (few echoes, sd_vvp below threshold, rain).
    Layers with sd_vvp below the threshold are treated as 0 (no bird movement) and the rest are left as NaN,
    which reads as missing data.
    """
    d = df[(df["height"] >= h_min) & (df["height"] < h_max)].copy()
    dens = d["dens"].to_numpy(dtype=float)
    sd = d["sd_vvp"].to_numpy(dtype=float)
    low = np.isfinite(sd) & (sd < sd_vvp_min)
    dens = np.where(low, 0.0, dens)
    d["dens_clean"] = dens
    # a missing ff is NOT zero speed: in several radars (France 2023-2026) vol2bird stops storing the wind
    # fit and only publishes density. Filling with 0 sank the MTR to zero; here it is flagged as missing.
    d["has_ff"] = np.isfinite(d["ff"].to_numpy(dtype=float))
    return d


def profiles(df: pd.DataFrame) -> pd.DataFrame:
    """One record per instant: VID, MTR, mean altitude, valid layers."""
    d = df.copy()
    d["valid"] = np.isfinite(d["dens_clean"])
    d["dens0"] = d["dens_clean"].fillna(0.0)
    d["mtr_layer"] = d["dens0"] * d["ff"].fillna(0.0) * 3.6 * LAYER_KM   # birds/km/h (layers without ff add nothing)
    d["vid_layer"] = d["dens0"] * LAYER_KM                      # birds/km²
    d["dens_with_ff"] = np.where(d["has_ff"], d["dens0"], 0.0)
    d["h_w"] = d["dens0"] * d["height"]
    g = d.groupby("datetime", sort=True)
    out = pd.DataFrame({
        "n_layers": g["valid"].sum(),
        "vid": g["vid_layer"].sum(),
        "mtr": g["mtr_layer"].sum(),
        "h_w": g["h_w"].sum(),
        "dens_sum": g["dens0"].sum(),
        "dens_mean": g["dens0"].mean(),
        "dens_with_ff": g["dens_with_ff"].sum(),
    })
    out["alt_mean"] = np.where(out["dens_sum"] > 0, out["h_w"] / out["dens_sum"], np.nan)
    # share of the profile's density that has a measured speed: without it the MTR is underestimated
    out["ff_frac"] = np.where(out["dens_sum"] > 0, out["dens_with_ff"] / out["dens_sum"], np.nan)
    out = out.drop(columns=["h_w", "dens_sum", "dens_with_ff"]).reset_index()
    return out


def add_night(p: pd.DataFrame, lat: float, lon: float) -> pd.DataFrame:
    p = p.copy()
    p["sun_elev"] = sun_elevation(lat, lon, p["datetime"])
    p["is_night"] = p["sun_elev"] < NIGHT_ELEV
    p["is_day"] = p["sun_elev"] > DAY_ELEV
    # a night is labelled with the date of its sunset: instants before noon UTC belong to the previous day
    p["night"] = (p["datetime"] - pd.Timedelta(hours=12)).dt.date
    return p


def nightly(p: pd.DataFrame, radar: str) -> pd.DataFrame:
    """Radar × night table built from the profiles once they carry a night label."""
    if p.empty:
        return pd.DataFrame()
    step_h = p["datetime"].diff().dt.total_seconds().median() / 3600.0
    night = p[p["is_night"]]
    day = p[p["is_day"]]
    if night.empty:  # radars with daytime scans only (e.g. esgrm in 2026)
        return pd.DataFrame()
    gn = night.groupby("night")
    gd = day.groupby("night")
    out = pd.DataFrame({
        "n_profiles": gn.size(),
        "mtr_night": gn["mtr"].sum() * step_h,             # birds/km/night
        "mtr_peak": gn["mtr"].max(),                       # peak birds/km/h
        "vid_mean": gn["vid"].mean(),
        "alt_mean": gn.apply(lambda x: np.average(x["alt_mean"].fillna(0), weights=x["vid"] + 1e-9)),
        "dens_night": gn["dens_mean"].mean(),
        "vid_night": gn["vid"].mean(),                     # mean birds/km² of the night (needs no speed)
        "ff_frac": gn.apply(lambda x: np.average(x["ff_frac"].fillna(0), weights=x["vid"] + 1e-9)),
        "first": gn["datetime"].min(),
        "last": gn["datetime"].max(),
    })
    out["dens_day"] = gd["dens_mean"].mean()
    out["hours_night"] = out["n_profiles"] * step_h
    # nominal night: span between the first and last night profile plus one step
    dur = (out["last"] - out["first"]).dt.total_seconds() / 3600.0 + step_h
    out["coverage"] = (out["hours_night"] / dur).clip(upper=1.0)
    out.insert(0, "radar", radar)
    out = out.reset_index().rename(columns={"night": "night"})
    out["night"] = pd.to_datetime(out["night"])
    out["step_min"] = round(step_h * 60)
    # without speed for at least half the density the MTR is not interpretable: it is flagged as missing
    out.loc[out["ff_frac"] < FF_FRAC_MIN, "mtr_night"] = np.nan
    out.loc[out["ff_frac"] < FF_FRAC_MIN, "mtr_peak"] = np.nan
    return out


def radar_position(df: pd.DataFrame) -> tuple[float, float]:
    return float(df["radar_latitude"].dropna().iloc[0]), float(df["radar_longitude"].dropna().iloc[0])


def build_nightly(df: pd.DataFrame, radar: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (profiles with a night label, nightly table)."""
    lat, lon = radar_position(df)
    p = add_night(profiles(clean(df)), lat, lon)
    n = nightly(p, radar)
    n["lat"], n["lon"] = lat, lon
    return p, n
