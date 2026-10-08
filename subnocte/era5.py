"""ERA5 reanalysis from the Copernicus Climate Data Store, as a quota-free archive for the wind zones.

Open-Meteo counts every point as a separate request, so 150 zones over five seasons do not fit in its free
quota. ERA5 is downloaded once per month as a box that covers every zone, and then read at each zone's point.
The result has the same columns and units as the Open-Meteo archive (`weather.HOURLY` + `HOURLY_LEVELS`), so
`features`, `predict` and `night_power` run on it unchanged.

ERA5 is a reanalysis, not an archived forecast: smoother and without forecast errors. The models were trained
on Open-Meteo's forecast archive, so before using ERA5 thresholds compare both sources on the zones that have
both (`wind-compare`).

Needs a CDS account with the licences of the two ERA5 datasets accepted, and the token in `~/.cdsapirc`.
"""

from __future__ import annotations

import calendar
import datetime as dt
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .weather import WINDOWS

SINGLE = "reanalysis-era5-single-levels"
LEVELS = "reanalysis-era5-pressure-levels"
SINGLE_VARS = ["2m_temperature", "2m_dewpoint_temperature", "surface_pressure", "mean_sea_level_pressure",
               "total_precipitation", "total_cloud_cover", "10m_u_component_of_wind", "10m_v_component_of_wind",
               "100m_u_component_of_wind", "100m_v_component_of_wind"]
LEVEL_VARS = ["u_component_of_wind", "v_component_of_wind", "temperature", "geopotential"]
LEVEL_HPA = ("700", "850", "925")
AREA = [44.25, -9.75, 35.5, 4.75]  # N, W, S, E: the wind zones' box plus one grid cell
DELAY_DAYS = 6                     # ERA5T reaches about five days back from today
WORKERS = 3                        # the CDS queues each user's requests; a few in flight is enough
G = 9.80665


def months(years: list[int], today: dt.date | None = None) -> list[tuple[int, int, list[int]]]:
    """(year, month, days) touching the migration windows, up to the last day ERA5 already has."""
    cap = (today or dt.date.today()) - dt.timedelta(days=DELAY_DAYS)
    out = []
    for y in years:
        for (m0, _), (m1, _) in WINDOWS:
            for m in range(m0, m1 + 1):
                last = calendar.monthrange(y, m)[1]
                days = [d for d in range(1, last + 1) if dt.date(y, m, d) <= cap]
                if days:
                    out.append((y, m, days))
    return out


def _request(y: int, m: int, days: list[int], levels: bool) -> dict:
    q = {"product_type": ["reanalysis"], "year": [str(y)], "month": [f"{m:02d}"],
         "day": [f"{d:02d}" for d in days], "time": [f"{h:02d}:00" for h in range(24)],
         "area": AREA, "data_format": "netcdf", "download_format": "unarchived"}
    if levels:
        q |= {"variable": LEVEL_VARS, "pressure_level": list(LEVEL_HPA)}
    else:
        q |= {"variable": SINGLE_VARS}
    return q


def _target(cache_dir: Path, y: int, m: int, levels: bool) -> Path:
    return cache_dir / f"{'levels' if levels else 'single'}_{y}{m:02d}.nc"


def download(years: list[int], cache_dir: Path, log=print) -> list[tuple[int, int]]:
    """Fetch every missing month (both datasets) into `cache_dir`; returns the months that are complete.

    A month already on disk is kept, except the latest one, which is fetched again while ERA5 is still adding
    its last days.
    """
    import cdsapi

    cache_dir.mkdir(parents=True, exist_ok=True)
    todo = months(years)
    full = {(y, m) for y, m, days in todo if len(days) == calendar.monthrange(y, m)[1]}
    jobs = [(y, m, days, lv) for y, m, days in todo for lv in (False, True)
            if not _target(cache_dir, y, m, lv).exists() or (y, m) not in full]
    log(f"ERA5: {len(todo)} months, {len(jobs)} requests to make")
    client = cdsapi.Client(quiet=True, progress=False)

    def fetch(job):
        y, m, days, lv = job
        dest = _target(cache_dir, y, m, lv)
        tmp = dest.with_suffix(".part")
        client.retrieve(LEVELS if lv else SINGLE, _request(y, m, days, lv), str(tmp))
        tmp.replace(dest)  # only a finished file gets the final name
        log(f"  {dest.name}: {dest.stat().st_size / 1e6:.0f} MB")

    with ThreadPoolExecutor(WORKERS) as ex:
        for _ in ex.map(fetch, jobs):
            pass
    return [(y, m) for y, m, _ in todo]


def _open(path: Path):
    """One ERA5 file as a dataset; the CDS zips instant and accumulated fields together when both are asked for."""
    import xarray as xr

    if zipfile.is_zipfile(path):
        out = path.with_suffix("")
        with zipfile.ZipFile(path) as z:
            z.extractall(out)
        ds = xr.merge([xr.open_dataset(f).load() for f in sorted(out.glob("*.nc"))], compat="override")
    else:
        ds = xr.open_dataset(path).load()
    ds = ds.rename({k: v for k, v in {"valid_time": "time", "pressure_level": "level"}.items() if k in ds.dims})
    return ds.drop_vars([c for c in ("number", "expver") if c in ds.coords or c in ds.data_vars])


def _wind(u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Speed (m/s) and the direction the wind blows from (degrees), as Open-Meteo gives them."""
    return np.hypot(u, v), np.mod(180 + np.degrees(np.arctan2(u, v)), 360)


def _humidity(t_c: np.ndarray, td_c: np.ndarray) -> np.ndarray:
    """Relative humidity (%) from temperature and dew point (Magnus formula, Alduchov and Eskridge 1996)."""
    a, b = 17.625, 243.04
    return np.clip(100 * np.exp(a * td_c / (b + td_c) - a * t_c / (b + t_c)), 0, 100)


def at_points(single, levels, points: pd.DataFrame) -> pd.DataFrame:
    """Hourly table in Open-Meteo's columns at each point (`zone`, `lat`, `lon`), bilinear between grid cells."""
    import xarray as xr

    where = {"latitude": xr.DataArray(points["lat"].to_numpy(), dims="p"),
             "longitude": xr.DataArray(points["lon"].to_numpy(), dims="p")}
    s = single.interp(where).transpose("time", "p")
    lv = levels.interp(where).transpose("time", "level", "p")
    t2 = s["t2m"].values - 273.15
    cols = {
        "temperature_2m": t2,
        "relative_humidity_2m": _humidity(t2, s["d2m"].values - 273.15),
        "surface_pressure": s["sp"].values / 100,
        "pressure_msl": s["msl"].values / 100,
        "precipitation": np.maximum(s["tp"].values * 1000, 0),
        "cloud_cover": s["tcc"].values * 100,
    }
    for h, (u, v) in {"10m": ("u10", "v10"), "100m": ("u100", "v100")}.items():
        cols[f"wind_speed_{h}"], cols[f"wind_direction_{h}"] = _wind(s[u].values, s[v].values)
    for p in LEVEL_HPA:
        q = lv.sel(level=float(p))
        cols[f"wind_speed_{p}hPa"], cols[f"wind_direction_{p}hPa"] = _wind(q["u"].values, q["v"].values)
    q = lv.sel(level=850.0)
    cols["temperature_850hPa"] = q["t"].values - 273.15
    cols["geopotential_height_850hPa"] = q["z"].values / G

    time = pd.DatetimeIndex(s["time"].values).tz_localize("UTC")
    n_t, n_p = len(time), len(points)
    df = pd.DataFrame({k: np.asarray(v, dtype="float32").reshape(n_t, n_p).ravel() for k, v in cols.items()})
    df.insert(0, "radar", np.tile(points["zone"].to_numpy(), n_t))
    df["time"] = np.repeat(time, n_p)
    return df


def _in_windows(t: pd.Series) -> pd.Series:
    md = t.dt.month * 100 + t.dt.day
    return pd.concat([md.between(m0 * 100 + d0, m1 * 100 + d1) for (m0, d0), (m1, d1) in WINDOWS], axis=1).any(axis=1)


def build(points: pd.DataFrame, month_list: list[tuple[int, int]], cache_dir: Path, out_dir: Path,
          log=print) -> int:
    """Read every month at every point and write `{out_dir}/{zone}.parquet`, as `fetch_archive` would."""
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    for y, m in month_list:
        a, b = _target(cache_dir, y, m, False), _target(cache_dir, y, m, True)
        if not (a.exists() and b.exists()):
            log(f"  {y}-{m:02d}: missing, skipped")
            continue
        df = at_points(_open(a), _open(b), points)
        parts.append(df[_in_windows(df["time"])])
    if not parts:
        return 0
    allz = pd.concat(parts, ignore_index=True).sort_values(["radar", "time"])
    for zone, g in allz.groupby("radar", sort=False):
        g.drop_duplicates("time").reset_index(drop=True).to_parquet(out_dir / f"{zone}.parquet", index=False)
    log(f"ERA5: {allz['radar'].nunique()} zones, {len(allz):,} zone-hours")
    return allz["radar"].nunique()
