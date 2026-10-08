import datetime as dt

import numpy as np
import pandas as pd

from subnocte import era5 as E


def test_months_cover_the_windows_and_stop_before_today():
    m = E.months([2025], today=dt.date(2025, 9, 20))
    assert [(y, mo) for y, mo, _ in m] == [(2025, k) for k in (2, 3, 4, 5, 6, 8, 9)]
    assert m[-1][2][-1] == 14  # six days back from the 20th


def test_wind_direction_is_where_it_blows_from():
    speed, frm = E._wind(np.array([0.0, 5.0, 0.0]), np.array([-5.0, 0.0, 5.0]))
    assert np.allclose(speed, 5)
    assert np.allclose(frm, [0, 270, 180])  # northerly, westerly, southerly


def test_humidity_is_100_at_the_dew_point():
    assert np.isclose(E._humidity(np.array([15.0]), np.array([15.0]))[0], 100)
    assert 38 < E._humidity(np.array([25.0]), np.array([10.0]))[0] < 40  # about 39 %


def test_only_hours_inside_the_windows_are_kept():
    t = pd.Series(pd.to_datetime(["2025-02-11", "2025-02-12", "2025-07-01", "2025-12-03", "2025-12-04"], utc=True))
    assert E._in_windows(t).tolist() == [False, True, False, True, False]
