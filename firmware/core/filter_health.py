"""Filter efficiency from two sensors: 1 - (PM after filter / PM before filter)."""
from core.ring import Ring


class FilterHealth:
    def __init__(self, cfg, size=60, settle_s=120, min_pm=20.0):
        self.cfg = cfg
        self.ring = Ring(size)
        self.settle_s = settle_s    # wait after a speed change before judging
        self.min_pm = min_pm        # air must be dirty enough for a meaningful ratio
        self.alerted = False
        self.last = None            # this tick's efficiency, or None if not measurable

    def update(self, now, speed, speed_since, before, after):
        """Returns a message once when the filter needs replacing, else None."""
        if speed == 0 or now - speed_since < self.settle_s or before < self.min_pm:
            return None
        e = min(1.0, max(0.0, 1.0 - after / before))
        self.last = e
        self.ring.append(e)
        if self.ring.full() and not self.alerted:
            m = self.ring.mean()
            if m < self.cfg.min_eff:
                self.alerted = True
                return "Filter efficiency is %d%%: replace the filter" % int(round(m * 100))
        return None

    def current(self):
        """Rolling average of recent valid readings, or None."""
        return self.ring.mean() if len(self.ring) else None

    def reset(self):
        self.ring.clear()
        self.alerted = False
        self.last = None
