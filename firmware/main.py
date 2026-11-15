"""ESP32 entry point (MicroPython 1.22 or newer).

Tasks:  control loop (feeds the watchdog), buttons, WiFi + clock sync, web server, Telegram.
The control loop never waits on the network. If it hangs or keeps failing, the hardware
watchdog resets the board and the fan comes back in its last saved state.
"""
import asyncio
import time

import machine
import network
import ntptime
import pins
import private
from core.app import SAMPLE_S, App
from core.clock import Mono
from core.relays import RelayBank
from core.timeutil import unix_from_tuple
from drivers.ds3231 import DS3231
from drivers.panel import Debouncer, Leds, button_command
from drivers.pms5003 import PMS5003
from net.api import Api
from net.server import serve
from net.telegram import Notifier, Telegram
from storage.filestore import FileStore

WDT_MS = 20000
MAX_STEP_FAILURES = 10
NTP_EVERY_S = 24 * 3600


def reset_reason():
    names = (("PWRON_RESET", "power came back"), ("WDT_RESET", "watchdog reset after a hang"),
             ("SOFT_RESET", "soft reset"), ("HARD_RESET", "hard reset"),
             ("DEEPSLEEP_RESET", "woke from deep sleep"))
    cause = machine.reset_cause()
    for const, text in names:
        if getattr(machine, const, None) == cause:
            return text
    return "unknown reset"


def wall():
    """UTC Unix seconds from the board clock (kept in step with the DS3231)."""
    t = time.localtime()
    return unix_from_tuple(t[0], t[1], t[2], t[3], t[4], t[5])


def load_clock_from_rtc(ds):
    ts = ds.read_unix()
    if ts is None:
        return
    from core.timeutil import tuple_from_unix
    y, mo, d, h, mi, s = tuple_from_unix(ts)
    machine.RTC().datetime((y, mo, d, 0, h, mi, s, 0))


async def wifi_task(notifier, ds, mono):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    last_sync = None
    while True:
        if not wlan.isconnected():
            try:
                wlan.connect(private.WIFI_SSID, private.WIFI_PASSWORD)
            except OSError:
                pass
            for _ in range(30):
                if wlan.isconnected():
                    break
                await asyncio.sleep(1)
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            if notifier.base_url != "http://" + ip:
                notifier.base_url = "http://" + ip
                print("Dashboard:", notifier.base_url)
            if last_sync is None or mono() - last_sync >= NTP_EVERY_S:
                try:
                    ntptime.timeout = 2
                    ntptime.settime()               # sets the board clock to UTC
                    ds.write_unix(wall())           # keep the DS3231 in step
                    last_sync = mono()
                except Exception as e:
                    print("NTP failed:", e)
                    last_sync = mono() - NTP_EVERY_S + 600      # retry in 10 minutes
        await asyncio.sleep(10)


async def control_loop(app, wdt, mono):
    failures = 0
    while True:
        try:
            app.step(mono())
            failures = 0
        except Exception as e:
            failures += 1
            print("step failed:", e)
            if failures >= MAX_STEP_FAILURES:
                app.failsafe()      # fan off, then stop feeding the watchdog so we reboot
                while True:
                    await asyncio.sleep(60)
        wdt.feed()
        await asyncio.sleep(SAMPLE_S)


async def buttons_loop(app, button_pins, mono):
    deb = Debouncer(len(button_pins))
    while True:
        now = mono()
        for i in deb.update([p.value() == 0 for p in button_pins], now * 1000):
            try:
                app.handle_command(button_command(i, app.relays.speed), now)
            except Exception as e:
                print("button error:", e)
        await asyncio.sleep_ms(20)


async def main():
    wdt = machine.WDT(timeout=WDT_MS)
    mono = Mono(time.ticks_ms, time.ticks_diff)

    i2c = machine.I2C(pins.I2C_ID, scl=machine.Pin(pins.I2C_SCL), sda=machine.Pin(pins.I2C_SDA))
    ds = DS3231(i2c)
    try:
        load_clock_from_rtc(ds)
    except OSError as e:
        print("RTC not found:", e)

    off = 1 if pins.RELAY_ACTIVE_LOW else 0
    relay_pins = [machine.Pin(p, machine.Pin.OUT, value=off) for p in pins.RELAY_PINS]

    def write(states):
        for pin, on in zip(relay_pins, states):
            pin.value((0 if pins.RELAY_ACTIVE_LOW else 1) if on else off)

    relays = RelayBank(write, sleep=time.sleep)

    def uart(uid, rx, tx):
        return PMS5003(machine.UART(uid, baudrate=9600, rx=rx, tx=tx, rxbuf=512))

    leds = Leds([machine.Pin(p, machine.Pin.OUT, value=0) for p in pins.LED_PINS])
    button_pins = [machine.Pin(p, machine.Pin.IN, machine.Pin.PULL_UP) for p in pins.BUTTON_PINS]

    notifier = Notifier()
    store = FileStore("/data")
    app = App(store, relays,
              uart(pins.BEFORE_UART, pins.BEFORE_RX, pins.BEFORE_TX),
              uart(pins.AFTER_UART, pins.AFTER_RX, pins.AFTER_TX),
              wall, notifier, now=mono(), boot_reason=reset_reason(), leds=leds)
    api = Api(app, store, mono, "/web/index.html")

    asyncio.create_task(control_loop(app, wdt, mono))
    asyncio.create_task(buttons_loop(app, button_pins, mono))
    asyncio.create_task(wifi_task(notifier, ds, mono))
    await serve(api, "0.0.0.0", 80)
    if private.TELEGRAM_TOKEN and private.TELEGRAM_CHAT_ID:
        bot = Telegram(private.TELEGRAM_TOKEN, private.TELEGRAM_CHAT_ID, notifier, app.status)
        asyncio.create_task(bot.run())
    while True:
        await asyncio.sleep(60)


asyncio.run(main())
