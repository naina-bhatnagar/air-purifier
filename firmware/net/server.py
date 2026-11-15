"""Tiny asyncio HTTP server. Works on CPython and MicroPython (uasyncio)."""
import asyncio
import os

MAX_BODY = 2048
CHUNK = 512
READ_TIMEOUT_S = 5

STATUS = {200: "OK", 204: "No Content", 400: "Bad Request", 403: "Forbidden", 404: "Not Found",
          405: "Method Not Allowed", 413: "Payload Too Large", 429: "Too Many Requests",
          500: "Internal Server Error"}


def parse_request_line(line):
    parts = line.strip().split(" ")
    if len(parts) < 2:
        return None
    return parts[0].upper(), parts[1]


def build_head(code, ctype, length=None, extra=None):
    lines = ["HTTP/1.0 %d %s" % (code, STATUS.get(code, "")), "Content-Type: " + ctype,
             "Connection: close", "Cache-Control: no-store"]
    if length is not None:
        lines.append("Content-Length: %d" % length)
    for k, v in (extra or {}).items():
        lines.append("%s: %s" % (k, v))
    return ("\r\n".join(lines) + "\r\n\r\n").encode()


async def _read_request(reader):
    line = await reader.readline()
    if not line:
        return None
    first = parse_request_line(line.decode())
    if first is None:
        return None
    headers = {}
    for _ in range(24):
        h = await reader.readline()
        if h in (b"\r\n", b"\n", b""):
            break
        k, _, v = h.decode().partition(":")
        headers[k.strip().lower()] = v.strip()
    try:
        n = int(headers.get("content-length", "0") or 0)
    except ValueError:
        return None
    if n > MAX_BODY:
        return "toobig"
    body = (await reader.readexactly(n)).decode() if n else ""
    return first[0], first[1], headers, body


async def _send_file(writer, path, ctype, extra):
    size = os.stat(path)[6]
    writer.write(build_head(200, ctype, size, extra))
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()


async def _handle(api, reader, writer):
    try:
        req = await asyncio.wait_for(_read_request(reader), READ_TIMEOUT_S)
        if req is None:
            return
        if req == "toobig":
            writer.write(build_head(413, "text/plain", 0))
        else:
            code, ctype, payload, extra = api.handle(*req)
            if isinstance(payload, tuple):
                await _send_file(writer, payload[1], ctype, extra)
            else:
                data = payload.encode()
                writer.write(build_head(code, ctype, len(data), extra) + data)
        await writer.drain()
    except Exception as e:
        print("http error:", e)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def serve(api, host="0.0.0.0", port=80, max_conn=4):
    """Starts the server and returns it. Extra simultaneous connections are dropped
    so a flood cannot use up the ESP32's memory."""
    active = [0]

    async def on_conn(reader, writer):
        if active[0] >= max_conn:
            writer.close()
            return
        active[0] += 1
        try:
            await _handle(api, reader, writer)
        finally:
            active[0] -= 1

    return await asyncio.start_server(on_conn, host, port)
