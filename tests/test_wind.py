"""Wind zones: parsing of the OSM tags, the power curve, the cost of stopping and the decision table."""
import numpy as np
import pandas as pd

from subnocte import wind as W


def _node(i, lat, lon, **tags):
    return {"type": "node", "id": i, "lat": lat, "lon": lon, "tags": tags}


def test_power_tags_in_any_unit():
    assert W._power_mw("2 MW") == 2 and W._power_mw("850 kW") == 0.85
    assert W._power_mw("2000000 W") == 2 and W._power_mw("2,5 MW") == 2.5
    assert W._power_mw("1800 MW") == 1.8  # unit mistake in OSM
    assert W._power_mw("yes") is None and W._power_mw(None) is None


def test_small_turbines_are_left_out():
    els = [_node(1, 42.0, -2.0, **{"generator:output:electricity": "2 MW", "height:hub": "80"}),
           _node(2, 42.0, -2.0, **{"generator:output:electricity": "5 kW"}),
           _node(3, 42.0, -2.0, height="12"),
           _node(4, 42.0, -2.0),  # nothing tagged: kept
           {"type": "way", "id": 5, "center": {"lat": 41.0, "lon": -3.0}, "tags": {"rotor:diameter": "90 m"}}]
    t = W.parse_turbines(els)
    assert list(t["osm_id"]) == ["n1", "n4", "w5"]
    assert t.loc[2, "rotor_m"] == 90 and t.loc[0, "hub_m"] == 80


def test_power_curve():
    f = W.power_fraction(np.array([2, 3, 6, 12, 20, 26]))
    assert np.allclose(f, [0, 0, (6 ** 3 - 27) / (12 ** 3 - 27), 1, 1, 0])


def test_zones_need_enough_turbines(monkeypatch):
    monkeypatch.setattr(W, "_place", lambda lat, lon: ("Navarra", "ES"))
    big = pd.DataFrame({"osm_id": [f"n{i}" for i in range(12)], "lat": 42.6, "lon": -1.7,
                        "power_mw": 2.0, "rotor_m": np.nan, "hub_m": np.nan, "height_m": np.nan})
    small = big.head(W.MIN_TURBINES - 1).assign(lat=40.2, lon=-3.2)
    z = W.zones(pd.concat([big, small]))
    assert list(z["zone"]) == ["42.5N2.0W"] and z.loc[0, "turbines"] == 12
    assert z.loc[0, "power_mw"] == 24 and z.loc[0, "country"] == "ES"


def test_places_already_known_are_not_looked_up(monkeypatch):
    def fail(lat, lon):
        raise AssertionError("looked up again")
    monkeypatch.setattr(W, "_place", fail)
    t = pd.DataFrame({"osm_id": range(10), "lat": 42.6, "lon": -1.7, "power_mw": 2.0, "rotor_m": np.nan,
                      "hub_m": np.nan, "height_m": np.nan})
    prev = pd.DataFrame({"zone": ["42.5N2.0W"], "place": ["Navarra"], "country": ["ES"]})
    assert W.zones(t, prev).loc[0, "place"] == "Navarra"


def test_night_power_uses_only_the_night_window():
    h = pd.DataFrame({"time": pd.date_range("2026-10-01 12:00", periods=24, freq="h", tz="UTC"),
                      "wind_speed_100m": [20.0] * 8 + [12.0] * 10 + [20.0] * 6})
    n = pd.DataFrame({"radar": ["z"], "night": [pd.Timestamp("2026-10-01")],
                      "first": [h["time"][8]], "last": [h["time"][17]]})
    r = W.night_power(h, n).iloc[0]
    assert r["power_frac"] == 1 and r["hours_producing"] == 10 and r["wind100_mean"] == 12


def test_advice_table():
    assert W.stop_cost(0.1) == "cheap" and W.stop_cost(0.3) == "moderate" and W.stop_cost(0.6) == "expensive"
    assert W.advice("very high", "cheap") == "stop"
    assert W.advice("very high", "expensive") == "stop at peak hours"
    assert W.advice("high", "cheap") == "stop" and W.advice("high", "moderate") == "watch"
    assert W.advice("moderate", "cheap") == "run" and W.advice("no threshold", "cheap") == "run"
