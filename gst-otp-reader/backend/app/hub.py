"""WebSocket hub. Payloads are status-only; an OTP is never passed through here."""
class Hub:
    def __init__(self): self.conns = {}  # device_id -> (user_id, websocket)
    def add(self, did, uid, ws): self.conns[did] = (uid, ws)
    def remove(self, did): self.conns.pop(did, None)
    async def emit(self, user_ids, payload) -> int:
        n = 0
        for did, (uid, ws) in list(self.conns.items()):
            if uid in user_ids:
                try: await ws.send_json(payload); n += 1
                except Exception: self.conns.pop(did, None)
        return n
    async def drop(self, did):
        c = self.conns.pop(did, None)
        if c:
            try: await c[1].close(code=4403)
            except Exception: pass

hub = Hub()
