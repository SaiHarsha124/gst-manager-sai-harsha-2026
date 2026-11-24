import time, collections, threading
from fastapi import HTTPException

class Limiter:
    def __init__(self): self.h, self.l = collections.defaultdict(collections.deque), threading.Lock()
    def check(self, key: str, n: int, per: int):
        t = time.monotonic()
        with self.l:
            q = self.h[key]
            while q and q[0] < t - per: q.popleft()
            if len(q) >= n: raise HTTPException(429, "Too many requests")
            q.append(t)

limiter = Limiter()
