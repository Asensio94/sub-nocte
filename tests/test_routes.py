import datetime as dt
import json
import re

import numpy as np
import pandas as pd
import pytest

from subnocte import routes as R
from subnocte import routes_page as RP


def _nights(radar="esmad", lat=40.4, lon=-3.7, n=30, heading=200.0, start="2019-09-01", traffic=1000.0, **kw):
    h = np.radians(heading)
    nights = pd.date_range(start, periods=n, freq="D")
    d = pd.DataFrame({"radar": radar, "night": nights, "n_prof": 60, "step_min": 5, "vec_frac": 0.9,
                      "vid": 5.0, "tu": traffic * np.sin(h), "tv": traffic * np.cos(h),
                      "su": 12 * np.sin(h), "sv": 12 * np.cos(h), "alt": 900.0, "lat": lat, "lon": lon})
    return d.assign(**kw)


def test_compass_and_season():
    assert R.compass(0) == "N"
    assert R.compass(359) == "N"
    assert R.compass(202.5, "es") == "SSO"
    assert R.compass(225, "en") == "SW"
    assert R.season_of(9) == "autumn"
    assert R.season_of(4) == "spring"
    assert R.season_of(7) is None


def test_usable_drops_short_unvectored_and_too_fast_nights():
    d = _nights(n=4)
    d.loc[0, "vec_frac"] = 0.2           # most of the density without a vector
    d.loc[1, "n_prof"] = 10              # 50 minutes of radar
    d.loc[2, ["su", "sv"]] = [30.0, 0]   # 30 m/s over the ground: rain or clutter
    u = R.usable(d)
    assert list(u.index) == [3]
    assert u["station"].iat[0] == "Madrid"
    assert u["season"].iat[0] == "autumn"


def test_climatology_heading_and_steadiness():
    c = R.climatology(_nights(heading=200.0)).iloc[0]
    assert c["heading"] == pytest.approx(200.0)
    assert c["steadiness"] == pytest.approx(1.0)
    # half the nights the other way round: the arrow loses its steadiness
    d = pd.concat([_nights(n=20, heading=200.0), _nights(n=20, heading=20.0, start="2019-10-01")])
    assert R.climatology(d).iloc[0]["steadiness"] == pytest.approx(0.0, abs=1e-9)


def test_one_huge_night_cannot_turn_the_arrow():
    d = _nights(n=40, heading=200.0)
    big = _nights(n=1, heading=90.0, start="2019-10-20", traffic=1e6)
    c = R.climatology(pd.concat([d, big], ignore_index=True)).iloc[0]
    assert 190 < c["heading"] < 215
    # the concentration still counts it in full
    assert c["top_share"] > 0.9


def test_old_and_renewed_radar_weigh_alike():
    old = _nights("esmad", n=20, heading=180.0, traffic=10.0)
    new = _nights("estjv", n=20, heading=270.0, traffic=10000.0, start="2019-10-01")
    c = R.climatology(pd.concat([old, new], ignore_index=True)).iloc[0]
    assert c["station"] == "Madrid"
    assert c["heading"] == pytest.approx(225.0, abs=0.5)


def test_min_nights_per_station():
    assert R.climatology(_nights(n=R.MIN_NIGHTS - 1)).empty


def test_window_is_around_the_date_every_year():
    d = pd.concat([_nights(n=20, start="2019-09-05"), _nights(n=20, start="2020-09-05", heading=210.0),
                   _nights(n=20, start="2019-10-20")])
    w = R.window(d, dt.date(2026, 9, 15))
    assert w["nights"].iat[0] == 40   # both Septembers, not the late October nights
    assert R.window(d, dt.date(2026, 4, 15)).empty


def test_direction_field_fades_away_from_the_stations():
    st = pd.DataFrame({"heading": [180.0], "steadiness": [0.8], "lon": [-3.7], "lat": [40.4]})
    lon = np.array([[-3.7, -3.7 + R.FADE_KM[1] / 85 + 0.5]])
    lat = np.array([[40.4, 40.4]])
    u, v, a = R.direction_field(st, lon, lat)
    assert a[0, 0] == 1.0 and a[0, 1] == 0.0
    assert v[0, 0] == pytest.approx(-0.8)
    assert u[0, 0] == pytest.approx(0.0, abs=1e-9)
    assert np.isnan(R.at(lon[0, 1], lat[0, 1], st)[0])


def test_land_packs_and_thins_rings():
    ring = np.array([[-5.0, 40.0], [-5.001, 40.0], [-4.0, 40.0], [-4.0, 41.0], [-5.0, 41.0], [-5.0, 40.0]])
    far = ring + [80, 0]
    out = RP.land([ring, far])
    assert len(out) == 1
    assert out[0][:4] == [-500, 4000, -400, 4000]   # the point 0.001° away is dropped


def _inputs():
    nights = pd.concat([_nights("esmad", 40.4, -3.7, heading=200.0), _nights("espdg", 41.7, -0.5, heading=215.0),
                        _nights("esmad", 40.4, -3.7, heading=30.0, start="2019-04-01"),
                        _nights("esmad", 40.4, -3.7, heading=200.0, start="2019-10-01")], ignore_index=True)
    zones = pd.DataFrame({"zone": ["41.5N1.0W", "40.0N4.0W"], "place": ["Cinco Villas", None], "country": "ES",
                          "turbines": [150, 20], "power_mw": [146.0, 30.0], "lat": [41.5, 40.0], "lon": [-1.0, -4.0]})
    th = pd.DataFrame({"zone": ["41.5N1.0W", "41.5N1.0W", "40.0N4.0W", "40.0N4.0W"],
                       "season": ["autumn", "spring"] * 2, "nights": 100, "pred_mean": [2.0, 1.5, 1.0, 0.8]})
    wf = pd.DataFrame({"zone": ["41.5N1.0W", "40.0N4.0W"] * 2,
                       "night": pd.to_datetime(["2026-10-15", "2026-10-15", "2026-10-16", "2026-10-16"]),
                       "lat": [41.5, 40.0] * 2, "lon": [-1.0, -4.0] * 2, "power_mw": [146.0, 30.0] * 2,
                       "pred": [3.0, 1.0, 1.5, 1.0],
                       "level": ["very high", "low", "high", "low"], "percentile": [0.97, 0.3, 0.8, 0.2],
                       "advice": ["stop", "run", "watch", "run"], "wind100_mean": [3.1, 8.0, 6.7, 9.0],
                       "power_frac": [0.05, 0.6, 0.17, 0.7], "cost": ["cheap", "expensive", "cheap", "expensive"]})
    ring = np.array([[-9.5, 36.0], [3.3, 36.0], [3.3, 43.8], [-9.5, 43.8], [-9.5, 36.0]])
    return RP.Inputs(nights=nights, zones=zones, zone_thresholds=th, wind_forecast=wf, rings=[ring])


@pytest.mark.parametrize("lang", ["es", "en"])
def test_page_smoke(lang):
    html = RP.page(_inputs(), lang, dt.date(2026, 10, 15))
    blob = re.search(r"id='routes-data'>(.*?)</script>", html, re.S).group(1)
    d = json.loads(blob)
    assert set(d["modes"]) >= {"autumn", "spring"}
    fc = [m for m in d["modes"].values() if m["kind"] == "forecast"]
    assert len(fc) == 2 and d["fdir"]["st"]
    assert fc[0]["zs"]["41.5N1.0W"][0] == "stop"
    assert len(fc[0]["i"]) == len(d["fdir"]["u"])
    assert "Cinco Villas" in html
    assert "@@N@@" in blob and "{name}" in d["text"]["station_html"]
