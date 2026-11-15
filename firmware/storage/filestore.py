"""Small, flash-friendly file storage using only open/os (works on MicroPython and CPython)."""
import json
import os

from core.ring import Ring

TRIM_SLACK = 50     # let a log grow this far past its limit before trimming


def _exists(p):
    try:
        os.stat(p)
        return True
    except OSError:
        return False


class FileStore:
    def __init__(self, root):
        self.root = root.rstrip("/")
        self.corrupt = []       # names of files that existed but could not be read
        self._counts = {}
        if not _exists(self.root):
            try:
                os.mkdir(self.root)
            except OSError:
                pass

    def path(self, name):
        return self.root + "/" + name

    def exists(self, name):
        return _exists(self.path(name))

    # ---- JSON files (settings, state)
    def load_json(self, name):
        p = self.path(name)
        if not _exists(p) and _exists(p + ".tmp"):
            os.rename(p + ".tmp", p)            # finish an interrupted save
        if not _exists(p):
            return None
        try:
            with open(p) as f:
                return json.load(f)
        except (ValueError, OSError):
            if name not in self.corrupt:
                self.corrupt.append(name)
            return None

    def save_json(self, name, obj):
        p = self.path(name)
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(obj, f)
        if _exists(p):
            os.remove(p)
        os.rename(tmp, p)

    # ---- line logs (hourly readings, events)
    def _count(self, name, header):
        if name in self._counts:
            return self._counts[name]
        p = self.path(name)
        n = 0
        if _exists(p):
            with open(p) as f:
                for _ in f:
                    n += 1
            if header and n:
                n -= 1
        self._counts[name] = n
        return n

    def append_line(self, name, line, max_rows=None, header=None):
        p = self.path(name)
        n = self._count(name, header)
        is_new = not _exists(p)
        with open(p, "a") as f:
            if is_new and header:
                f.write(header + "\n")
            f.write(line + "\n")
        self._counts[name] = n + 1
        if max_rows and n + 1 > max_rows + TRIM_SLACK:
            self._trim(name, max_rows, header)

    def _trim(self, name, keep, header):
        """Streams the file so the whole log never has to fit in RAM."""
        p = self.path(name)
        tmp = p + ".tmp"
        skip = self._counts[name] - keep
        offset = 1 if header else 0
        with open(p) as src, open(tmp, "w") as dst:
            i = 0
            for line in src:
                if (header and i == 0) or i - offset >= skip:
                    dst.write(line)
                i += 1
        os.remove(p)
        os.rename(tmp, p)
        self._counts[name] = keep

    def tail(self, name, n, skip_header=True):
        p = self.path(name)
        if not _exists(p):
            return []
        ring = Ring(n)
        first = skip_header
        with open(p) as f:
            for line in f:
                if first:
                    first = False
                    continue
                ring.append(line.strip())
        return ring.values()
