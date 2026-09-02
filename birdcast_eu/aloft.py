"""Acceso al bucket público de Aloft (perfiles verticales de aves, VPTS CSV, licencia CC0).

Estructura del bucket (verificada el 2 sep 2026):
  baltrad/monthly/{radar}/{año}/{radar}_vpts_{AAAAMM}.csv.gz   meses completos
  baltrad/daily/{radar}/{año}/{radar}_vpts_{AAAAMMDD}.csv       un fichero por día, sube en D+1/D+2
"""

from __future__ import annotations

import datetime as dt
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd
import requests

BUCKET = "https://aloftdata.s3-eu-west-1.amazonaws.com"
NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}

# Columnas numéricas del formato VPTS CSV (https://github.com/aloftdata/vpts-csv)
NUMERIC = [
    "height", "u", "v", "w", "ff", "dd", "sd_vvp", "eta", "dens", "dbz", "dbz_all",
    "n", "n_dbz", "n_all", "n_dbz_all", "rcs", "sd_vvp_threshold",
    "radar_latitude", "radar_longitude", "radar_height", "radar_wavelength",
]

_session = requests.Session()
_session.headers["User-Agent"] = "birdcast-europa/0.1 (proyecto abierto de conservación)"


def list_prefixes(prefix: str) -> list[str]:
    """Subcarpetas inmediatas bajo un prefijo (p. ej. códigos de radar o años)."""
    out: list[str] = []
    token = None
    while True:
        params = {"list-type": "2", "prefix": prefix, "delimiter": "/"}
        if token:
            params["continuation-token"] = token
        r = _session.get(BUCKET, params=params, timeout=60)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for cp in root.findall("s3:CommonPrefixes/s3:Prefix", NS):
            out.append(cp.text.rstrip("/").split("/")[-1])
        token = root.findtext("s3:NextContinuationToken", default=None, namespaces=NS)
        if not token:
            return out


def list_keys(prefix: str) -> Iterator[tuple[str, dt.datetime, int]]:
    """Objetos bajo un prefijo: (clave, fecha de subida, tamaño)."""
    token = None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        r = _session.get(BUCKET, params=params, timeout=60)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for c in root.findall("s3:Contents", NS):
            key = c.findtext("s3:Key", namespaces=NS)
            lm = dt.datetime.fromisoformat(c.findtext("s3:LastModified", namespaces=NS).replace("Z", "+00:00"))
            size = int(c.findtext("s3:Size", namespaces=NS))
            yield key, lm, size
        token = root.findtext("s3:NextContinuationToken", default=None, namespaces=NS)
        if not token:
            return


def list_radars() -> list[str]:
    return list_prefixes("baltrad/daily/")


def radar_years(radar: str) -> list[int]:
    return sorted(int(y) for y in list_prefixes(f"baltrad/daily/{radar}/") if y.isdigit())


def monthly_key(radar: str, year: int, month: int) -> str:
    return f"baltrad/monthly/{radar}/{year}/{radar}_vpts_{year}{month:02d}.csv.gz"


def daily_key(radar: str, day: dt.date) -> str:
    return f"baltrad/daily/{radar}/{day.year}/{radar}_vpts_{day:%Y%m%d}.csv"


def download(key: str, cache_dir: Path) -> Path | None:
    """Descarga un objeto a la caché local. Devuelve None si no existe en el bucket."""
    dest = cache_dir / key
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    r = _session.get(f"{BUCKET}/{key}", timeout=300)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest


def read_vpts(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, na_values=["NaN", ""], keep_default_na=True, low_memory=False)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    for c in NUMERIC:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "gap" in df.columns:
        df["gap"] = df["gap"].astype(str).str.upper().eq("TRUE")
    return df


def months_between(start: dt.date, end: dt.date) -> Iterator[tuple[int, int]]:
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_radar(radar: str, start: dt.date, end: dt.date, cache_dir: Path, log=print) -> pd.DataFrame:
    """Perfiles de un radar entre dos fechas. Usa el mensual comprimido cuando existe y
    completa con ficheros diarios (mes en curso o meses sin resumen)."""
    frames: list[pd.DataFrame] = []
    today = dt.datetime.now(dt.timezone.utc).date()
    for y, m in months_between(start, end):
        first = dt.date(y, m, 1)
        last = (dt.date(y + (m == 12), (m % 12) + 1, 1) - dt.timedelta(days=1))
        path = None
        if last < today:  # solo meses cerrados tienen resumen mensual
            path = download(monthly_key(radar, y, m), cache_dir)
        if path is not None:
            log(f"  {radar} {y}-{m:02d}: mensual ({path.stat().st_size/1e6:.1f} MB)")
            frames.append(read_vpts(path))
            continue
        n = 0
        day = max(first, start)
        while day <= min(last, end, today):
            p = download(daily_key(radar, day), cache_dir)
            if p is not None:
                frames.append(read_vpts(p))
                n += 1
            day += dt.timedelta(days=1)
        log(f"  {radar} {y}-{m:02d}: {n} ficheros diarios")
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df[(df["datetime"].dt.date >= start) & (df["datetime"].dt.date <= end)]
    return df.sort_values(["datetime", "height"]).reset_index(drop=True)
