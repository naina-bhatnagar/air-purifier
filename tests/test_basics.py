from core.aqi import aqi_band, pm25_to_aqi
from core.clock import Mono
from core.relays import RelayBank
from core.ring import Ring
from core.timeutil import iso_local, tuple_from_unix, unix_from_tuple


def test_aqi_cpcb_breakpoints():
    assert [pm25_to_aqi(x) for x in (0, 30, 60, 90, 120)] == [0, 50, 100, 200, 300]
    assert pm25_to_aqi(1000) == 500


def test_aqi_epa_differs_and_is_monotonic():
    assert pm25_to_aqi(35.4, "epa") == 100
    values = [pm25_to_aqi(x, "epa") for x in range(0, 300, 5)]
    assert values == sorted(values)


def test_bands():
    assert [aqi_band(x) for x in (40, 90, 150, 350)] == ["best", "average", "moderate", "severe"]


def test_ring_order_and_mean():
    r = Ring(3)
    for x in (1, 2, 3, 4):
        r.append(x)
    assert r.values() == [2, 3, 4] and r.full() and r.mean() == 3
    r.clear()
    assert len(r) == 0 and r.mean() == 0.0


def test_time_known_value_and_roundtrip():
    assert unix_from_tuple(2026, 11, 14) == 1794614400
    for ts in (0, 951782400, 1709210096, 1794614400 + 12345):
        assert unix_from_tuple(*tuple_from_unix(ts)) == ts
    assert tuple_from_unix(1709210096)[:3] == (2024, 2, 29)     # leap day


def test_iso_local_applies_offset():
    assert iso_local(1794614400, 330) == "2026-11-14 05:30"


def test_mono_survives_tick_wrap():
    wrap = 2 ** 30
    ticks = [wrap - 1000]

    def diff(a, b):
        return ((a - b + wrap // 2) % wrap) - wrap // 2

    m = Mono(lambda: ticks[0], diff)
    ticks[0] = (ticks[0] + 3000) % wrap     # wraps past zero
    assert m() == 3.0
    ticks[0] = (ticks[0] + 2000) % wrap
    assert m() == 5.0


def test_relays_interlock_and_gap():
    writes = []
    r = RelayBank(writes.append, sleep=lambda s: None)
    for s in (1, 3, 2, 0, 3, 1):
        r.set_speed(s)
    assert all(sum(w) <= 1 for w in writes)
    # moving between two running speeds always passes through all-off
    i = writes.index([False, False, True])
    assert writes[i - 1] == [False, False, False]


def test_relays_reject_bad_speed():
    r = RelayBank(lambda p: None)
    try:
        r.set_speed(4)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
