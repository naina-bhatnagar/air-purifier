"""Fixed-size ring buffer. (collections.deque is limited on MicroPython.)"""


class Ring:
    def __init__(self, size):
        self.size = size
        self.buf = [None] * size
        self.n = 0
        self.i = 0

    def append(self, x):
        self.buf[self.i] = x
        self.i = (self.i + 1) % self.size
        if self.n < self.size:
            self.n += 1

    def __len__(self):
        return self.n

    def full(self):
        return self.n == self.size

    def clear(self):
        self.n = 0
        self.i = 0

    def values(self):
        """Oldest first."""
        if self.n < self.size:
            return self.buf[:self.n]
        return self.buf[self.i:] + self.buf[:self.i]

    def mean(self):
        v = self.values()
        return sum(v) / len(v) if v else 0.0
