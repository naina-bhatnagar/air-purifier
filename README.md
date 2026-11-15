# Room air purifier controller

An ESP32 reads two particle sensors (before and after a homemade filter), switches a
3-speed cooler fan through relays, logs hourly summaries, serves a live dashboard on your
home WiFi, and sends a few Telegram alerts.

The decision logic is plain Python with no hardware imports, so it runs unchanged on your
computer against a simulated room. That is how all the tests run.

## Layout

```
firmware/
  core/       decision logic: controller, AQI, filter health, alerts, hourly log, settings, App
  drivers/    PMS5003, DS3231 clock, relays are in core/relays.py, LEDs and buttons, simulator
  storage/    flash-friendly file store (JSON settings/state, trimmed CSV logs)
  net/        HTTP server, API with PIN, minimal Telegram client
  web/        index.html, the whole dashboard in one file
  main.py     ESP32 entry point         sim_main.py  run everything on your computer
  pins.py     pin numbers (placeholders, set them to your wiring)
tests/        unit, integration and end-to-end server tests
.github/      CI: lint, tests, dashboard script check
```

## Getting Started

```
python firmware/sim_main.py            # then open http://127.0.0.1:8080, PIN 0000 (default)
python firmware/sim_main.py --speed 120 --clog-after 1b
```

Outdoor pollution rises and falls on a 3-hour cycle, so you can watch it start, change
speed, rest and stop. Telegram messages print in the terminal.

## Tests and CI

```
pip install pytest ruff
ruff check .
python -m pytest -q
```

CI runs the same on every push (Python 3.11 and 3.12). There is no deployment step yet:
nothing to deploy until the board is wired.

## What it does

- **Auto:** starts at PM2.5 of 60 or more, stops at 35 or less (1-minute average).
  Speed follows the level (medium from 90, high from 150, never changed faster than once a
  minute). After 60 minutes running it rests 30 minutes.
- **Manual:** buttons or the dashboard override auto. After a restart the fan returns to
  the speed you set. Auto mode restarts off and decides from fresh readings.
- **Hard limits (not adjustable):** one relay at a time with a gap between speeds, and a
  6-hour cap on any manual run.
- **Sensor lost:** auto mode turns the fan off, manual keeps working, the page shows a banner.
- **Dashboard:** AQI and band, both sensors (now and 1-minute average, PM2.5 and PM10),
  filter efficiency, fan state, a 10 or 30 minute graph, controls and settings behind a PIN,
  CSV downloads. If the board stops answering while the page is open it says offline.
- **Log:** one row per hour (average, min and max PM2.5, PM10, AQI, run minutes, speed,
  filter efficiency), plus an events log. Both are trimmed to a fixed size.
- **Telegram:** only "replace the filter" (and the run-hours reminder), severe air that lasts,
  "restarted: power came back / watchdog reset", and a reply to any message mentioning AQI.
  Everything else gets the dashboard link. Only your chat id is answered.
- **Settings:** change thresholds, run and rest times, alert rules, AQI scale (India or US)
  and time zone from the page. Saved in flash and kept after restarts. Invalid combinations
  are rejected, and unreadable saved settings fall back to defaults with a warning.

## Putting it on the ESP32

1. Install MicroPython 1.22 or newer.
2. Edit `firmware/pins.py` to match your wiring.
3. Copy `firmware/private_example.py` to `firmware/private.py`, fill in WiFi (and Telegram).
4. Copy everything in `firmware/` to the board except `sim_main.py`, for example
   `mpremote cp -r firmware/. :` (`private.py` is git-ignored on purpose).
5. Reset the board. The serial console prints the dashboard address.
6. Change the PIN from 0000 on the dashboard.

## What is not verified

Everything above is tested in simulation only. Not yet checked on real hardware: the
PMS5003 and DS3231 drivers on real wires, relay switching, MicroPython compatibility of the
networking code, Telegram over TLS on the board, and memory use. The Telegram and WiFi calls
all have timeouts, but a stuck DNS lookup can still pause the board for a few seconds, which
is why the relays hold their state and the watchdog only watches the control loop.
Test the relays with no mains connected first.
