"""Three-speed relay bank with an interlock: never more than one relay on."""


class RelayBank:
    def __init__(self, write, sleep=None, dead_s=0.2):
        """write(list_of_3_bools) drives the real pins (or records them in a simulation)."""
        self._write = write
        self._sleep = sleep
        self._dead = dead_s
        self.pins = [False, False, False]
        self.speed = 0
        self.switches = 0
        self._write(list(self.pins))

    def set_speed(self, speed):
        if speed not in (0, 1, 2, 3):
            raise ValueError("bad speed %r" % (speed,))
        if speed == self.speed:
            return
        self.pins = [False, False, False]      # everything off first
        self._write(list(self.pins))
        if speed:
            if self._sleep:
                self._sleep(self._dead)        # gap so two windings never overlap
            self.pins[speed - 1] = True
            self._write(list(self.pins))
        self.speed = speed
        self.switches += 1
        assert sum(self.pins) <= 1

    def all_off(self):
        self.set_speed(0)
