"""One summary row per hour: the log you download from the dashboard."""
from core.timeutil import iso_local

HEADER = ("hour_start,pm25_avg,pm25_min,pm25_max,pm10_avg,aqi_avg,"
          "run_min,avg_speed,filter_eff_pct,samples")


class HourlyLog:
    HEADER = HEADER

    def __init__(self):
        self._reset(None)

    def _reset(self, key):
        self.key = key
        self.n = 0
        self.s25 = self.s10 = self.saqi = 0.0
        self.mn = self.mx = None
        self.run_s = self.speed_s = 0.0
        self.eff_s = 0.0
        self.eff_n = 0

    def add(self, local_ts, pm25, pm10, aqi, speed, dt, eff):
        """local_ts is wall time already shifted to local time. Returns a CSV row
        when a new hour begins, else None."""
        key = int(local_ts // 3600)
        row = None
        if self.key is None:
            self.key = key
        elif key != self.key:
            row = self._finish()
            self._reset(key)
        self.n += 1
        self.s25 += pm25
        self.s10 += pm10
        self.saqi += aqi
        self.mn = pm25 if self.mn is None else min(self.mn, pm25)
        self.mx = pm25 if self.mx is None else max(self.mx, pm25)
        if speed > 0:
            self.run_s += dt
            self.speed_s += speed * dt
        if eff is not None:
            self.eff_s += eff
            self.eff_n += 1
        return row

    def _finish(self):
        if self.n == 0:
            return None
        n = float(self.n)
        eff = "%d" % int(round(self.eff_s / self.eff_n * 100)) if self.eff_n else ""
        avg_speed = self.speed_s / self.run_s if self.run_s else 0.0
        return "%s,%.1f,%.1f,%.1f,%.1f,%d,%.1f,%.2f,%s,%d" % (
            iso_local(self.key * 3600), self.s25 / n, self.mn, self.mx, self.s10 / n,
            int(round(self.saqi / n)), self.run_s / 60.0, avg_speed, eff, self.n)
