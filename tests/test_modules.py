import json

from core.alerts import SevereAlert
from core.hourly import HEADER, HourlyLog
from core.settings import Settings
from drivers import ds3231
from drivers.panel import Debouncer, button_command
from drivers.pms5003 import latest_reading, parse_frame
from net.telegram import Notifier, parse_updates, reply_for, status_text
from storage.filestore import FileStore


# ---- hourly log
def test_hourly_row_on_hour_change():
    h = HourlyLog()
    base = 3600 * 1000
    row = None
    for i in range(0, 3600, 5):
        row = h.add(base + i, 50.0, 80.0, 90, 2, 5, 0.8) or row
    assert row is None                              # still inside the first hour
    row = h.add(base + 3600, 50.0, 80.0, 90, 2, 5, 0.8)
    cols = dict(zip(HEADER.split(","), row.split(",")))
    assert cols["pm25_avg"] == "50.0" and cols["run_min"] == "60.0"
    assert cols["avg_speed"] == "2.00" and cols["filter_eff_pct"] == "80"
    assert cols["samples"] == "720"


def test_hourly_empty_efficiency_and_min_max():
    h = HourlyLog()
    h.add(7200, 10.0, 16.0, 30, 0, 5, None)
    h.add(7205, 30.0, 48.0, 50, 0, 5, None)
    cols = dict(zip(HEADER.split(","), h.add(10800, 1, 1, 1, 0, 5, None).split(",")))
    assert cols["pm25_min"] == "10.0" and cols["pm25_max"] == "30.0"
    assert cols["filter_eff_pct"] == "" and cols["run_min"] == "0.0"


# ---- severe-air alert
def test_severe_alert_needs_duration_and_respects_gap():
    cfg = Settings()
    a = SevereAlert(cfg)
    assert a.update(0, "severe") is None
    assert a.update(cfg.severe_alert_s - 1, "severe") is None
    assert a.update(cfg.severe_alert_s, "severe") is not None
    assert a.update(cfg.severe_alert_s + 60, "severe") is None          # inside the gap
    assert a.update(cfg.severe_alert_s + cfg.alert_gap_s, "severe") is not None


def test_severe_alert_timer_resets_when_air_improves():
    cfg = Settings()
    a = SevereAlert(cfg)
    a.update(0, "severe")
    a.update(300, "moderate")
    assert a.update(cfg.severe_alert_s, "severe") is None


# ---- storage
def test_json_roundtrip_and_missing(tmp_path):
    s = FileStore(str(tmp_path))
    assert s.load_json("x.json") is None
    s.save_json("x.json", {"a": 1})
    s.save_json("x.json", {"a": 2})
    assert s.load_json("x.json") == {"a": 2}


def test_corrupt_json_is_flagged(tmp_path):
    (tmp_path / "x.json").write_text("{not json")
    s = FileStore(str(tmp_path))
    assert s.load_json("x.json") is None and "x.json" in s.corrupt


def test_interrupted_save_is_recovered(tmp_path):
    (tmp_path / "x.json.tmp").write_text('{"a": 5}')
    assert FileStore(str(tmp_path)).load_json("x.json") == {"a": 5}


def test_log_trims_but_keeps_header_and_newest(tmp_path):
    s = FileStore(str(tmp_path))
    for i in range(300):
        s.append_line("log.csv", "row%d" % i, max_rows=100, header="h")
    lines = (tmp_path / "log.csv").read_text().split("\n")[:-1]
    assert lines[0] == "h" and lines[-1] == "row299"
    assert 100 <= len(lines) - 1 <= 150
    assert s.tail("log.csv", 3) == ["row297", "row298", "row299"]


def test_count_survives_a_new_store_object(tmp_path):
    s = FileStore(str(tmp_path))
    for i in range(5):
        s.append_line("log.csv", "r%d" % i, max_rows=3, header="h")
    s2 = FileStore(str(tmp_path))
    s2.append_line("log.csv", "r5", max_rows=3, header="h")
    assert s2.tail("log.csv", 1) == ["r5"]


# ---- PMS5003
def frame(pm25, pm10):
    body = bytearray([0x42, 0x4D, 0, 28] + [0] * 26)
    body[12], body[13] = pm25 >> 8, pm25 & 255
    body[14], body[15] = pm10 >> 8, pm10 & 255
    total = sum(body)
    return bytes(body) + bytes([total >> 8, total & 255])


def test_pms_parses_valid_frame():
    assert parse_frame(frame(35, 60)) == (35, 60)
    assert parse_frame(frame(300, 700)) == (300, 700)


def test_pms_rejects_bad_checksum_header_and_length():
    bad = bytearray(frame(35, 60))
    bad[31] ^= 1
    assert parse_frame(bytes(bad)) is None
    assert parse_frame(b"\x00" + frame(35, 60)[1:]) is None
    assert parse_frame(frame(35, 60)[:31]) is None


def test_pms_finds_newest_frame_in_noisy_stream():
    stream = b"\x01\x42\x99" + frame(10, 20) + b"junk" + frame(40, 70) + frame(55, 90)[:20]
    reading, rest = latest_reading(stream)
    assert reading == (40, 70)
    assert len(rest) < 32 and rest.startswith(b"\x42\x4d")


# ---- DS3231
def test_ds3231_roundtrip():
    for ts in (1767225600, 1794614400 + 4567, 1709210096):
        assert ds3231.decode(ds3231.encode(ts)) == ts


class FakeI2C:
    def __init__(self, ts):
        self.regs = ds3231.encode(ts)

    def readfrom_mem(self, addr, reg, n):
        return self.regs

    def writeto_mem(self, addr, reg, data):
        self.regs = data


def test_ds3231_reports_unset_clock_as_none():
    assert ds3231.DS3231(FakeI2C(946684800)).read_unix() is None      # 2000-01-01
    assert ds3231.DS3231(FakeI2C(1794614400)).read_unix() == 1794614400


# ---- buttons
def test_debouncer_ignores_bounce_and_fires_once():
    d = Debouncer(2, stable_ms=40)
    assert d.update([True, False], 0) == []
    assert d.update([False, False], 10) == []           # bounced away
    assert d.update([True, False], 20) == []
    assert d.update([True, False], 70) == [0]
    assert d.update([True, False], 200) == []           # held: no repeat
    assert d.update([False, False], 300) == []
    assert d.update([False, False], 400) == []


def test_button_commands():
    assert button_command(0, 0) == "speed:1" and button_command(0, 2) == "off"
    assert [button_command(i, 1) for i in (1, 2, 3)] == ["up", "down", "auto"]


# ---- Telegram
def test_updates_only_from_allowed_chat():
    resp = {"ok": True, "result": [
        {"update_id": 7, "message": {"chat": {"id": 111}, "text": "aqi?"}},
        {"update_id": 8, "message": {"chat": {"id": 999}, "text": "let me in"}},
        {"update_id": 9, "message": {"chat": {"id": 111}}},
    ]}
    texts, nxt = parse_updates(resp, "111")
    assert texts == ["aqi?"] and nxt == 10
    assert parse_updates({"ok": False}, "111") == ([], None)


def test_reply_rules():
    assert reply_for("What's the AQI?", "AQI 80", "http://1.2.3.4").startswith("AQI 80")
    assert "http://1.2.3.4" in reply_for("what's the AQI?", "AQI 80", "http://1.2.3.4")
    assert "http://1.2.3.4" in reply_for("hello", "AQI 80", "http://1.2.3.4")
    assert "AQI 80" not in reply_for("hello", "AQI 80", "http://1.2.3.4")


def test_notifier_caps_queue_and_adds_link():
    n = Notifier(max_queue=3)
    for i in range(5):
        n("m%d" % i)
    assert n.outbox == ["m2", "m3", "m4"]
    n.base_url = "http://x"
    assert n.with_link("hi").endswith("http://x")


def test_status_text():
    st = {"before": {"pm25": 88.4, "pm25_avg": 90.1}, "aqi": 130, "band": "moderate",
          "speed": 2, "mode": "AUTO"}
    assert "AQI 130" in status_text(st) and "speed 2" in status_text(st)
    assert "No sensor" in status_text({"before": None})
    assert json.dumps(st)
