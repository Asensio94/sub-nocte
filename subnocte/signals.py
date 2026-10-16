"""signals.json for Estado de las IBA: tonight's migration forecast per Spanish city.

The format is the sibling projects' contract
(https://github.com/Asensio94/estado-iba/blob/main/CONTRATO.md). Only the first night still to
come is sent, one signal per city; the hub turns the city name into its INE code.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

PAGE = "https://asensio94.github.io/sub-nocte/"
LEVEL_ES = {"very high": "muy alta", "high": "alta", "moderate": "moderada", "low": "baja"}


def build(fc: pd.DataFrame | None, today: dt.date, generated: dt.datetime) -> dict:
    signals = []
    if fc is not None and not fc.empty:
        nights = pd.to_datetime(fc["night"]).dt.date
        rows = fc[(fc["country"] == "ES") & (nights >= today)]
        if not rows.empty:
            first = pd.to_datetime(rows["night"]).dt.date.min()
            rows = rows[pd.to_datetime(rows["night"]).dt.date == first]
        for r in rows.itertuples(index=False):
            night = pd.Timestamp(r.night).date().isoformat()
            details = {"city": r.city}
            if pd.notna(r.lon) and pd.notna(r.lat):
                details["point"] = [round(float(r.lon), 4), round(float(r.lat), 4)]
            signals.append({
                "id": f"{r.city}-{night}", "kind": "migration", "date": night,
                "title": f"{r.city}: migración nocturna {LEVEL_ES.get(r.level, r.level)} prevista",
                "url": PAGE, "municipality_names": [r.city], "precision": "radar",
                "deadline": None, "status": r.level, "value": None, "details": details,
            })
    return {
        "source": "sub-nocte", "version": 1, "generated": generated.strftime("%Y-%m-%dT%H:%MZ"),
        "coverage": {"label": "Ciudades con radar meteorológico", "sites": [],
                     "note": "Previsión de paso de aves migratorias por la noche, a partir de radares y meteorología."},
        "signals": signals,
    }


def write(fc: pd.DataFrame | None, path: Path, now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    doc = build(fc, now.date(), now)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(doc["signals"])
