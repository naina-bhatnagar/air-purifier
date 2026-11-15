"""Request handling for the dashboard. Pure Python: no sockets, easy to test.

handle() returns (status_code, content_type, payload, extra_headers).
payload is a string, or ("file", path) to stream a file from flash.
"""
import json

from core.app import SAMPLE_S
from core.settings import CHOICES, DEFAULTS, LIMITS

MAX_FAILS = 5
LOCK_S = 60


def _same(a, b):
    """Compare strings without stopping at the first difference."""
    if len(a) != len(b):
        return False
    diff = 0
    for x, y in zip(a, b):
        diff |= ord(x) ^ ord(y)
    return diff == 0


class Api:
    def __init__(self, app, store, clock, web_file):
        """clock(): monotonic seconds. web_file: path of index.html."""
        self.app, self.store, self.clock, self.web_file = app, store, clock, web_file
        self.fails = 0
        self.locked_until = 0.0

    # ---- helpers
    def _json(self, code, obj):
        return code, "application/json", json.dumps(obj), {}

    def _file(self, name, ctype, download):
        extra = {"Content-Disposition": 'attachment; filename="%s"' % download}
        if not self.store.exists(name):
            return 200, ctype, "", extra
        return 200, ctype, ("file", self.store.path(name)), extra

    def _check_pin(self, headers):
        """Returns None if the PIN is right, else an error response."""
        now = self.clock()
        if now < self.locked_until:
            return self._json(429, {"error": "Too many wrong PINs. Try again in a minute."})
        if _same(headers.get("x-pin", ""), self.app.cfg.pin):
            self.fails = 0
            return None
        self.fails += 1
        if self.fails >= MAX_FAILS:
            self.fails = 0
            self.locked_until = now + LOCK_S
        return self._json(403, {"error": "Wrong PIN"})

    # ---- routing
    def handle(self, method, path, headers, body):
        path = path.split("?")[0]
        try:
            if method == "GET":
                return self._get(path)
            if method == "POST":
                return self._post(path, headers, body)
            return self._json(405, {"error": "method not allowed"})
        except Exception as e:      # a bad request must never take the server down
            print("api error:", e)
            return self._json(500, {"error": "internal error"})

    def _get(self, path):
        app = self.app
        if path in ("/", "/index.html"):
            return 200, "text/html; charset=utf-8", ("file", self.web_file), {}
        if path == "/api/status":
            return self._json(200, app.status())
        if path == "/api/live":
            return self._json(200, {"points": app.live_points(), "sample_s": SAMPLE_S})
        if path == "/api/settings":
            return self._json(200, {
                "values": app.cfg.public(),
                "defaults": {k: v for k, v in DEFAULTS.items() if k != "pin"},
                "limits": LIMITS,
                "choices": CHOICES,
            })
        if path == "/api/events":
            return self._json(200, {"events": app.recent_events(20)})
        if path == "/api/log.csv":
            return self._file("hourly.csv", "text/csv", "hourly-log.csv")
        if path == "/api/events.csv":
            return self._file("events.csv", "text/csv", "events.csv")
        if path == "/favicon.ico":
            return 204, "image/x-icon", "", {}
        return self._json(404, {"error": "not found"})

    def _post(self, path, headers, body):
        denied = self._check_pin(headers)
        if denied:
            return denied
        try:
            data = json.loads(body) if body else {}
        except ValueError:
            return self._json(400, {"error": "invalid JSON"})
        if not isinstance(data, dict):
            return self._json(400, {"error": "expected a JSON object"})
        app, now = self.app, self.clock()
        if path == "/api/auth":
            return self._json(200, {"ok": True})
        if path == "/api/command":
            cmd = data.get("cmd")
            if not isinstance(cmd, str):
                return self._json(400, {"error": "cmd must be a string"})
            try:
                app.handle_command(cmd, now)
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            return self._json(200, {"ok": True})
        if path == "/api/settings":
            errs = app.update_settings(data)
            if errs:
                return self._json(400, {"errors": errs})
            return self._json(200, {"ok": True})
        if path == "/api/settings/reset":
            app.reset_settings()
            return self._json(200, {"ok": True})
        if path == "/api/filter/reset":
            app.filter_replaced(now)
            return self._json(200, {"ok": True})
        return self._json(404, {"error": "not found"})
