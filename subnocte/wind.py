"""Wind farms: nightly migration forecast per wind zone and the cost of stopping the turbines.

In the Netherlands offshore wind farms have been slowed on nights of heavy migration since May 2023, with a
forecast from the University of Amsterdam built on weather data and bird radars. In Spain and Portugal there is
nothing of the kind. This module points
the phase 3 forecast, which works at any point without a radar, at the wind turbines instead of the cities,
and adds the other half of the decision: what stopping would cost.

Three pieces:

1. **Inventory.** The wind turbines of Spain and Portugal in OpenStreetMap (ODbL). They are grouped into **wind zones**, cells of `CELL_DEG` degrees with at least `MIN_TURBINES`
   turbines. The weather model is synoptic: within a cell the forecast barely changes, and one point per cell
   keeps the archive needed for the thresholds within what Open-Meteo gives for free. Each zone carries the
   ground elevation of its point, the starting point for reading the radar band at turbine level.
2. **Forecast per zone.** The phase 3 operational model at the zone's point, with alert levels cut on the
   percentiles of that same zone around the same date, exactly as for the cities.
3. **Cost of stopping.** The forecast wind at 100 m over the night hours, through a generic power curve, gives
   the share of the rated power the zone would produce that night. A night of heavy passage with weak wind is a
   cheap night to stop; with strong wind it is an expensive one. The curve is generic (no manufacturer data), so
   the figure ranks the nights rather than measuring megawatt-hours.

What it does not do: say how many birds fly **at rotor height**. The forecast is the density of the whole column
the radars see, and the radars hardly see the lowest few hundred metres. See the limitations in the report.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
ELEVATION = "https://api.open-meteo.com/v1/elevation"
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "sub-nocte/0.1 (open conservation project)"

CELL_DEG = 0.5          # side of a wind zone, in degrees (about 55 × 42 km in the Peninsula)
MIN_TURBINES = 10       # fewer turbines than this in a cell do not make a zone
MIN_HEIGHT_M = 30       # below this (tagged height or hub) it is a small domestic turbine, left out
MIN_POWER_MW = 0.1
MAX_POWER_MW = 20       # above this a tagged power is a unit mistake
# The model was trained on the European radars: the Canaries and Madeira, out at sea and on another flyway,
# are left out. The box keeps the Peninsula and the Balearics.
LAT_RANGE, LON_RANGE = (35.8, 44.0), (-9.6, 4.5)

# Generic power curve of a modern onshore turbine at hub height (wind at 100 m from the forecast):
# nothing below the cut-in speed, cubic growth up to the rated speed, flat up to the cut-out speed.
CUT_IN, RATED, CUT_OUT = 3.0, 12.0, 25.0
CHEAP = 0.25            # night output below 25 % of rated power: stopping is cheap
EXPENSIVE = 0.50        # above 50 %: stopping is expensive

QUERY = """[out:json][timeout:600];
(area["ISO3166-1"="ES"][admin_level=2]; area["ISO3166-1"="PT"][admin_level=2];)->.a;
(node["power"="generator"]["generator:source"="wind"](area.a);
 way["power"="generator"]["generator:source"="wind"](area.a););
out center tags;"""


def _number(text: str | None) -> float | None:
    m = re.search(r"\d+(?:[.,]\d+)?", text or "")
    return float(m.group().replace(",", ".")) if m else None


def _power_mw(text: str | None) -> float | None:
    """'2 MW', '2000 kW', '850 kW' → MW. 'yes' or nothing → None."""
    v = _number(text)
    if v is None:
        return None
    t = (text or "").lower()
    mw = v / 1000 if "kw" in t else v / 1e6 if re.search(r"\d\s*w\b", t) else v
    # no wind turbine reaches 20 MW: '1800 MW' is a kW figure with the wrong unit
    return mw / 1000 if mw > MAX_POWER_MW else mw


def parse_turbines(elements: list[dict]) -> pd.DataFrame:
    rows = []
    for e in elements:
        t = e.get("tags", {})
        lat, lon = (e["lat"], e["lon"]) if e["type"] == "node" else (e["center"]["lat"], e["center"]["lon"])
        rows.append({
            "osm_id": f"{e['type'][0]}{e['id']}", "lat": round(lat, 5), "lon": round(lon, 5),
            "power_mw": _power_mw(t.get("generator:output:electricity")),
            "rotor_m": _number(t.get("rotor:diameter") or t.get("diameter:rotor")),
            "hub_m": _number(t.get("height:hub")),
            "height_m": _number(t.get("height")),
        })
    df = pd.DataFrame(rows)
    small = ((df["height_m"] < MIN_HEIGHT_M) | (df["hub_m"] < MIN_HEIGHT_M) | (df["power_mw"] < MIN_POWER_MW))
    return df[~small.fillna(False)].reset_index(drop=True)


def fetch_turbines(cache_dir: Path, log=print) -> pd.DataFrame:
    """Wind turbines of Spain and Portugal from Overpass, in a single query; the raw answer is cached.

    The country of each zone comes later from the place lookup, so the query does not need to be split.
    """
    raw = cache_dir / "turbines.json"
    if not raw.exists():
        # the public Overpass servers answer 504 when busy: alternate them, waiting longer each round
        for attempt, url in enumerate(OVERPASS * 3):
            try:
                r = requests.post(url, data={"data": QUERY}, headers={"User-Agent": USER_AGENT}, timeout=700)
            except requests.RequestException as e:
                log(f"  {url}: {e.__class__.__name__}")
                continue
            if r.ok:
                raw.parent.mkdir(parents=True, exist_ok=True)
                raw.write_bytes(r.content)
                break
            log(f"  {url}: HTTP {r.status_code}")
            time.sleep(30 * (attempt // len(OVERPASS) + 1))
        else:
            raise RuntimeError("Overpass unavailable")
    df = parse_turbines(json.loads(raw.read_text(encoding="utf-8"))["elements"])
    log(f"  {len(df):,} turbines")
    return df


def add_elevation(df: pd.DataFrame, log=print) -> pd.DataFrame:
    """Ground elevation of each point (Copernicus DEM 90 m through Open-Meteo, 100 points per call).

    Open-Meteo counts every point as one request against the hourly free quota, so this is run on the zones'
    points, not on the 25 000 turbines: the quota is needed for the weather archive.
    """
    out = np.full(len(df), np.nan)
    for i in range(0, len(df), 100):
        part = df.iloc[i:i + 100]
        for attempt in range(4):
            r = requests.get(ELEVATION, params={"latitude": ",".join(map(str, part["lat"])),
                                                "longitude": ",".join(map(str, part["lon"]))}, timeout=60)
            if r.ok:
                out[i:i + len(part)] = r.json()["elevation"]
                break
            time.sleep(2 ** attempt * 5)
        if i % 5000 == 0:
            log(f"  elevation {i}/{len(df)}")
    return df.assign(ground_m=out)


def _place(lat: float, lon: float) -> tuple[str, str]:
    """Province (Spain) or district (Portugal) of a point and its country code, from Nominatim."""
    r = requests.get(NOMINATIM, params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 8,
                                        "accept-language": "es"},
                     headers={"User-Agent": USER_AGENT}, timeout=60)
    time.sleep(1.1)  # Nominatim usage policy: one request per second
    a = r.json().get("address", {}) if r.ok else {}
    place = a.get("province") or a.get("county") or a.get("state_district") or a.get("state") or ""
    return place, a.get("country_code", "").upper()


def zone_id(clat: float, clon: float) -> str:
    """South-west corner of the cell, readable: 42.0N2.0W."""
    return f"{abs(clat):.1f}{'N' if clat >= 0 else 'S'}{abs(clon):.1f}{'E' if clon >= 0 else 'W'}"


def zones(turbines: pd.DataFrame, previous: pd.DataFrame | None = None, log=print) -> pd.DataFrame:
    """Group the turbines into cells and describe each zone. Places already looked up are reused."""
    t = turbines[turbines["lat"].between(*LAT_RANGE) & turbines["lon"].between(*LON_RANGE)].copy()
    t["cell_lat"] = np.floor(t["lat"] / CELL_DEG) * CELL_DEG
    t["cell_lon"] = np.floor(t["lon"] / CELL_DEG) * CELL_DEG
    known = ({r.zone: (r.place, r.country) for r in previous.itertuples()}
             if previous is not None and {"place", "country"} <= set(previous) else {})
    rows = []
    for (clat, clon), g in t.groupby(["cell_lat", "cell_lon"]):
        if len(g) < MIN_TURBINES:
            continue
        rotor_top = g["hub_m"] + g["rotor_m"] / 2
        rows.append({
            "zone": zone_id(clat, clon),
            "lat": round(g["lat"].mean(), 4), "lon": round(g["lon"].mean(), 4),
            "turbines": len(g),
            "power_mw": round(g["power_mw"].sum(), 1), "power_known": round(g["power_mw"].notna().mean(), 2),
            "rotor_m": g["rotor_m"].median(), "rotor_known": round(g["rotor_m"].notna().mean(), 2),
            "rotor_top_m": rotor_top.median(),
        })
    z = pd.DataFrame(rows).sort_values("turbines", ascending=False).reset_index(drop=True)
    places, countries = [], []
    for r in z.itertuples():
        if r.zone not in known:
            known[r.zone] = _place(r.lat, r.lon)
            log(f"  {r.zone}: {known[r.zone][0]} ({r.turbines} turbines)")
        places.append(known[r.zone][0]); countries.append(known[r.zone][1])
    return z.assign(place=places, country=countries)


# ---------------------------------------------------------------- cost of stopping

def power_fraction(wind: np.ndarray) -> np.ndarray:
    """Share of rated power for a wind speed at hub height (generic curve)."""
    w = np.asarray(wind, dtype=float)
    f = np.clip((w ** 3 - CUT_IN ** 3) / (RATED ** 3 - CUT_IN ** 3), 0, 1)
    return np.where((w < CUT_IN) | (w >= CUT_OUT), 0.0, f)


def night_power(hourly: pd.DataFrame, nights: pd.DataFrame) -> pd.DataFrame:
    """Mean share of rated power over each night window, and the hours of the night above the cut-in speed."""
    h = hourly.assign(time=pd.to_datetime(hourly["time"], utc=True)).set_index("time")
    rows = []
    for n in nights.itertuples(index=False):
        w = h.loc[n.first:n.last, "wind_speed_100m"].dropna()
        if w.empty:
            continue
        p = power_fraction(w.to_numpy())
        rows.append({"radar": n.radar, "night": n.night, "wind100_mean": round(float(w.mean()), 1),
                     "power_frac": round(float(p.mean()), 3), "hours_producing": int((p > 0).sum())})
    return pd.DataFrame(rows)


def stop_cost(power_frac: float) -> str:
    if power_frac < CHEAP:
        return "cheap"
    return "expensive" if power_frac >= EXPENSIVE else "moderate"


def advice(level: str, cost: str) -> str:
    """The decision table that crosses the two halves. It is a suggestion to rank nights, not an order.

    Chosen on the 2021-2026 hindcast of the first 59 zones. Stopping from the 75th percentile would have stopped
    21 nights per season and zone and lost 13.5 % of the night output; only from the 90th percentile and on cheap
    nights it is 7 nights and 2 % of the output, for 11 % of the predicted migration. It is that cheap because the
    heavy nights tend to be calm ones (correlation -0.19 between night output and predicted density).
    """
    if level == "very high":
        return {"cheap": "stop", "moderate": "stop at peak hours"}.get(cost, "watch")
    return "watch" if level == "high" else "run"
