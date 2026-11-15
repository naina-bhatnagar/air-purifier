"""The decision logic. No hardware, storage or network code in here."""
from core.aqi import aqi_band, pm25_to_aqi
from core.filter_health import FilterHealth
from core.ring import Ring
from core.settings import HARD_MAX_MANUAL_S

MIN_SWITCH_S = 60       # minimum time between automatic speed changes
MISSING_LIMIT = 6       # missed readings in a row before the sensor counts as lost
WINDOW = 12             # readings in the 1-minute average (12 x 5 s)


class Controller:
    def __init__(self, cfg, relays, on_event=None):
        """on_event(now, level, message), level is "info", "warn" or "alert"."""
        self.cfg = cfg
        self.relays = relays
        self.on_event = on_event or (lambda now, level, msg: None)
        self.window = Ring(WINDOW)
        self.filter = FilterHealth(cfg)
        self.state = "IDLE"         # IDLE, RUNNING, REST or MANUAL
        self.mode = "AUTO"          # AUTO or MANUAL
        self.manual_speed = 0
        self.since = 0.0            # when the current state began
        self.speed_since = 0.0
        self.manual_since = 0.0
        self.total_run_s = 0.0
        self.hours_alerted = False
        self.last_tick = None
        self.missing = 0
        self.fault = False
        self.avg = 0.0
        self.aqi = 0
        self.band = "best"
        self.dirty = False          # persistent state changed, caller should save

    # ---- helpers
    def _event(self, now, msg, level="info"):
        self.on_event(now, level, msg)

    def _set_state(self, now, state):
        if state != self.state:
            self._event(now, "%s -> %s" % (self.state, state))
            self.state = state
            self.since = now
            self.dirty = True

    def _apply(self, now, speed):
        if speed != self.relays.speed:
            self.speed_since = now
            self.relays.set_speed(speed)

    # ---- persistence
    def snapshot(self):
        return {
            "mode": self.mode,
            "manual_speed": self.manual_speed,
            "total_run_s": int(self.total_run_s),
            "filter_alerted": self.filter.alerted,
            "hours_alerted": self.hours_alerted,
        }

    def restore(self, saved, now):
        """After a restart: same run-hours, and manual mode keeps the speed you set."""
        self.total_run_s = float(saved.get("total_run_s", 0))
        self.filter.alerted = bool(saved.get("filter_alerted", False))
        self.hours_alerted = bool(saved.get("hours_alerted", False))
        speed = saved.get("manual_speed", 0)
        if saved.get("mode") == "MANUAL" and speed in (0, 1, 2, 3):
            self.mode = "MANUAL"
            self.manual_speed = speed
            self.state = "MANUAL"
            self.since = self.manual_since = now
            self._apply(now, speed)
            self._event(now, "Restored manual speed %d after restart" % speed)

    def filter_replaced(self, now):
        self.filter.reset()
        self.total_run_s = 0.0
        self.hours_alerted = False
        self.dirty = True
        self._event(now, "Filter replaced, counters reset")

    # ---- commands from buttons and the web page
    def command(self, cmd, now):
        """auto, off, up, down or speed:N. Raises ValueError for anything else."""
        if cmd == "auto":
            self.mode = "AUTO"
            self.manual_speed = 0
            self._set_state(now, "IDLE")
            self.since = now
            self._apply(now, 0)
            self._event(now, "Back to auto mode")
        else:
            if cmd.startswith("speed:"):
                s = int(cmd[6:])
            elif cmd == "off":
                s = 0
            elif cmd == "up":
                s = min(3, self.relays.speed + 1)
            elif cmd == "down":
                s = max(0, self.relays.speed - 1)
            else:
                raise ValueError("unknown command: %s" % cmd)
            if s not in (0, 1, 2, 3):
                raise ValueError("speed must be 0 to 3")
            self.mode = "MANUAL"
            self.manual_speed = s
            self.manual_since = now
            self._set_state(now, "MANUAL")
            self._event(now, "Manual speed %d" % s)
            self._apply(now, s)
        self.dirty = True

    # ---- automatic logic
    def _auto_target(self):
        if self.avg < self.cfg.med_pm:
            return 1
        return 2 if self.avg < self.cfg.high_pm else 3

    def _decide(self, now):
        c = self.cfg
        if self.mode == "MANUAL":
            if self.manual_speed > 0 and now - self.manual_since >= HARD_MAX_MANUAL_S:
                self.mode = "AUTO"
                self.manual_speed = 0
                self._set_state(now, "REST")
                self._event(now, "Manual run limit reached, resting before auto resumes", "warn")
                return 0
            return self.manual_speed
        if self.fault:                  # no air data: fail safe, fan off
            self._set_state(now, "IDLE")
            return 0
        if self.state == "IDLE":
            if self.window.full() and self.avg >= c.on_pm:
                self._set_state(now, "RUNNING")
        elif self.state == "RUNNING":
            if self.avg <= c.off_pm:
                self._set_state(now, "IDLE")
            elif now - self.since >= c.max_run_s:
                self._set_state(now, "REST")
                self._event(now, "Run limit reached, resting")
        elif self.state == "REST":
            if now - self.since >= c.rest_s:
                self._set_state(now, "IDLE")
        if self.state != "RUNNING":
            return 0
        target, cur = self._auto_target(), self.relays.speed
        if cur and target != cur and now - self.speed_since < MIN_SWITCH_S:
            return cur                  # don't flip speeds back and forth
        return target

    def tick(self, now, before, after):
        """One control step. before/after are PM2.5 readings, or None if unavailable."""
        dt = 0.0 if self.last_tick is None else now - self.last_tick
        self.last_tick = now
        if self.relays.speed > 0:
            self.total_run_s += dt
        self.filter.last = None
        if before is None:
            self.missing += 1
            if self.missing >= MISSING_LIMIT and not self.fault:
                self.fault = True
                self.window.clear()
                self._event(now, "Air sensor not responding", "warn")
        else:
            self.missing = 0
            if self.fault:
                self.fault = False
                self._event(now, "Air sensor responding again")
            self.window.append(before)
            self.avg = self.window.mean()
            self.aqi = pm25_to_aqi(self.avg, self.cfg.aqi_scale)
            self.band = aqi_band(self.aqi)
        self._apply(now, self._decide(now))
        if before is not None and after is not None:
            msg = self.filter.update(now, self.relays.speed, self.speed_since, before, after)
            if msg:
                self.dirty = True
                self._event(now, msg, "alert")
        if not self.hours_alerted and self.total_run_s >= self.cfg.filter_hours * 3600:
            self.hours_alerted = True
            self.dirty = True
            self._event(now, "%d run hours: time to check the filter" % self.cfg.filter_hours,
                        "alert")
