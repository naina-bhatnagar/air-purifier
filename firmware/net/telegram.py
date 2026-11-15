"""Minimal Telegram support: a message queue, a command reply, and an async client.

Every network call has a timeout and runs as its own task, so the control loop never waits.
"""
import asyncio
import json

API_HOST = "api.telegram.org"
POLL_S = 10
RETRY_S = 30


class Notifier:
    """notify(text) just queues. The Telegram task sends when WiFi is available."""

    def __init__(self, max_queue=8):
        self.outbox = []
        self.max_queue = max_queue
        self.base_url = None        # set once WiFi gives us an address

    def __call__(self, text):
        self.outbox.append(text)
        if len(self.outbox) > self.max_queue:
            self.outbox.pop(0)

    def with_link(self, text):
        return text + ("\nDashboard: " + self.base_url if self.base_url else "")


def status_text(st):
    b = st.get("before")
    if b is None:
        return "No sensor reading right now."
    fan = "off" if st["speed"] == 0 else "on, speed %d" % st["speed"]
    return "AQI %d (%s). PM2.5 %.0f, 1-min average %.0f ug/m3. Purifier %s (%s)." % (
        st["aqi"], st["band"], b["pm25"], b["pm25_avg"], fan, st["mode"].lower())


def reply_for(text, status, link):
    """Any message mentioning AQI gets the numbers. Everything else gets the link."""
    if "aqi" in text.lower():
        return status + ("\nDashboard: " + link if link else "")
    return "Live readings, charts and controls: " + (link or "open the dashboard on your home WiFi")


def parse_updates(resp, allowed_chat):
    """Returns (texts from the allowed chat only, next offset or None)."""
    texts = []
    nxt = None
    updates = resp.get("result", []) if resp.get("ok") else []
    for u in updates:
        uid = u.get("update_id")
        if uid is not None and (nxt is None or uid + 1 > nxt):
            nxt = uid + 1
        m = u.get("message") or {}
        chat = (m.get("chat") or {}).get("id")
        if str(chat) == str(allowed_chat) and m.get("text"):
            texts.append(m["text"])
    return texts, nxt


async def https_post(host, path, obj, timeout=10):
    body = json.dumps(obj).encode()
    head = ("POST %s HTTP/1.0\r\nHost: %s\r\nContent-Type: application/json\r\n"
            "Content-Length: %d\r\nConnection: close\r\n\r\n" % (path, host, len(body))).encode()

    async def go():
        reader, writer = await asyncio.open_connection(host, 443, ssl=True)
        try:
            writer.write(head + body)
            await writer.drain()
            data = b""
            while len(data) < 16384:
                chunk = await reader.read(1024)
                if not chunk:
                    break
                data += chunk
            return data
        finally:
            writer.close()

    raw = await asyncio.wait_for(go(), timeout)
    return json.loads(raw.partition(b"\r\n\r\n")[2])


class Telegram:
    def __init__(self, token, chat_id, notifier, get_status, post=https_post):
        """get_status(): the dict from App.status()."""
        self.token, self.chat_id, self.notifier = token, chat_id, notifier
        self.get_status, self.post = get_status, post
        self.offset = None

    async def _send(self, text):
        await self.post(API_HOST, "/bot%s/sendMessage" % self.token,
                        {"chat_id": self.chat_id, "text": text})

    async def tick(self):
        """One round: send queued alerts, then answer any new messages."""
        while self.notifier.outbox:
            await self._send(self.notifier.with_link(self.notifier.outbox[0]))
            self.notifier.outbox.pop(0)
        req = {"timeout": 0}
        if self.offset is not None:
            req["offset"] = self.offset
        resp = await self.post(API_HOST, "/bot%s/getUpdates" % self.token, req)
        texts, nxt = parse_updates(resp, self.chat_id)
        if nxt is not None:
            self.offset = nxt
        for text in texts:
            reply = reply_for(text, status_text(self.get_status()), self.notifier.base_url)
            await self._send(reply)

    async def run(self):
        while True:
            try:
                await self.tick()
                delay = POLL_S
            except Exception as e:
                print("telegram error:", e)
                delay = RETRY_S
            await asyncio.sleep(delay)
