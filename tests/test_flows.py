"""Night replay: frames, the density field and the night summary on synthetic radars."""
import numpy as np
import pandas as pd

from subnocte import flows as F


def _radars(vid=(10.0, 1.0)):
    return pd.DataFrame({"radar": ["a", "b"], "lat": [40.0, 40.0], "lon": [-4.0, 0.0], "vid": list(vid),
                         "u": [0.0, np.nan], "v": [-10.0, np.nan]})


def test_field_matches_an_isolated_radar_and_fades_far_away():
    z, alpha = F.field(_radars(), np.array([-4.0, 0.0, -4.0]), np.array([40.0, 40.0, 50.0]))
    assert abs(z[0] - 10) < 0.5 and abs(z[1] - 1) < 0.1  # radars 340 km apart barely mix
    assert alpha[0] == 1 and alpha[2] == 0               # 1100 km from any radar: not drawn


def test_frames_average_profiles_within_twenty_minutes():
    t = pd.to_datetime(["2026-09-24 22:00", "2026-09-24 22:10", "2026-09-24 22:25"], utc=True)
    p = pd.DataFrame({"datetime": t, "vid": [2.0, 4.0, 8.0], "u": 0.0, "v": 1.0, "alt": 1000.0,
                      "radar": "a", "lat": 40.0, "lon": -4.0})
    fr = F.frames(p)
    assert list(fr["vid"]) == [3.0, 8.0]


def test_summary_heading_is_the_direction_of_flight():
    fr = pd.DataFrame({"radar": ["a", "a"], "lat": 40.0, "lon": -4.0, "vid": [1.0, 3.0],
                       "u": [-5.0, -5.0], "v": [-5.0, -5.0], "alt": 1200.0})
    s = F.night_summary(fr).iloc[0]
    assert round(s["heading"]) == 225 and abs(s["speed"] - np.hypot(5, 5)) < 1e-9  # towards the south-west
