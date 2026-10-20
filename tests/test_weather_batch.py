import datetime as dt

from subnocte import weather as Wx


class _Resp:
    status_code = 200

    def __init__(self, j):
        self._j = j

    def raise_for_status(self):
        pass

    def json(self):
        return self._j


def test_many_points_go_in_batches_and_keep_their_order(monkeypatch):
    calls = []

    def get(url, params, timeout):
        lats = params["latitude"].split(",")
        calls.append(len(lats))
        hourly = [{"hourly": {"time": ["2026-10-20T00:00"], "lat": [float(x)]}} for x in lats]
        return _Resp(hourly if len(lats) > 1 else hourly[0])

    monkeypatch.setattr(Wx.requests, "get", get)
    monkeypatch.setattr(Wx, "PAUSE_S", 0)
    lats = [40 + i / 100 for i in range(Wx.BATCH_POINTS + 1)]
    out = Wx.fetch_hourly_many(lats, [0.0] * len(lats), dt.date(2026, 10, 20), dt.date(2026, 10, 21))
    assert calls == [Wx.BATCH_POINTS, 1]   # the last point alone: Open-Meteo answers an object, not a list
    assert [round(f["lat"].iat[0], 2) for f in out] == [round(x, 2) for x in lats]
