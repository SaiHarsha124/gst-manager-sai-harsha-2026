"""Transient, in-memory-only OTP relay. Never persisted, never logged, never in events.
Single-process by design; for multiple workers use a sticky/in-memory service, NOT a database."""
import threading, time

class OtpStore:
    def __init__(self): self._d, self._l = {}, threading.Lock()
    def put(self, sid: str, otp: str, auditor_id: str, ttl: float):
        with self._l: self._d[sid] = (otp, auditor_id, time.monotonic() + ttl)
    def has(self, sid: str) -> bool:
        with self._l: v = self._d.get(sid); return bool(v and v[2] > time.monotonic())
    def pop(self, sid: str, auditor_id: str):  # one-time, bound to one auditor
        with self._l:
            v = self._d.get(sid)
            if not v or v[1] != auditor_id: return None
            del self._d[sid]
            return v[0] if v[2] > time.monotonic() else None
    def clear(self, sid: str):
        with self._l: self._d.pop(sid, None)

otp_store = OtpStore()
