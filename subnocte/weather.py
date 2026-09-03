"""Phase 2: historical weather per radar and per-night features.

Two sources, both from Open-Meteo (CC BY 4.0, no key for non-commercial use):

1. **ERA5 reanalysis** (`archive-api`), from 1940: surface and 100 m only. The archive accepts pressure-level
   variables but returns them empty, so it cannot give the wind at flight altitude.
2. **Forecast archive** (`historical-forecast-api`), from 2021: it does serve pressure levels (925, 850 and
   700 hectopascals, i.e. roughly 750, 1,500 and 3,000 m), which is where the birds fly. These are the analyses
   and short-range forecasts of the operational models, not a reanalysis, which also makes training consistent
   with operation: in production the prediction is made from forecasts too.

Wind in the flight layer is the single most important predictor of nocturnal migration, so the main model uses
the pressure levels and is limited to 2021-today; the surface one covers 2016-today and serves as a reference
to measure how much the altitude adds.
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
HOURLY_LEVELS = ([f"{v}_{h}hPa" for h in LEVEL_HPA for v in ("wind_speed", "wind_direction")]
                 + ["temperature_850hPa", "geopotential_height_850hPa"])
LEVELS_YEAR0 = 2021  # the forecast archive has no pressure levels before 2021
PAUSE_S = 1.0        # courtesy towards the free service
RETRIES = 14
BACKOFF_S = 90       # the free quota renews by the minute and by the hour
BACKOFF_MAX_S = 900  # once the hourly quota is exhausted the wait is real, retrying in a loop does not help

# Direction most birds migrate towards in western Europe (degrees, where they head to)
HEADING = {"spring": 30.0, "autumn": 210.0}


def _until_next_hour() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    nxt = (now + dt.timedelta(hours=1)).replace(minute=0, second=30, microsecond=0)
    return max(int((nxt - now).total_seconds()), 60)


def _chunks(years: list[int], maximum: int) -> list[tuple[int, int]]:
    """Group consecutive years into chunks of at most `maximum` years, to make fewer requests."""
    chunks: list[tuple[int, int]] = []
    for y in sorted(years):
        if chunks and y == chunks[-1][1] + 1 and chunks[-1][1] - chunks[-1][0] + 1 < maximum:
            chunks[-1] = (chunks[-1][0], y)
        else:
            chunks.append((y, y))
    return chunks


def fetch_hourly(lat: float, lon: float, start: dt.date, end: dt.date, url: str = ARCHIVE,
                 hourly: list[str] | None = None, log=print) -> pd.DataFrame:
    params = {"latitude": lat, "longitude": lon, "start_date": start.isoformat(), "end_date": end.isoformat(),
              "hourly": ",".join(hourly or HOURLY), "timezone": "UTC", "wind_speed_unit": "ms"}
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, params=params, timeout=300)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.RequestException(f"HTTP {r.status_code}")
            r.raise_for_status()
            j = r.json()
            if "hourly" in j:
                break
            # quota exhausted or another logical error: arrives as 200 with an error flag and a reason
            raise requests.RequestException(j.get("reason", "response without hourly data"))
        except requests.RequestException as e:
            if attempt == RETRIES - 1:
                raise
            msg = str(e).lower()
            # the hourly quota renews on the hour; retrying earlier only burns attempts. A 429 can also be the
            # per-minute limit, so the first retry is short and from the second one it waits for the hour.
            if "hourly api request limit" in msg or ("429" in msg and attempt >= 1):
                wait = _until_next_hour()
            else:
                wait = min(BACKOFF_S * (attempt + 1), BACKOFF_MAX_S)
            log(f"  Open-Meteo: {e}; retrying in {wait} s")
            time.sleep(wait)
    df = pd.DataFrame(j["hourly"])
    df["time"] = pd.to_datetime(df.pop("time"), utc=True)
    return df


# Migration windows with three days of margin on each side (the margin allows the 24 h trends)
WINDOWS = (((2, 12), (6, 3)), ((8, 12), (12, 3)))


def _year_windows(y: int) -> list[tuple[dt.date, dt.date]]:
    return [(dt.date(y, m0, d0), dt.date(y, m1, d1)) for (m0, d0), (m1, d1) in WINDOWS]


def fetch_radar_weather(radar: str, lat: float, lon: float, years: list[int], out_dir: Path, log=print,
                        url: str = ARCHIVE, hourly: list[str] | None = None, delay_days: int = 6,
                        years_per_request: int = 1, seasons_only: bool = False) -> pd.DataFrame:
    """Download in chunks and save `{out_dir}/{radar}.parquet`.

    The free quota is measured by data volume, not by number of requests, so there are two levers: asking for
    several years at once (fewer requests, same volume) and, with `seasons_only`, asking only for the two
    migration windows, which is all the model uses and cuts the volume by 40 %.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{radar}.parquet"
    frames = [pd.read_parquet(dest)] if dest.exists() else []
    today = dt.datetime.now(dt.timezone.utc).date()
    cap = today - dt.timedelta(days=delay_days)
    if seasons_only:
        days = set(frames[0]["time"].dt.date) if frames else set()
        pending = []
        for y in sorted(years):
            for a, b in _year_windows(y):
                b = min(b, cap)
                if b < a:
                    continue
                # an already downloaded window has practically all its days; if over 10 % is missing, redo it
                expected = (b - a).days + 1
                if sum((a + dt.timedelta(days=i)) in days for i in range(expected)) >= 0.9 * expected:
                    continue
                pending.append((a, b))
    else:
        have = set(frames[0]["time"].dt.year) if frames else set()
        pending = []
        for y0, y1 in _chunks([y for y in years if y not in have], years_per_request):
            b = min(dt.date(y1, 12, 31), cap)
            if b >= dt.date(y0, 1, 1):
                pending.append((dt.date(y0, 1, 1), b))
    for a, b in pending:
        df = fetch_hourly(lat, lon, a, b, url=url, hourly=hourly, log=log)
        df.insert(0, "radar", radar)
        frames.append(df)
        log(f"  {radar} {a}/{b}: {len(df):,} hours")
        m = pd.concat(frames, ignore_index=True).drop_duplicates("time").sort_values("time").reset_index(drop=True)
        m.to_parquet(dest, index=False)  # after every chunk, so no progress is lost if the process dies
        time.sleep(PAUSE_S)
    return pd.read_parquet(dest) if dest.exists() else pd.DataFrame()


def fetch_radar_levels(radar: str, lat: float, lon: float, years: list[int], out_dir: Path, log=print) -> pd.DataFrame:
    """Wind and temperature on pressure levels (flight altitude), available from 2021."""
    years = [y for y in years if y >= LEVELS_YEAR0]
    return fetch_radar_weather(radar, lat, lon, years, out_dir, log=log, url=ARCHIVE_LEVELS, hourly=HOURLY_LEVELS,
                               delay_days=1, seasons_only=True)


def _wind_components(speed: pd.Series, direction_from: pd.Series, heading_to: float) -> tuple[pd.Series, pd.Series]:
    """Tailwind component (positive = pushes towards `heading_to`) and crosswind, in m/s.

    The meteorological direction says where the wind comes from; the motion vector of the air goes the other way.
    """
    to = np.deg2rad((direction_from + 180.0) % 360.0)
    h = np.deg2rad(heading_to)
    tail = speed * np.cos(to - h)
    cross = speed * np.sin(to - h)
    return tail, cross


def available_levels(columns) -> list[str]:
    """Levels with wind in the table: 10m, 100m, 850hPa… in the order they appear."""
    return [m.group(1) for c in columns if (m := re.fullmatch(r"wind_speed_(\w+)", str(c)))]


def night_features(weather: pd.DataFrame, nights: pd.DataFrame, levels: pd.DataFrame | None = None) -> pd.DataFrame:
    """One record per night with the weather of the night window and of the previous day.

    nights: the radar nightly table with `night`, `first`, `last` (UTC instants of the first and last profile).
    The [first, last] window is summarised by its mean, plus the value at the start (twilight + 1 h), and 24 h
    trends of pressure and temperature (frontal passage) are added, the classic BirdCast predictors.
    """
    m = weather.set_index("time").sort_index()
    if levels is not None and not levels.empty:
        m = m.join(levels.set_index("time").sort_index().drop(columns=["radar"], errors="ignore"), how="left")
    lvls = available_levels(m.columns)
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
        season = "spring" if night.month <= 7 else "autumn"
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
