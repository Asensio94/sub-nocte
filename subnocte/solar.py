"""Approximate solar elevation (simplified NOAA algorithm, error < 0.05°), vectorised with numpy."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sun_elevation(lat: float, lon: float, times: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    """Solar elevation in degrees for UTC instants."""
    t = pd.DatetimeIndex(times)
    if t.tz is None:
        t = t.tz_localize("UTC")
    jd = t.to_julian_date().to_numpy()
    n = jd - 2451545.0
    L = np.mod(280.460 + 0.9856474 * n, 360.0)
    g = np.deg2rad(np.mod(357.528 + 0.9856003 * n, 360.0))
    lam = np.deg2rad(L + 1.915 * np.sin(g) + 0.020 * np.sin(2 * g))
    eps = np.deg2rad(23.439 - 0.0000004 * n)
    ra = np.arctan2(np.cos(eps) * np.sin(lam), np.cos(lam))
    dec = np.arcsin(np.sin(eps) * np.sin(lam))
    gmst = np.mod(18.697374558 + 24.06570982441908 * n, 24.0)
    lst = np.deg2rad(np.mod(gmst * 15.0 + lon, 360.0))
    ha = lst - ra
    phi = np.deg2rad(lat)
    elev = np.arcsin(np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.cos(ha))
    return np.rad2deg(elev)
