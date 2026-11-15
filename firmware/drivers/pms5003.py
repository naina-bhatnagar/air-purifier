"""Plantower PMS5003 driver. Frame parsing is pure Python so it can be unit tested."""


def parse_frame(f):
    """f is 32 bytes. Returns (pm25, pm10) in ug/m3 (atmospheric), or None if invalid."""
    if len(f) != 32 or f[0] != 0x42 or f[1] != 0x4D:
        return None
    if ((f[2] << 8) | f[3]) != 28:
        return None
    if (sum(f[:30]) & 0xFFFF) != ((f[30] << 8) | f[31]):
        return None
    return ((f[12] << 8) | f[13], (f[14] << 8) | f[15])


def latest_reading(buf):
    """Scan buf for valid frames. Returns (newest reading or None, leftover bytes)."""
    best = None
    i = 0
    n = len(buf)
    while i + 32 <= n:
        if buf[i] == 0x42 and buf[i + 1] == 0x4D:
            r = parse_frame(buf[i:i + 32])
            if r is not None:
                best = r
                i += 32
                continue
        i += 1
    return best, buf[i:]


class PMS5003:
    def __init__(self, uart):
        """uart: a machine.UART at 9600 baud, created with rxbuf of 512 or more."""
        self.uart = uart
        self.buf = b""

    def read(self):
        """Non-blocking. Returns the newest (pm25, pm10) since the last call, or None."""
        n = self.uart.any()
        if n:
            data = self.uart.read(n)
            if data:
                self.buf = (self.buf + data)[-256:]
        reading, self.buf = latest_reading(self.buf)
        return reading
