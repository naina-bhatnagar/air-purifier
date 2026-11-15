"""Status LEDs and push buttons."""


class Leds:
    ORDER = ("best", "average", "moderate", "severe")    # green, yellow, orange, red

    def __init__(self, pins):
        self.pins = pins

    def set_band(self, band):
        for name, pin in zip(self.ORDER, self.pins):
            pin.value(1 if name == band else 0)


class Debouncer:
    def __init__(self, n, stable_ms=40):
        self.stable = [False] * n
        self.cand = [False] * n
        self.since = [0] * n
        self.stable_ms = stable_ms

    def update(self, raw, now_ms):
        """raw: list of bool (True = pressed). Returns indexes pressed since last call."""
        pressed = []
        for i, r in enumerate(raw):
            if r != self.cand[i]:
                self.cand[i] = r
                self.since[i] = now_ms
            elif r != self.stable[i] and now_ms - self.since[i] >= self.stable_ms:
                self.stable[i] = r
                if r:
                    pressed.append(i)
        return pressed


def button_command(index, speed):
    """Buttons: 0 start/stop, 1 faster, 2 slower, 3 back to auto."""
    if index == 0:
        return "off" if speed > 0 else "speed:1"
    return ("up", "down", "auto")[index - 1]
