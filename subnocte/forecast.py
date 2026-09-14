"""Phase 3: operational forecast per city.

Phase 2 showed that the weather predicts the intensity of the nocturnal passage at a point **without a radar**:
leaving whole radars out, the model captured 34 % of the heavy-passage nights against the 10 % of chance. Here
that becomes a service: instead of reanalyses of the past, the model is fed the **forecast** of the coming days
at the coordinates of each city.

Three pieces:

1. **Theoretical night window.** Without a radar there are no profiles to say when the night starts and ends, so
   it is computed from the solar elevation: the night is the stretch with the sun below civil twilight (-6°), the
   same definition the radar nights were built with.
2. **Operational model.** The two phase 2 models retrained without the local climatology features, which in a
   city without a radar do not exist. It is exactly the configuration validated by leaving radars out.
3. **A threshold of each city's own, moving through the year.** The model gives a continuous number; to switch
   the alert on it takes knowing what counts as a lot *there* and *then*. The model is run over the weather
   archive from 2021 onwards at the city's point, and the percentiles are taken over the nights around the same
   date rather than over the whole season. That way the alert means the same thing in Sevilla and in Bilbao, and
   it still means something at the peak of the passage, when every night beats the seasonal median.

Training and operation draw on the same family of data (the Open-Meteo operational model), which is what makes
the thresholds computed over the archive valid for the forecast.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from .history import SEASONS, season_mask
from .weather import (ARCHIVE_LEVELS, HOURLY, HOURLY_LEVELS, LEVELS_YEAR0, fetch_hourly, fetch_radar_weather,
                      night_features)
from .nightly import NIGHT_ELEV
from .solar import sun_elevation

FORECAST = "https://api.open-meteo.com/v1/forecast"
HOURLY_ALL = HOURLY + HOURLY_LEVELS  # surface and pressure levels in a single request
FORECAST_DAYS = 7

# Percentiles of each city's own prediction distribution that separate the four alert levels.
LEVELS = [(0.90, "very high"), (0.75, "high"), (0.50, "moderate"), (0.0, "low")]
DOY_STEP = 10      # width of the bins the thresholds are stored in, in days
DOY_WINDOW = 21    # half-width of the window each bin's percentiles are taken over
MIN_NIGHTS = 60    # below this the window is too thin to cut percentiles on


def night_windows(name: str, lat: float, lon: float, hours: pd.DatetimeIndex) -> pd.DataFrame:
    """One row per night with the first and last night instant, in the style of the radar table.

    `hours` are the available UTC instants (archive or forecast). Every night is labelled with the date of its
    sunset, just like the radar nights, and nights cut by the edge of the download are discarded.
    """
    h = pd.DatetimeIndex(hours).sort_values()
    night = h[sun_elevation(lat, lon, h) < NIGHT_ELEV]
    if len(night) == 0:
        return pd.DataFrame()
    label = (night - pd.Timedelta(hours=12)).date
    g = pd.DataFrame({"night": pd.to_datetime(label), "t": night}).groupby("night")["t"]
    out = pd.DataFrame({"first": g.min(), "last": g.max(), "hours": g.size()}).reset_index()
    # the nights at both ends are cut by the edge of the download and would give biased means
    out = out[(out["hours"] >= 5) & (out["first"] > h[0]) & (out["last"] < h[-1])]
    out.insert(0, "radar", name)  # the model calls the spatial unit "radar"; here it is the city
    return out.reset_index(drop=True)


def features(name: str, lat: float, lon: float, hourly: pd.DataFrame) -> pd.DataFrame:
    """Per-night features from an hourly table at the city's point."""
    hourly = hourly.copy()
    hourly["time"] = pd.to_datetime(hourly["time"], utc=True)
    nights = night_windows(name, lat, lon, pd.DatetimeIndex(hourly["time"]))
    if nights.empty:
        return pd.DataFrame()
    f = night_features(hourly.assign(radar=name), nights)
    if f.empty:
        return f
    f["doy"] = f["night"].dt.dayofyear
    f["year"] = f["night"].dt.year
    f["doy_sin"] = np.sin(2 * np.pi * f["doy"] / 365.25)
    f["doy_cos"] = np.cos(2 * np.pi * f["doy"] / 365.25)
    f["lat"], f["lon"] = lat, lon
    f["season"] = np.where(season_mask(f["night"], "spring"), "spring",
                           np.where(season_mask(f["night"], "autumn"), "autumn", "off season"))
    return f


def fetch_archive(name: str, lat: float, lon: float, years: list[int], out_dir: Path, log=print) -> pd.DataFrame:
    """Weather archive of the city (surface and flight altitude) inside the migration windows."""
    return fetch_radar_weather(name, lat, lon, [y for y in years if y >= LEVELS_YEAR0], out_dir, log=log,
                               url=ARCHIVE_LEVELS, hourly=HOURLY_ALL, delay_days=1, seasons_only=True)


def fetch_forecast(lat: float, lon: float, days: int = FORECAST_DAYS, log=print) -> pd.DataFrame:
    """Hourly forecast of the coming days at the city's point.

    One day back is requested because the 24 h trends of pressure and temperature need the day before the
    first night.
    """
    today = dt.datetime.now(dt.timezone.utc).date()
    return fetch_hourly(lat, lon, today - dt.timedelta(days=1), today + dt.timedelta(days=days),
                        url=FORECAST, hourly=HOURLY_ALL, log=log)


def load_models(data_dir: Path) -> tuple:
    """The two operational models and the list of features they were trained with."""
    import lightgbm as lgb
    vid = lgb.Booster(model_file=str(data_dir / "model_op_vid.txt"))
    alert = lgb.Booster(model_file=str(data_dir / "model_op_alert.txt"))
    return vid, alert, vid.feature_name()


def predict(f: pd.DataFrame, models: tuple) -> pd.DataFrame:
    vid, alert, cols = models
    f = f.copy()
    for c in [c for c in cols if c not in f.columns]:
        f[c] = np.nan  # a variable the forecast does not carry is left missing: the trees handle it
    return f.assign(pred=vid.predict(f[cols]), p_alert=alert.predict(f[cols]))


def _doy_bin(doy) -> np.ndarray:
    """Index of the bin a day of the year falls in (0 for the first ten days of January)."""
    return (np.asarray(doy) - 1) // DOY_STEP


def _doy_centre(b) -> np.ndarray:
    return np.asarray(b) * DOY_STEP + DOY_STEP // 2


def _doy_gap(a, b) -> np.ndarray:
    """Distance in days between two days of the year, going round the end of December."""
    d = np.abs(np.asarray(a) - np.asarray(b))
    return np.minimum(d, 366 - d)


def compute_thresholds(pred: pd.DataFrame) -> pd.DataFrame:
    """Percentiles of each city's predictions, taken over a window that moves through the year.

    Season-wide percentiles lose their bite at the peak of the passage: in September almost every night
    beats the autumn median, so almost every night comes out as an alert and the level stops telling the
    nights apart. Cutting instead on the nights around the same date keeps the alert answering the
    question it is meant to answer, «is far more passing tonight than is normal here *at this time of
    year*?». The window is +-21 days around the centre of each 10-day bin, so consecutive bins overlap
    and the threshold moves smoothly instead of jumping.

    Both sets are stored: the one of the intensity model, which ranks the nights, and the one of the
    heavy-passage classifier, which is what decides the alert.
    """
    q = [p for p, _ in LEVELS if p > 0]
    rows = []
    for city, g in pred[pred["season"] != "off season"].groupby("radar"):
        doy = g["doy"].to_numpy()
        for b in range(366 // DOY_STEP + 1):
            w = g[_doy_gap(doy, _doy_centre(b)) <= DOY_WINDOW]
            if len(w) < MIN_NIGHTS:
                continue
            row = {"city": city, "season": w["season"].mode().iat[0], "doy_bin": b,
                   "doy_centre": int(_doy_centre(b)), "nights": len(w),
                   "pred_mean": w["pred"].mean(), "p_alert_mean": w["p_alert"].mean()}
            for p in q:
                row[f"pred_q{int(p * 100)}"] = w["pred"].quantile(p)
                row[f"alert_q{int(p * 100)}"] = w["p_alert"].quantile(p)
            rows.append(row)
    return pd.DataFrame(rows)


def alert_level(p_alert: float, threshold: pd.Series) -> str:
    for q, name in LEVELS:
        if q == 0 or p_alert >= threshold.get(f"alert_q{int(q * 100)}", np.inf):
            return name
    return "low"


def apply_thresholds(pred: pd.DataFrame, thresholds: pd.DataFrame) -> pd.DataFrame:
    """Add the alert level and the night's percentile within the city's own record for this time of year."""
    qs = sorted(q for q, _ in LEVELS if q > 0)
    by_city = {c: g.set_index("doy_bin") for c, g in thresholds.groupby("city")}
    rows = []
    for r in pred.itertuples(index=False):
        g = by_city.get(r.radar)
        if g is None or r.season == "off season":
            rows.append({"level": "no threshold", "percentile": np.nan})
            continue
        b = int(_doy_bin(r.doy))
        if b not in g.index:  # edge of the season: take the nearest bin that does have a threshold
            b = int(min(g.index, key=lambda k: _doy_gap(_doy_centre(k), r.doy)))
        row = g.loc[b]
        pct = 0.0
        for q in qs:
            if r.p_alert >= row[f"alert_q{int(q * 100)}"]:
                pct = q
        rows.append({"level": alert_level(r.p_alert, row), "percentile": pct})
    out = pd.concat([pred.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    return out.assign(city=out["radar"])


def active_season(day: dt.date | None = None) -> str | None:
    day = day or dt.datetime.now(dt.timezone.utc).date()
    md = day.month * 100 + day.day
    for name, ((m1, d1), (m2, d2)) in SEASONS.items():
        if m1 * 100 + d1 <= md <= m2 * 100 + d2:
            return name
    return None
