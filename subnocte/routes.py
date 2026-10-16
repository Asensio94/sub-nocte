"""Where the birds fly: the migration routes over Iberia and France, from the radars' flight vectors.

The nightly table (`nightly.py`) keeps how many birds were aloft, not where they were heading. The heading is in
the raw profiles: for each 200 m layer vol2bird fits the flight vector (u, v, ground speed towards east and north).
This module goes back to the monthly profile files of the migration months and keeps, per radar and night, the
**traffic vector**: the sum over the night of density × velocity × layer thickness, i.e. how many birds crossed a
1 km line and in which direction (the vector form of the night MTR).

Only the radar-months that publish the vector are read (`flight_months`): vol2bird stopped storing it in France in
2021 and in most of Spain after the 2020 radar renewal, so the routes rest on Spain 2018-2020, France 2016-2022 and
Portugal 2019-2026. Direction does not depend on the radar's calibration, which is why years whose densities are
on another scale (the old Spanish radars) are still good here.

Per radar and season the nights are summed as vectors (`climatology`). The resultant gives the main direction of
the season's traffic and its *steadiness* R (1 when every bird went the same way, 0 when they cancel out). Each
night weighs by its own traffic within that radar, so the radars' different scales never mix.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from . import aloft as A
from .nightly import FF_FRAC_MIN, LAYER_KM, NIGHT_ELEV, clean, radar_position
from .solar import sun_elevation

MONTHS = (3, 4, 5, 8, 9, 10, 11)          # spring and autumn passage
SEASONS = {"spring": (3, 4, 5), "autumn": (8, 9, 10, 11)}


def season_of(month: int) -> str | None:
    for s, ms in SEASONS.items():
        if month in ms:
            return s
    return None


def flight_months(nightly_dir: Path) -> pd.DataFrame:
    """Radar-months of the migration seasons where most of the night density carries a flight vector."""
    rows = []
    for f in sorted(nightly_dir.glob("*.parquet")):
        if f.stem.endswith("_profiles"):
            continue
        n = pd.read_parquet(f, columns=["radar", "night", "ff_frac"])
        n["night"] = pd.to_datetime(n["night"])
        n = n[n["night"].dt.month.isin(MONTHS)]
        if n.empty:
            continue
        g = n.groupby([n["night"].dt.year.rename("year"), n["night"].dt.month.rename("month")])["ff_frac"].median()
        for (y, m), ff in g.items():
            if ff >= FF_FRAC_MIN:
                rows.append({"radar": n["radar"].iat[0], "year": int(y), "month": int(m)})
    return pd.DataFrame(rows)


def night_vectors(df: pd.DataFrame, radar: str) -> pd.DataFrame:
    """Per night: mean density, traffic vector and mean flight velocity, from the raw profiles of a radar.

    tu, tv   traffic towards east / north, birds per km of front per night (Σ dens·u·Δh·Δt)
    su, sv   density-weighted mean ground velocity of the birds (m/s)
    vec_frac share of the night's density whose layer has a flight vector
    """
    if df.empty:
        return pd.DataFrame()
    lat, lon = radar_position(df)
    d = clean(df)
    d["dens0"] = d["dens_clean"].fillna(0.0)
    u, v = d["u"].to_numpy(float), d["v"].to_numpy(float)
    ok = np.isfinite(u) & np.isfinite(v)
    w = d["dens0"].to_numpy(float)
    d["wu"] = np.where(ok, w * u, 0.0)
    d["wv"] = np.where(ok, w * v, 0.0)
    d["wok"] = np.where(ok, w, 0.0)
    d["wh"] = w * d["height"].to_numpy(float)
    g = d.groupby("datetime", sort=True)
    p = pd.DataFrame({"dsum": g["dens0"].sum(), "wu": g["wu"].sum(), "wv": g["wv"].sum(),
                      "wok": g["wok"].sum(), "wh": g["wh"].sum(), "valid": g["dens_clean"].count()}).reset_index()
    p = p[p["valid"] > 0]
    if p.empty:
        return pd.DataFrame()
    p["sun"] = sun_elevation(lat, lon, p["datetime"])
    p = p[p["sun"] < NIGHT_ELEV].copy()
    if p.empty:
        return pd.DataFrame()
    p["night"] = (p["datetime"] - pd.Timedelta(hours=12)).dt.normalize().dt.tz_localize(None)
    step_s = float(p["datetime"].diff().dt.total_seconds().median() or 300.0)
    # per instant: birds/km² (VID) and traffic flux birds/km/s, per component
    p["vid"] = p["dsum"] * LAYER_KM
    p["fu"] = p["wu"] * LAYER_KM / 1000.0
    p["fv"] = p["wv"] * LAYER_KM / 1000.0
    gn = p.groupby("night")
    out = pd.DataFrame({
        "n_prof": gn.size(),
        "vid": gn["vid"].mean(),
        "tu": gn["fu"].sum() * step_s,
        "tv": gn["fv"].sum() * step_s,
        "su_w": gn["wu"].sum(), "sv_w": gn["wv"].sum(), "wok": gn["wok"].sum(),
        "dsum": gn["dsum"].sum(), "wh": gn["wh"].sum(),
    })
    out["su"] = np.where(out["wok"] > 0, out["su_w"] / out["wok"], np.nan)
    out["sv"] = np.where(out["wok"] > 0, out["sv_w"] / out["wok"], np.nan)
    out["vec_frac"] = np.where(out["dsum"] > 0, out["wok"] / out["dsum"], np.nan)
    out["alt"] = np.where(out["dsum"] > 0, out["wh"] / out["dsum"], np.nan)
    out = out.drop(columns=["su_w", "sv_w", "wok", "dsum", "wh"]).reset_index()
    out.insert(0, "radar", radar)
    out["lat"], out["lon"] = lat, lon
    out["step_min"] = round(step_s / 60)
    return out


def month_vectors(radar: str, year: int, month: int, cache_dir: Path, keep: bool = False) -> pd.DataFrame:
    """Night vectors of one radar-month from Aloft's monthly file. The raw file is deleted unless `keep`."""
    key = A.monthly_key(radar, year, month)
    path = A.download(key, cache_dir)
    if path is None:
        return pd.DataFrame()
    try:
        df = A.read_vpts(path)
        out = night_vectors(df, radar)
    finally:
        if not keep:
            path.unlink(missing_ok=True)
    if out.empty:
        return out
    # the monthly file carries the first hours of the next month's first night: keep the month's own nights
    return out[out["night"].dt.month == month].reset_index(drop=True)


def archive(months: pd.DataFrame, out_dir: Path, cache_dir: Path, workers: int = 4, log=print) -> Path:
    """Night vectors of every radar-month, one small parquet per radar-month so that the run can resume."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    parts = out_dir / "months"
    parts.mkdir(parents=True, exist_ok=True)
    todo = [r for r in months.itertuples(index=False)
            if not (parts / f"{r.radar}_{r.year}{r.month:02d}.parquet").exists()]
    log(f"{len(months)} radar-months with a flight vector, {len(todo)} still to read")

    def one(r):
        t0 = dt.datetime.now()
        try:
            v = month_vectors(r.radar, r.year, r.month, cache_dir)
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the archive
            return r, None, f"error {type(e).__name__}: {e}"[:160]
        dest = parts / f"{r.radar}_{r.year}{r.month:02d}.parquet"
        (v if not v.empty else pd.DataFrame({"radar": [r.radar]}).iloc[:0]).to_parquet(dest, index=False)
        return r, len(v), f"{(dt.datetime.now() - t0).total_seconds():.0f} s"

    done = 0
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(one, r) for r in todo]
        for f in as_completed(futs):
            r, n, msg = f.result()
            done += 1
            log(f"  [{done}/{len(todo)}] {r.radar} {r.year}-{r.month:02d}: {n if n is not None else '-'} nights, {msg}")
    return combine(out_dir)


def combine(out_dir: Path) -> Path:
    frames = [pd.read_parquet(f) for f in sorted((out_dir / "months").glob("*.parquet"))]
    frames = [f for f in frames if not f.empty]
    nv = pd.concat(frames, ignore_index=True).sort_values(["radar", "night"])
    dest = out_dir / "flight_nights.parquet"
    nv.to_parquet(dest, index=False)
    return dest


# ---------------------------------------------------------------- from nights to routes

MIN_VEC_FRAC = 0.5     # a night counts when at least half of its density carries a flight vector
MIN_NIGHT_MIN = 120    # and the radar saw at least two hours of it
MIN_NIGHTS = 15        # a station needs this many nights in a season (or date window) to give a direction
WINDOW_DAYS = 15       # date window around a forecast night for its usual direction
TOP_SHARE = 0.10       # the heaviest tenth of the nights, for the concentration figure
MAX_SPEED = 25.0       # m/s over the ground; faster nights are most likely rain or clutter moved by the wind
CAP_Q = 0.95           # for the direction, no night weighs more than this quantile of its station's nights

# Old and renewed Spanish radars share sites under different codes: they are one station for the routes.
STATION_NAMES = {
    "esahr": "Málaga", "esmal": "Málaga", "esalm": "Almería", "esnjr": "Almería", "esbad": "Cáceres",
    "essft": "Cáceres", "esbar": "Barcelona", "esgld": "Barcelona", "esclg": "Sevilla", "essev": "Sevilla",
    "escor": "A Coruña", "eslid": "Valladolid", "esmad": "Madrid", "estjv": "Madrid", "esmur": "Murcia",
    "espdg": "Zaragoza", "eszar": "Zaragoza", "espma": "Mallorca", "essan": "Asturias", "essse": "Bizkaia",
    "esval": "Valencia",
}
COMPASS = {"es": ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"],
           "en": ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]}


def compass(heading: float, lang: str = "en") -> str:
    return COMPASS[lang][int(((heading % 360) + 11.25) // 22.5) % 16]


def station_name(radar: str) -> str:
    from .flows import radar_name

    return STATION_NAMES.get(radar) or radar_name(radar, "es")


def usable(nv: pd.DataFrame) -> pd.DataFrame:
    """Nights with a trustworthy vector, labelled with their station and season."""
    d = nv[(nv["vec_frac"] >= MIN_VEC_FRAC) & (nv["n_prof"] * nv["step_min"] >= MIN_NIGHT_MIN)].copy()
    d["night"] = pd.to_datetime(d["night"])
    d["season"] = d["night"].dt.month.map(season_of)
    d = d[d["season"].notna()]
    d["station"] = d["radar"].map(station_name)
    d["traffic"] = np.hypot(d["tu"], d["tv"])
    return d[np.hypot(d["su"], d["sv"]) <= MAX_SPEED]


def _resultant(g: pd.DataFrame) -> pd.Series:
    """Sum of the nights' traffic vectors of one station. Each radar code is first put on its own scale (its
    nights divided by its mean traffic), so that an old and a renewed radar on the same site weigh alike.

    For the direction each night's weight is capped at the CAP_Q quantile of the station's nights, so one huge
    night (or one echo the filters missed) cannot turn the arrow on its own; the concentration uses the raw sums.
    """
    scale = g.groupby("radar")["traffic"].transform("mean").replace(0, np.nan)
    tu, tv, t = g["tu"] / scale, g["tv"] / scale, g["traffic"] / scale
    f = np.minimum(1.0, t.quantile(CAP_Q) / t.where(t > 0))
    su, sv, sw = (tu * f).sum(), (tv * f).sum(), (t * f).sum()
    tt = t.sum()
    top = np.sort(t.to_numpy())[::-1]
    k = max(1, int(round(len(top) * TOP_SHARE)))
    return pd.Series({
        "nights": len(g),
        "years": f"{g['night'].dt.year.min()}–{g['night'].dt.year.max()}",
        "heading": float((np.degrees(np.arctan2(su, sv)) + 360) % 360),
        "steadiness": float(np.hypot(su, sv) / sw) if sw > 0 else np.nan,
        "speed": float(np.average(np.hypot(g["su"], g["sv"]), weights=g["traffic"] + 1e-9)),
        "alt": float(np.average(g["alt"].fillna(0), weights=g["traffic"] + 1e-9)),
        "top_share": float(top[:k].sum() / tt) if tt > 0 else np.nan,
        "p90": float(g["traffic"].quantile(0.9)),   # birds per km of front on a heavy night, raw radar scale
        "lat": float(g["lat"].mean()), "lon": float(g["lon"].mean()),
        "radars": " ".join(sorted(g["radar"].unique())),
    })


def climatology(nv: pd.DataFrame) -> pd.DataFrame:
    """Per station and season: main direction of the traffic, its steadiness, speed and concentration."""
    d = usable(nv)
    out = d.groupby(["station", "season"]).apply(_resultant, include_groups=False).reset_index()
    return out[out["nights"] >= MIN_NIGHTS].reset_index(drop=True)


def window(nv: pd.DataFrame, day: dt.date) -> pd.DataFrame:
    """Per station: the usual direction around one date of the year (± WINDOW_DAYS, every year)."""
    d = usable(nv)
    doy = d["night"].dt.dayofyear
    target = pd.Timestamp(day).dayofyear
    d = d[np.abs(doy - target) <= WINDOW_DAYS]
    if d.empty:
        return pd.DataFrame()
    out = d.groupby("station").apply(_resultant, include_groups=False).reset_index()
    return out[out["nights"] >= MIN_NIGHTS].reset_index(drop=True)


# ---------------------------------------------------------------- fields over the map

EXTENT = (-10.5, 8.5, 34.8, 51.5)   # lon_min, lon_max, lat_min, lat_max: Iberia, the Strait and France
GRID = 0.5                         # degrees; the page interpolates between nodes
SIGMA_KM = 130                     # kernel that spreads each station's direction
FADE_KM = (160, 320)               # direction drawn fully up to the first distance from a station, gone at the second
SIGMA_I_KM = 70                    # kernel for the intensity points (wind zones and cities)
FADE_I_KM = (70, 160)


def grid() -> tuple[np.ndarray, np.ndarray]:
    lon = np.arange(EXTENT[0], EXTENT[1] + GRID / 2, GRID)
    lat = np.arange(EXTENT[2], EXTENT[3] + GRID / 2, GRID)
    return np.meshgrid(lon, lat)


def _dist_km(lon, lat, plon, plat) -> np.ndarray:
    kx = 111.32 * np.cos(np.radians((lat[..., None] + plat) / 2))
    return np.hypot((lon[..., None] - plon) * kx, (lat[..., None] - plat) * 110.57)


def direction_field(st: pd.DataFrame, lon: np.ndarray, lat: np.ndarray):
    """Unit flight direction scaled by steadiness at every node, and how much of it to draw (0-1).

    It is a smoother between stations, not a model: away from every station it fades out instead of guessing.
    """
    if st.empty:
        z = np.zeros_like(lon)
        return z, z, z
    h = np.radians(st["heading"].to_numpy())
    r = st["steadiness"].to_numpy()
    d = _dist_km(lon, lat, st["lon"].to_numpy(), st["lat"].to_numpy())
    w = np.exp(-0.5 * (d / SIGMA_KM) ** 2) + 1e-12
    u = (w * (np.sin(h) * r)).sum(-1) / w.sum(-1)
    v = (w * (np.cos(h) * r)).sum(-1) / w.sum(-1)
    a = np.clip((FADE_KM[1] - d.min(-1)) / (FADE_KM[1] - FADE_KM[0]), 0, 1)
    return u, v, a


def intensity_field(pts: pd.DataFrame, lon: np.ndarray, lat: np.ndarray):
    """Expected birds/km² (from `vid`) at every node and how much of it to draw, from the forecast points."""
    if pts.empty:
        z = np.zeros_like(lon)
        return z, z
    d = _dist_km(lon, lat, pts["lon"].to_numpy(), pts["lat"].to_numpy())
    w = np.exp(-0.5 * (d / SIGMA_I_KM) ** 2) + 1e-12
    z = np.expm1((w * np.log1p(pts["vid"].clip(lower=0).to_numpy())).sum(-1) / w.sum(-1))
    a = np.clip((FADE_I_KM[1] - d.min(-1)) / (FADE_I_KM[1] - FADE_I_KM[0]), 0, 1)
    return z, a


def at(lon0: float, lat0: float, st: pd.DataFrame) -> tuple[float, float]:
    """Direction (degrees) and steadiness of the field at one point."""
    u, v, a = direction_field(st, np.array([[lon0]]), np.array([[lat0]]))
    if a[0, 0] <= 0:
        return np.nan, np.nan
    return float((np.degrees(np.arctan2(u[0, 0], v[0, 0])) + 360) % 360), float(np.hypot(u[0, 0], v[0, 0]))


def season_exposure(thresholds: pd.DataFrame, key: str = "zone") -> pd.DataFrame:
    """Expected birds/km² per place and season from the model's hindcast (mean of the date bins, by nights), and
    its rank among the places: 1 is the place with the most passage."""
    t = thresholds.assign(w=thresholds["nights"], vid=thresholds["pred_mean"].clip(lower=0) ** 3)
    g = (t.groupby([key, "season"])
         .apply(lambda x: np.average(x["vid"], weights=x["w"]), include_groups=False)
         .rename("vid").reset_index())
    g["pct"] = g.groupby("season")["vid"].rank(pct=True)
    return g
