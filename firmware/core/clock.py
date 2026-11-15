"""Monotonic seconds that never wrap.

ESP32 time.ticks_ms() wraps after about 12 days, which would break run timers.
Call the object at least every few seconds. Pass time.ticks_ms and time.ticks_diff.
"""


class Mono:
    def __init__(self, ticks_ms, ticks_diff):
        self._ms = ticks_ms
        self._diff = ticks_diff
        self._last = ticks_ms()
        self.t = 0.0

    def __call__(self):
        now = self._ms()
        self.t += self._diff(now, self._last) / 1000.0
        self._last = now
        return self.t
