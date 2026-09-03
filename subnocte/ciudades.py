"""Ciudades del piloto y su asignación a radares.

Un radar de banda C mide bien el volumen de aire entre unos 5 y 100 km de la antena; a menos de 5 km hay cono
de silencio y a más de 100 km el haz vuela demasiado alto. Una ciudad solo se asigna a un radar si cae en esa
banda, y se marca la confianza según la distancia y la calidad conocida del radar (fase 0).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

R_TIERRA = 6371.0
D_MIN, D_MAX = 5.0, 100.0

# Coordenadas del centro urbano (grados decimales). Piloto ibérico y candidatas del sur de Francia.
CIUDADES = [
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

# Calidad conocida por radar tras la fase 0 (2 sept 2026); el resto se marca "sin evaluar".
CALIDAD = {"estjv": "alta", "esgld": "alta", "essft": "alta", "ptprt": "alta",
           "esahr": "baja", "ptlis": "baja"}


def distancia_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R_TIERRA * np.arcsin(np.sqrt(a))


RANGO_CALIDAD = {"alta": 0, "sin evaluar": 1, "baja": 2}


def asignar(radares: pd.DataFrame, ciudades=CIUDADES) -> pd.DataFrame:
    """radares: columnas radar, lat, lon y (opcional) ultimo_anio, de las tablas nocturnas.

    La red renovada de AEMET ocupa los mismos emplazamientos que la antigua (esbad/essft, esmad/estjv,
    esbar/esgld, esalm/esnjr comparten coordenadas), así que a igual distancia se desempata por calidad
    conocida y por el año más reciente con datos.
    """
    rows = []
    ultimo = dict(zip(radares["radar"], radares.get("ultimo_anio", pd.Series(0, index=radares.index))))
    for nombre, pais, lat, lon in ciudades:
        d = distancia_km(lat, lon, radares["lat"].to_numpy(), radares["lon"].to_numpy())
        cand = [i for i in range(len(d)) if D_MIN <= d[i] <= D_MAX]
        orden = sorted(range(len(d)), key=lambda i: d[i])
        cand.sort(key=lambda i: (round(d[i] / 10), RANGO_CALIDAD.get(CALIDAD.get(radares["radar"].iloc[i], "sin evaluar"), 1),
                                 -ultimo.get(radares["radar"].iloc[i], 0), d[i]))
        elegido = cand[0] if cand else None
        row = {"ciudad": nombre, "pais": pais, "lat": lat, "lon": lon}
        if elegido is None:
            i = orden[0]
            row |= {"radar": None, "dist_km": round(float(d[i]), 1), "confianza": "sin radar útil",
                    "radar_mas_cercano": radares["radar"].iloc[i]}
        else:
            r = radares["radar"].iloc[elegido]
            dist = float(d[elegido])
            cal = CALIDAD.get(r, "sin evaluar")
            conf = "baja" if cal == "baja" or dist > 80 else ("alta" if cal == "alta" and dist <= 60 else "media")
            row |= {"radar": r, "dist_km": round(dist, 1), "confianza": conf, "radar_mas_cercano": r}
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["pais", "ciudad"]).reset_index(drop=True)
