from core.app import SAMPLE_S, App
from core.controller import Controller
from core.relays import RelayBank
from core.settings import Settings
from drivers.sim import SimRoom, SimSensor
from storage.filestore import FileStore

WALL0 = 1_800_000_000


def make_ctl(**overrides):
    """A Controller with fake sensor values you can change: vals['b'], vals['a']."""
    cfg = Settings()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    events = []
    bank = RelayBank(lambda pins: None)
    ctl = Controller(cfg, bank, lambda now, level, msg: events.append((level, msg)))
    return ctl, {"b": 10.0, "a": 10.0}, bank, events


def run_ctl(ctl, vals, start, seconds, step=5):
    t = start
    while t < start + seconds:
        ctl.tick(t, vals["b"], vals["a"])
        t += step
    return t


def make_app(root, boot="test", room=None, now=0.0):
    room = room or SimRoom(seed=1)
    bank = RelayBank(lambda pins: None)
    store = FileStore(str(root))
    sent = []
    t = {"now": now}
    sensors = (SimSensor(room), SimSensor(room, after=True))
    app = App(store, bank, sensors[0], sensors[1], lambda: WALL0 + t["now"], sent.append,
              now=now, boot_reason=boot)
    return app, room, bank, store, sent, t, sensors


def run_app(app, room, t, seconds):
    end = t["now"] + seconds
    while t["now"] < end:
        room.step(SAMPLE_S, app.relays.speed)
        app.step(t["now"])
        t["now"] += SAMPLE_S
