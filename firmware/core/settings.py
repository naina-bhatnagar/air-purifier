"""Adjustable settings: defaults, limits and validation."""

DEFAULT_PIN = "0000"
HARD_MAX_MANUAL_S = 6 * 3600   # fixed safety limit, not adjustable

DEFAULTS = {
    "on_pm": 60,            # start fan at or above (ug/m3 PM2.5)
    "off_pm": 35,           # stop fan at or below
    "med_pm": 90,           # medium speed from here
    "high_pm": 150,         # high speed from here
    "max_run_s": 3600,      # longest continuous auto run
    "rest_s": 1800,         # rest after a long run
    "min_eff": 0.5,         # replace-filter alert below this efficiency
    "filter_hours": 300,    # backup reminder, run hours
    "severe_alert_s": 600,  # severe air must last this long before an alert
    "alert_gap_s": 3600,    # minimum gap between severe alerts
    "aqi_scale": "cpcb",
    "tz_offset_min": 330,   # minutes from UTC (India = 330)
    "pin": DEFAULT_PIN,
}

LIMITS = {
    "on_pm": (10, 500), "off_pm": (5, 400), "med_pm": (20, 600), "high_pm": (30, 800),
    "max_run_s": (600, 10800), "rest_s": (300, 7200),
    "min_eff": (0.1, 0.9), "filter_hours": (10, 2000),
    "severe_alert_s": (60, 7200), "alert_gap_s": (300, 86400),
    "tz_offset_min": (-720, 840),
}

CHOICES = {"aqi_scale": ("cpcb", "epa")}


def _check(key, value):
    """Returns (clean_value, error)."""
    if key == "pin":
        if isinstance(value, str) and value.isdigit() and 4 <= len(value) <= 8:
            return value, None
        return None, "must be 4 to 8 digits"
    if key in CHOICES:
        if value in CHOICES[key]:
            return value, None
        return None, "must be one of " + ", ".join(CHOICES[key])
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, "must be a number"
    lo, hi = LIMITS[key]
    if not lo <= value <= hi:
        return None, "must be between %s and %s" % (lo, hi)
    if isinstance(DEFAULTS[key], int):
        if value != int(value):
            return None, "must be a whole number"
        return int(value), None
    return float(value), None


def _cross(c):
    errs = []
    if c["off_pm"] >= c["on_pm"]:
        errs.append("off_pm must be lower than on_pm")
    if c["med_pm"] < c["on_pm"]:
        errs.append("med_pm must be at least on_pm")
    if c["high_pm"] <= c["med_pm"]:
        errs.append("high_pm must be above med_pm")
    return errs


class Settings:
    def __init__(self, saved=None):
        self.fallback = False   # True if saved settings were unusable
        self.reset()
        if saved is not None:
            if not isinstance(saved, dict):
                self.fallback = True
            else:
                known = {k: v for k, v in saved.items() if k in DEFAULTS}
                if self.update(known):
                    self.reset()
                    self.fallback = True

    def reset(self, keep_pin=False):
        pin = getattr(self, "pin", DEFAULT_PIN)
        for k, v in DEFAULTS.items():
            setattr(self, k, v)
        if keep_pin:
            self.pin = pin

    def to_dict(self):
        return {k: getattr(self, k) for k in DEFAULTS}

    def public(self):
        d = self.to_dict()
        del d["pin"]
        return d

    def update(self, changes):
        """All-or-nothing. Returns a list of error strings (empty means applied)."""
        errs = []
        cand = self.to_dict()
        for k, v in changes.items():
            if k not in DEFAULTS:
                errs.append("unknown setting: " + str(k))
                continue
            val, err = _check(k, v)
            if err:
                errs.append(k + ": " + err)
            else:
                cand[k] = val
        if not errs:
            errs = _cross(cand)
        if errs:
            return errs
        for k, v in cand.items():
            setattr(self, k, v)
        return []
