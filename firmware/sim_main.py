"""Run the whole system on your computer with a simulated room, sensors and relays.

    python firmware/sim_main.py            then open http://127.0.0.1:8080
    python firmware/sim_main.py --speed 120 --clog-after 1

Outdoor pollution rises and falls on a 3-hour cycle so you can watch the controller react.
Default PIN is 0000. Telegram messages are printed here instead of being sent.
"""
import argparse
import asyncio
import math
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from core.app import SAMPLE_S, App  # noqa: E402
from core.relays import RelayBank  # noqa: E402
from drivers.sim import SimRoom, SimSensor  # noqa: E402
from net.api import Api  # noqa: E402
from net.server import serve  # noqa: E402
from storage.filestore import FileStore  # noqa: E402


async def run(args):
    data_dir = args.data or tempfile.mkdtemp(prefix="purifier-sim-")
    room = SimRoom(pm=40.0)
    relays = RelayBank(lambda pins: None)
    store = FileStore(data_dir)
    clock = {"now": 0.0}
    start = time.time()
    app = App(store, relays, SimSensor(room), SimSensor(room, after=True),
              lambda: start + clock["now"], lambda text: print("[telegram]", text),
              boot_reason="simulated start")
    api = Api(app, store, lambda: clock["now"], os.path.join(HERE, "web", "index.html"))
    await serve(api, "127.0.0.1", args.port)
    print("Simulation running at http://127.0.0.1:%d (PIN 0000, %gx speed)"
          % (args.port, args.speed))
    print("Data folder:", data_dir)
    while True:
        now = clock["now"]
        room.outdoor = 150 + 120 * math.sin(2 * math.pi * now / (3 * 3600))
        if args.clog_after and now >= args.clog_after * 3600:
            room.filter_eff = 0.3
        room.step(SAMPLE_S, relays.speed)
        app.step(now)
        clock["now"] = now + SAMPLE_S
        await asyncio.sleep(SAMPLE_S / args.speed)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--speed", type=float, default=30, help="simulated seconds per real second")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--clog-after", type=float, default=0,
                   help="simulated hours until the filter clogs")
    p.add_argument("--data", help="folder for logs and settings (default: a temp folder)")
    try:
        asyncio.run(run(p.parse_args()))
    except KeyboardInterrupt:
        pass
