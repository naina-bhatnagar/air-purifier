"""Date maths that ignores the platform epoch (MicroPython uses 2000, CPython 1970).

All wall-clock values in this project are Unix seconds in UTC.
"""


def _days_from_civil(y, m, d):
    if m <= 2:
        y -= 1
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    mp = m - 3 if m > 2 else m + 9
    doy = (153 * mp + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(z):
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    if m <= 2:
        y += 1
    return y, m, d


def unix_from_tuple(y, mo, d, h=0, mi=0, s=0):
    return _days_from_civil(y, mo, d) * 86400 + h * 3600 + mi * 60 + s


def tuple_from_unix(ts):
    days, rem = divmod(int(ts), 86400)
    y, mo, d = _civil_from_days(days)
    return y, mo, d, rem // 3600, rem % 3600 // 60, rem % 60


def iso_local(ts, tz_min=0):
    y, mo, d, h, mi, _ = tuple_from_unix(ts + tz_min * 60)
    return "%04d-%02d-%02d %02d:%02d" % (y, mo, d, h, mi)
