import datetime as dt

import pytest
import requests

from subnocte import weather as Wx

DAY = dt.date(2026, 10, 15)


class _Answer:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def _series(lat):
    return {"latitude": lat, "hourly": {"time": ["2026-10-15T00:00"], "temperature_2m": [lat]}}


@pytest.fixture
def calls(monkeypatch):
    log = []

    def get(url, params, timeout):
        log.append((params, timeout))
        lats = [float(x) for x in params["latitude"].split(",")]
        body = [_series(x) for x in lats] if len(lats) > 1 else _series(lats[0])
        return _Answer(body)

    monkeypatch.setattr(Wx.requests, "get", get)
    monkeypatch.setattr(Wx.time, "sleep", lambda s: None)
    return log


def test_many_points_in_few_requests_keep_their_order(calls):
    points = [(float(i), 0.0) for i in range(7)]
    out = Wx.fetch_hourly_many(points, DAY, DAY, per_request=3)
    assert len(calls) == 3
    assert [df["temperature_2m"].iloc[0] for df in out] == [p[0] for p in points]


def test_a_single_point_comes_back_as_an_object(calls):
    df = Wx.fetch_hourly(4.0, 0.0, DAY, DAY)
    assert df["temperature_2m"].iloc[0] == 4.0
    assert calls[0][1] == 300  # the archive keeps its long timeout


def test_a_request_without_answer_is_retried(monkeypatch):
    answers = iter([requests.exceptions.ReadTimeout("read timed out"), _Answer(_series(1.0))])
    waits = []

    def get(url, params, timeout):
        a = next(answers)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(Wx.requests, "get", get)
    monkeypatch.setattr(Wx.time, "sleep", waits.append)
    df = Wx.fetch_hourly(1.0, 0.0, DAY, DAY, timeout=60, backoff=10, log=lambda m: None)
    assert df["temperature_2m"].iloc[0] == 1.0
    assert waits == [10]
