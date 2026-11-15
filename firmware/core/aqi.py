"""PM2.5 to AQI. Breakpoint tables are (pm_low, pm_high, aqi_low, aqi_high)."""

CPCB = [  # India
    (0, 30, 0, 50), (30, 60, 50, 100), (60, 90, 100, 200),
    (90, 120, 200, 300), (120, 250, 300, 400), (250, 500, 400, 500),
]
EPA = [  # US, 2024 revision
    (0, 9.0, 0, 50), (9.0, 35.4, 50, 100), (35.4, 55.4, 100, 150),
    (55.4, 125.4, 150, 200), (125.4, 225.4, 200, 300), (225.4, 500, 300, 500),
]
TABLES = {"cpcb": CPCB, "epa": EPA}


def pm25_to_aqi(pm, scale="cpcb"):
    pm = max(0.0, pm)
    for lo, hi, alo, ahi in TABLES[scale]:
        if pm <= hi:
            return int(round(alo + (pm - lo) * (ahi - alo) / (hi - lo)))
    return 500


def aqi_band(aqi):
    """The four status-light bands."""
    if aqi <= 50:
        return "best"       # green
    if aqi <= 100:
        return "average"    # yellow
    if aqi <= 200:
        return "moderate"   # orange
    return "severe"         # red
