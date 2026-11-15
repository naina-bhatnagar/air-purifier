"""Simulated room and sensors for running everything without hardware."""
import random


class SimRoom:
    """PM2.5 leaks in from outdoors and is removed by the purifier."""

    def __init__(self, pm=40.0, outdoor=120.0, leak=0.0002, clean=0.0004,
                 filter_eff=0.9, seed=1):
        self.pm = pm
        self.outdoor = outdoor
        self.leak = leak
        self.clean = clean
        self.filter_eff = filter_eff
        self.speed = 0
        self.rng = random.Random(seed)

    def step(self, dt, speed):
        self.speed = speed
        removal = self.clean * speed * self.filter_eff
        self.pm += ((self.outdoor - self.pm) * self.leak - removal * self.pm) * dt
        self.pm = max(0.0, self.pm)

    def before_pm25(self):
        return max(0.0, self.pm + self.rng.gauss(0, 2))

    def after_pm25(self):
        keep = (1 - self.filter_eff) if self.speed else 1.0
        return max(0.0, self.pm * keep + self.rng.gauss(0, 1))


class SimSensor:
    """Same read() interface as the real PMS5003 driver."""

    def __init__(self, room, after=False):
        self.room = room
        self.after = after
        self.dead = False       # set True to simulate an unplugged sensor

    def read(self):
        if self.dead:
            return None
        pm25 = self.room.after_pm25() if self.after else self.room.before_pm25()
        return (pm25, pm25 * 1.6)
