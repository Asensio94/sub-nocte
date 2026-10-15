"""signals.json for Estado de las IBA: first night still to come, Spanish cities only."""
import datetime as dt

import pandas as pd

from subnocte import signals as S

NOW = dt.datetime(2026, 10, 15, 5, 30, tzinfo=dt.timezone.utc)


def _fc():
    rows = [("Madrid", "2026-10-14", "ES", "low", 40.4168, -3.7038),
            ("Madrid", "2026-10-15", "ES", "very high", 40.4168, -3.7038),
            ("Madrid", "2026-10-16", "ES", "high", 40.4168, -3.7038),
            ("Sevilla", "2026-10-15", "ES", "moderate", None, None),
            ("Lisboa", "2026-10-15", "PT", "high", 38.72, -9.14)]
    return pd.DataFrame(rows, columns=["city", "night", "country", "level", "lat", "lon"]).assign(
        night=lambda d: pd.to_datetime(d["night"]))


def test_first_coming_night_in_spain():
    doc = S.build(_fc(), NOW.date(), NOW)
    assert doc["source"] == "sub-nocte" and doc["version"] == 1 and doc["generated"] == "2026-10-15T05:30Z"
    by = {s["id"]: s for s in doc["signals"]}
    assert set(by) == {"Madrid-2026-10-15", "Sevilla-2026-10-15"}
    m = by["Madrid-2026-10-15"]
    assert m["title"] == "Madrid: migración nocturna muy alta prevista" and m["status"] == "very high"
    assert m["municipality_names"] == ["Madrid"] and m["precision"] == "radar"
    assert m["details"] == {"city": "Madrid", "point": [-3.7038, 40.4168]}
    assert "point" not in by["Sevilla-2026-10-15"]["details"]  # the contract wants a point or nothing


def test_no_forecast_still_writes_a_valid_file(tmp_path):
    assert S.write(None, tmp_path / "signals.json", NOW) == 0
    assert '"signals": []' in (tmp_path / "signals.json").read_text(encoding="utf-8")
