"""Wires sensors, controller, storage and notifications together.

step() runs one sample. The same App runs on the ESP32 and in the PC simulation.
"""
from core.alerts import SevereAlert
from core.controller import Controller
from core.hourly import HourlyLog
from core.ring import Ring
from core.settings import DEFAULT_PIN, Settings
from core.timeutil import iso_local

SAMPLE_S = 5
LIVE_POINTS = 360          # 30 minutes at one point per 5 s
MAX_HOURLY_ROWS = 9600     # about 400 days
MAX_EVENT_ROWS = 400
EVENT_HEADER = "time,level,message"
KEYS = ("b25", "b10", "a25", "a10")   # before/after filter, PM2.5/PM10


def _r1(x):
    return None if x is None else round(x, 1)


def _pct(x):
    return None if x is None else int(round(x * 100))


class App:
    def __init__(self, store, relays, before, after, wall, notify,
                 now=0.0, boot_reason="power-on", leds=None):
        """before/after: objects with read() -> (pm25, pm10) or None.
        wall(): Unix seconds (UTC). notify(text): queue a Telegram message."""
        self.store, self.relays = store, relays
        self.before, self.after = before, after
        self.wall, self.notify, self.leds = wall, notify, leds
        self.notes = []                 # start-up warnings shown on the page

        self.cfg = Settings(store.load_json("settings.json"))
        if "settings.json" in store.corrupt:
            self.cfg.fallback = True
        if self.cfg.fallback:
            self.notes.append("Saved settings could not be read, defaults are in use")
        self.ctl = Controller(self.cfg, relays, self._on_event)
        self.hourly = HourlyLog()
        self.severe = SevereAlert(self.cfg)
        self.live = Ring(LIVE_POINTS)
        self.win = {k: Ring(12) for k in KEYS}
        self.inst = {k: None for k in KEYS}
        self._last_step = None

        self.ctl.restore(store.load_json("state.json") or {}, now)
        self._on_event(now, "alert", "Purifier restarted: %s" % boot_reason)

    # ---- events and storage
    def _safe(self, fn, *args):
        try:
            fn(*args)
        except Exception as e:      # storage trouble must never stop the control loop
            print("storage error:", e)

    def _on_event(self, now, level, msg):
        line = "%s,%s,%s" % (iso_local(self.wall(), self.cfg.tz_offset_min), level,
                             msg.replace(",", ";").replace("\n", " "))
        self._safe(self.store.append_line, "events.csv", line, MAX_EVENT_ROWS, EVENT_HEADER)
        if level == "alert":
            self.notify(msg)

    def _save_state(self):
        self._safe(self.store.save_json, "state.json", self.ctl.snapshot())

    def recent_events(self, n=20):
        return self.store.tail("events.csv", n)

    # ---- one control step
    def _record(self, p, reading):
        if reading is None:
            self.inst[p + "25"] = self.inst[p + "10"] = None
            return
        for key, v in ((p + "25", reading[0]), (p + "10", reading[1])):
            self.inst[key] = v
            self.win[key].append(v)

    def step(self, now):
        dt = 0.0 if self._last_step is None else now - self._last_step
        self._last_step = now
        b, a = self.before.read(), self.after.read()
        self._record("b", b)
        self._record("a", a)
        b25 = b[0] if b else None
        a25 = a[0] if a else None
        self.ctl.tick(now, b25, a25)
        wall = self.wall()
        if self.leds:
            self.leds.set_band(self.ctl.band)
        if b25 is not None:
            msg = self.severe.update(now, self.ctl.band)
            if msg:
                self._on_event(now, "alert", msg)
            row = self.hourly.add(wall + self.cfg.tz_offset_min * 60, self.ctl.avg,
                                  self.inst["b10"], self.ctl.aqi, self.relays.speed,
                                  dt, self.ctl.filter.last)
            if row:
                self._safe(self.store.append_line, "hourly.csv", row, MAX_HOURLY_ROWS,
                           self.hourly.HEADER)
                self.ctl.dirty = True
        self.live.append((int(wall), _r1(b25), _r1(a25), _r1(self.ctl.avg), self.relays.speed))
        if self.ctl.dirty:
            self.ctl.dirty = False
            self._save_state()

    def failsafe(self):
        """Fan off. Called if the control step keeps failing."""
        self.relays.all_off()

    # ---- used by the web page and Telegram
    def handle_command(self, cmd, now):
        self.ctl.command(cmd, now)
        self.step_persist()

    def step_persist(self):
        if self.ctl.dirty:
            self.ctl.dirty = False
            self._save_state()

    def update_settings(self, changes):
        errs = self.cfg.update(changes)
        if not errs:
            self._safe(self.store.save_json, "settings.json", self.cfg.to_dict())
        return errs

    def reset_settings(self):
        self.cfg.reset(keep_pin=True)
        self._safe(self.store.save_json, "settings.json", self.cfg.to_dict())

    def filter_replaced(self, now):
        self.ctl.filter_replaced(now)
        self.step_persist()

    def live_points(self):
        return [list(p) for p in self.live.values()]

    def _sensor(self, p):
        if self.inst[p + "25"] is None:
            return None
        return {
            "pm25": _r1(self.inst[p + "25"]), "pm10": _r1(self.inst[p + "10"]),
            "pm25_avg": _r1(self.win[p + "25"].mean()), "pm10_avg": _r1(self.win[p + "10"].mean()),
        }

    def status(self):
        c, f = self.ctl, self.ctl.filter
        return {
            "time": int(self.wall()),
            "tz": self.cfg.tz_offset_min,
            "sample_s": SAMPLE_S,
            "before": self._sensor("b"),
            "after": self._sensor("a"),
            "aqi": c.aqi,
            "band": c.band,
            "scale": self.cfg.aqi_scale,
            "eff": {"now": _pct(f.last), "avg": _pct(f.current()), "alert": f.alerted},
            "state": c.state,
            "mode": c.mode,
            "speed": self.relays.speed,
            "fault": c.fault,
            "run_hours": round(c.total_run_s / 3600.0, 1),
            "filter_hours": self.cfg.filter_hours,
            "default_pin": self.cfg.pin == DEFAULT_PIN,
            "notes": self.notes,
        }
