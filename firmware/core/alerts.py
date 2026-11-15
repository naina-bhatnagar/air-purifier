"""When to send a "severe air" notification."""


class SevereAlert:
    def __init__(self, cfg):
        self.cfg = cfg
        self.since = None
        self.last_sent = None

    def update(self, now, band):
        """Returns a message when air has been severe long enough and the gap has passed."""
        if band != "severe":
            self.since = None
            return None
        if self.since is None:
            self.since = now
        long_enough = now - self.since >= self.cfg.severe_alert_s
        gap_ok = self.last_sent is None or now - self.last_sent >= self.cfg.alert_gap_s
        if long_enough and gap_ok:
            self.last_sent = now
            return "Air quality has been severe for %d min" % ((now - self.since) // 60)
        return None
