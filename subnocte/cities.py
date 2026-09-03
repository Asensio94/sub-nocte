"""Pilot cities and how they are matched to radars.

A C-band radar measures the air volume well between roughly 5 and 100 km from the antenna: closer than 5 km
lies the cone of silence and beyond 100 km the beam flies too high. A city is only assigned to a radar when it
falls inside that band, and the confidence is flagged from the distance and the radar's known quality (phase 0).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

R_EARTH = 6371.0
D_MIN, D_MAX = 5.0, 100.0

# City-centre coordinates (decimal degrees). Iberian pilot plus southern French candidates.
CITIES = [
    ("Madrid", "ES", 40.4168, -3.7038),
    ("Barcelona", "ES", 41.3874, 2.1686),
    ("Valencia", "ES", 39.4699, -0.3763),
    ("Sevilla", "ES", 37.3891, -5.9845),
    ("Zaragoza", "ES", 41.6488, -0.8891),
    ("Málaga", "ES", 36.7213, -4.4214),
    ("Murcia", "ES", 37.9922, -1.1307),
    ("Palma", "ES", 39.5696, 2.6502),
    ("Bilbao", "ES", 43.2630, -2.9350),
    ("Alicante", "ES", 38.3452, -0.4810),
    ("Córdoba", "ES", 37.8882, -4.7794),
    ("Valladolid", "ES", 41.6523, -4.7245),
    ("Vigo", "ES", 42.2406, -8.7207),
    ("Gijón", "ES", 43.5322, -5.6611),
    ("Granada", "ES", 37.1773, -3.5986),
    ("Cáceres", "ES", 39.4753, -6.3724),
    ("Almería", "ES", 36.8340, -2.4637),
    ("Santander", "ES", 43.4623, -3.8100),
    ("Salamanca", "ES", 40.9701, -5.6635),
    ("Lisboa", "PT", 38.7223, -9.1393),
    ("Porto", "PT", 41.1579, -8.6291),
    ("Coimbra", "PT", 40.2033, -8.4103),
    ("Faro", "PT", 37.0194, -7.9304),
    ("Toulouse", "FR", 43.6047, 1.4442),
    ("Montpellier", "FR", 43.6108, 3.8767),
    ("Bordeaux", "FR", 44.8378, -0.5792),
    ("Marseille", "FR", 43.2965, 5.3698),
    ("Nice", "FR", 43.7102, 7.2620),
    ("Lyon", "FR", 45.7640, 4.8357),
]

# Per-radar quality known after phase 0 (2 Sep 2026); everything else is flagged "unassessed".
QUALITY = {"estjv": "high", "esgld": "high", "essft": "high", "ptprt": "high",
           "esahr": "low", "ptlis": "low"}


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(a))


QUALITY_RANK = {"high": 0, "unassessed": 1, "low": 2}


def assign(radars: pd.DataFrame, cities=CITIES) -> pd.DataFrame:
    """radars: columns radar, lat, lon and (optionally) last_year, taken from the nightly tables.

    The renewed AEMET network sits on the same sites as the old one (esbad/essft, esmad/estjv, esbar/esgld,
    esalm/esnjr share coordinates), so ties at the same distance are broken by known quality and then by the
    most recent year with data.
    """
    rows = []
    last = dict(zip(radars["radar"], radars.get("last_year", pd.Series(0, index=radars.index))))
    for name, country, lat, lon in cities:
        d = distance_km(lat, lon, radars["lat"].to_numpy(), radars["lon"].to_numpy())
        cand = [i for i in range(len(d)) if D_MIN <= d[i] <= D_MAX]
        order = sorted(range(len(d)), key=lambda i: d[i])
        cand.sort(key=lambda i: (round(d[i] / 10), QUALITY_RANK.get(QUALITY.get(radars["radar"].iloc[i], "unassessed"), 1),
                                 -last.get(radars["radar"].iloc[i], 0), d[i]))
        chosen = cand[0] if cand else None
        row = {"city": name, "country": country, "lat": lat, "lon": lon}
        if chosen is None:
            i = order[0]
            row |= {"radar": None, "dist_km": round(float(d[i]), 1), "confidence": "no usable radar",
                    "nearest_radar": radars["radar"].iloc[i]}
        else:
            r = radars["radar"].iloc[chosen]
            dist = float(d[chosen])
            qual = QUALITY.get(r, "unassessed")
            conf = "low" if qual == "low" or dist > 80 else ("high" if qual == "high" and dist <= 60 else "medium")
            row |= {"radar": r, "dist_km": round(dist, 1), "confidence": conf, "nearest_radar": r}
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["country", "city"]).reset_index(drop=True)
