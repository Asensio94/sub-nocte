import pandas as pd
import pytest

from subnocte import wind_check as C


def _x():
    # two zones, one spring: zone a stops one calm night, zone b has a windy very high night it does not stop
    return pd.DataFrame({
        "zone": ["a", "a", "a", "b", "b", "b"],
        "year": 2024, "season": "spring",
        "level": ["very high", "low", "low", "very high", "high", "low"],
        "advice": ["stop", "run", "run", "watch", "watch", "run"],
        "power_frac": [0.1, 0.5, 0.4, 0.8, 0.1, 0.1],
        "pred": [10.0, 1.0, 1.0, 6.0, 1.0, 1.0],
    })


def test_hindcast_counts_nights_per_zone_and_shares():
    h = C.hindcast(_x()).set_index("rule")
    assert h.loc["stop", "nights_per_zone"] == 0.5
    assert h.loc["stop", "output_lost"] == pytest.approx(0.1 / 2.0)
    assert h.loc["stop", "migration_covered"] == pytest.approx(10 / 20)
    assert h.loc["every very high night", "nights_per_zone"] == 1.0
    assert h.loc["every very high night", "output_lost"] == pytest.approx(0.9 / 2.0)


def test_pair_radars_keeps_only_close_zones():
    nightly = pd.DataFrame({"radar": ["r1", "r1", "r2"], "lat": [40.0, 40.0, 43.0], "lon": [-3.0, -3.0, -8.0]})
    zones = pd.DataFrame({"zone": ["near", "far"], "lat": [40.3, 37.0], "lon": [-3.0, 0.0]})
    p = C.pair_radars(zones, nightly)
    assert list(p["zone"]) == ["near"]
    assert p["radar"].iat[0] == "r1"
    assert p["dist_km"].iat[0] == pytest.approx(33.4, abs=0.5)


def test_check_summary_lift_against_all_nights():
    m = pd.DataFrame({"level": ["very high", "very high", "low", "low"],
                      "advice": ["stop", "watch", "run", "run"],
                      "obs_pct": [0.9, 0.8, 0.2, 0.5]})
    s = C.check_summary(m).set_index("group")
    assert s.loc["all nights", "busy"] == 0.5
    assert s.loc["level very high", "busy"] == 1.0
    assert s.loc["level very high", "lift"] == 2.0
    assert s.loc["level low", "busy"] == 0.0
    assert s.loc["advice stop", "zone_nights"] == 1
