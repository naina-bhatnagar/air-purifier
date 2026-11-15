import asyncio
import json

from core.app import SAMPLE_S
from core.settings import DEFAULTS
from drivers.sim import SimRoom
from helpers import make_app, run_app
from net.api import Api
from net.server import build_head, parse_request_line, serve


def make_api(tmp_path, **kw):
    app, room, bank, store, sent, t, sensors = make_app(tmp_path, **kw)
    api = Api(app, store, lambda: t["now"], str(tmp_path / "index.html"))
    return api, app, room, bank, store, sent, t


def call(api, method, path, body=None, pin="0000"):
    headers = {"x-pin": pin} if pin is not None else {}
    raw = json.dumps(body) if body else ""
    code, ctype, payload, extra = api.handle(method, path, headers, raw)
    return code, payload, extra


# ---- whole app
def test_boot_sends_restart_message_with_reason(tmp_path):
    app, room, bank, store, sent, t, _ = make_app(tmp_path, boot="power came back")
    assert sent == ["Purifier restarted: power came back"]


def test_restart_keeps_manual_speed_and_settings(tmp_path):
    app, room, bank, store, sent, t, _ = make_app(tmp_path)
    assert app.update_settings({"on_pm": 80, "off_pm": 40}) == []
    app.handle_command("speed:2", t["now"])
    run_app(app, room, t, 60)

    app2, room2, bank2, *_ = make_app(tmp_path)
    assert bank2.speed == 2 and app2.ctl.mode == "MANUAL"
    assert app2.cfg.on_pm == 80 and app2.cfg.off_pm == 40


def test_restart_keeps_run_hours(tmp_path):
    app, room, bank, store, sent, t, _ = make_app(tmp_path)
    app.handle_command("speed:1", 0)
    run_app(app, room, t, 3600)
    app.ctl.dirty = True
    app.step(t["now"])                      # a step with changes saves the state
    app2 = make_app(tmp_path)[0]
    assert app2.ctl.total_run_s > 3000


def test_corrupt_settings_fall_back_and_warn(tmp_path):
    (tmp_path / "settings.json").write_text("{broken")
    app = make_app(tmp_path)[0]
    assert app.cfg.on_pm == DEFAULTS["on_pm"]
    assert any("defaults" in n for n in app.notes)


def test_status_has_everything_the_page_shows(tmp_path):
    app, room, bank, store, sent, t, _ = make_app(tmp_path)
    run_app(app, room, t, 120)
    st = app.status()
    assert set(st["before"]) == {"pm25", "pm10", "pm25_avg", "pm10_avg"}
    assert set(st["after"]) == {"pm25", "pm10", "pm25_avg", "pm10_avg"}
    for key in ("aqi", "band", "eff", "state", "mode", "speed", "run_hours", "default_pin"):
        assert key in st
    assert json.dumps(st)


def test_live_buffer_holds_30_minutes(tmp_path):
    app, room, bank, store, sent, t, _ = make_app(tmp_path)
    run_app(app, room, t, 3 * 3600)
    pts = app.live_points()
    assert len(pts) == 360 and pts[-1][0] - pts[0][0] == 359 * SAMPLE_S


def test_hourly_log_and_events_are_written(tmp_path):
    app, room, bank, store, sent, t, _ = make_app(tmp_path)
    run_app(app, room, t, 3 * 3600)
    rows = store.tail("hourly.csv", 10)
    assert len(rows) >= 2 and len(rows[0].split(",")) == 10
    assert store.tail("events.csv", 5)


def test_sensor_failure_is_survivable(tmp_path):
    room = SimRoom(pm=120, outdoor=200)
    app, room, bank, store, sent, t, sensors = make_app(tmp_path, room=room)
    run_app(app, room, t, 300)
    assert bank.speed > 0
    sensors[0].dead = True
    run_app(app, room, t, 120)
    assert app.status()["fault"] and bank.speed == 0 and app.status()["before"] is None
    sensors[0].dead = False
    run_app(app, room, t, 300)
    assert not app.status()["fault"] and bank.speed > 0


def test_one_relay_at_a_time_over_a_long_simulation(tmp_path):
    writes = []
    app, room, bank, *_ = make_app(tmp_path, room=SimRoom(outdoor=250))
    bank._write = writes.append
    t = {"now": 0.0}
    for _ in range(8 * 720):
        room.step(SAMPLE_S, bank.speed)
        app.step(t["now"])
        t["now"] += SAMPLE_S
    assert writes and all(sum(w) <= 1 for w in writes)


def test_severe_air_sends_one_alert_per_gap(tmp_path):
    app, room, bank, store, sent, t, _ = make_app(tmp_path, room=SimRoom(pm=400, outdoor=400))
    run_app(app, room, t, 3000)
    severe = [m for m in sent if "severe" in m]
    assert len(severe) == 1


# ---- API
def test_get_endpoints_work_without_pin(tmp_path):
    api, app, room, *_ = make_api(tmp_path)
    for path in ("/api/status", "/api/live", "/api/settings", "/api/events"):
        code, payload, _ = call(api, "GET", path, pin=None)
        assert code == 200 and json.loads(payload)


def test_settings_endpoint_never_leaks_pin(tmp_path):
    api, *_ = make_api(tmp_path)
    code, payload, _ = call(api, "GET", "/api/settings", pin=None)
    assert "pin" not in json.loads(payload)["values"] and "0000" not in payload


def test_commands_need_the_pin(tmp_path):
    api, app, room, bank, *_ = make_api(tmp_path)
    assert call(api, "POST", "/api/command", {"cmd": "speed:3"}, pin=None)[0] == 403
    assert call(api, "POST", "/api/command", {"cmd": "speed:3"}, pin="1111")[0] == 403
    assert bank.speed == 0
    assert call(api, "POST", "/api/command", {"cmd": "speed:3"})[0] == 200
    assert bank.speed == 3


def test_wrong_pin_lockout_then_recovers(tmp_path):
    api, app, room, bank, store, sent, t = make_api(tmp_path)
    for _ in range(5):
        assert call(api, "POST", "/api/auth", pin="9999")[0] == 403
    assert call(api, "POST", "/api/auth")[0] == 429             # even the right PIN is refused
    t["now"] += 61
    assert call(api, "POST", "/api/auth")[0] == 200


def test_bad_requests_get_clean_errors(tmp_path):
    api, *_ = make_api(tmp_path)
    assert api.handle("POST", "/api/command", {"x-pin": "0000"}, "{nope")[0] == 400
    assert api.handle("POST", "/api/command", {"x-pin": "0000"}, "[1]")[0] == 400
    assert call(api, "POST", "/api/command", {"cmd": "explode"})[0] == 400
    assert call(api, "POST", "/api/command", {"cmd": 5})[0] == 400
    assert call(api, "GET", "/nope", pin=None)[0] == 404
    assert call(api, "POST", "/nope")[0] == 404
    assert api.handle("DELETE", "/api/status", {}, "")[0] == 405


def test_settings_update_validation_and_pin_change(tmp_path):
    api, app, *_ = make_api(tmp_path)
    code, payload, _ = call(api, "POST", "/api/settings", {"on_pm": 5})
    assert code == 400 and json.loads(payload)["errors"]
    assert call(api, "POST", "/api/settings", {"on_pm": 80})[0] == 200 and app.cfg.on_pm == 80
    assert call(api, "POST", "/api/settings", {"pin": "4821"})[0] == 200
    assert call(api, "POST", "/api/auth", pin="0000")[0] == 403
    assert call(api, "POST", "/api/auth", pin="4821")[0] == 200
    assert call(api, "POST", "/api/settings/reset", pin="4821")[0] == 200
    assert app.cfg.on_pm == DEFAULTS["on_pm"] and app.cfg.pin == "4821"


def test_filter_reset_endpoint(tmp_path):
    api, app, *_ = make_api(tmp_path)
    app.ctl.total_run_s = 5000
    assert call(api, "POST", "/api/filter/reset")[0] == 200
    assert app.ctl.total_run_s == 0


def test_downloads_and_page_are_file_responses(tmp_path):
    api, app, room, bank, store, sent, t = make_api(tmp_path)
    code, payload, extra = call(api, "GET", "/api/log.csv", pin=None)
    assert code == 200 and payload == ""                      # nothing logged yet
    run_app(app, room, t, 3 * 3600)
    code, payload, extra = call(api, "GET", "/api/log.csv", pin=None)
    assert payload[0] == "file" and "attachment" in extra["Content-Disposition"]
    assert call(api, "GET", "/", pin=None)[1][0] == "file"


# ---- HTTP plumbing
def test_request_line_and_head():
    assert parse_request_line("GET /api/status HTTP/1.1\r\n") == ("GET", "/api/status")
    assert parse_request_line("garbage") is None
    head = build_head(200, "text/plain", 5, {"X-A": "b"}).decode()
    assert head.startswith("HTTP/1.0 200 OK") and "Content-Length: 5" in head and "X-A: b" in head


def test_real_server_end_to_end(tmp_path):
    (tmp_path / "index.html").write_text("<h1>hi</h1>")
    api, app, room, bank, store, sent, t = make_api(tmp_path)

    async def scenario():
        server = await serve(api, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        async def fetch(raw):
            r, w = await asyncio.open_connection("127.0.0.1", port)
            w.write(raw)
            await w.drain()
            data = await r.read()
            w.close()
            return data

        status = await fetch(b"GET /api/status HTTP/1.1\r\nHost: x\r\n\r\n")
        page = await fetch(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
        body = b'{"cmd": "speed:2"}'
        cmd = await fetch(b"POST /api/command HTTP/1.1\r\nX-Pin: 0000\r\nContent-Length: "
                          + str(len(body)).encode() + b"\r\n\r\n" + body)
        huge = await fetch(b"POST /api/command HTTP/1.1\r\nContent-Length: 99999\r\n\r\n")
        server.close()
        return status, page, cmd, huge

    status, page, cmd, huge = asyncio.run(scenario())
    assert status.startswith(b"HTTP/1.0 200") and b'"aqi"' in status
    assert page.endswith(b"<h1>hi</h1>")
    assert cmd.startswith(b"HTTP/1.0 200") and bank.speed == 2
    assert huge.startswith(b"HTTP/1.0 413")
