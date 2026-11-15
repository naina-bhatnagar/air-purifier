"""DS3231 real-time clock over I2C. Stores UTC."""
from core.timeutil import tuple_from_unix, unix_from_tuple

ADDR = 0x68
MIN_VALID = 1735689600      # 2025-01-01: anything older means the clock lost power


def _bcd(n):
    return (n // 10) << 4 | (n % 10)


def _dec(b):
    return (b >> 4) * 10 + (b & 0x0F)


def decode(regs):
    """7 register bytes -> Unix seconds."""
    sec, mi, hr = _dec(regs[0] & 0x7F), _dec(regs[1] & 0x7F), _dec(regs[2] & 0x3F)
    day, mon, yr = _dec(regs[4] & 0x3F), _dec(regs[5] & 0x1F), _dec(regs[6])
    return unix_from_tuple(2000 + yr, mon, day, hr, mi, sec)


def encode(ts):
    """Unix seconds -> 7 register bytes."""
    y, mo, d, h, mi, s = tuple_from_unix(ts)
    return bytes([_bcd(s), _bcd(mi), _bcd(h), 1, _bcd(d), _bcd(mo), _bcd(y - 2000)])


class DS3231:
    def __init__(self, i2c):
        self.i2c = i2c

    def read_unix(self):
        """Returns Unix seconds, or None if the clock has not been set."""
        ts = decode(self.i2c.readfrom_mem(ADDR, 0, 7))
        return ts if ts >= MIN_VALID else None

    def write_unix(self, ts):
        self.i2c.writeto_mem(ADDR, 0, encode(ts))
