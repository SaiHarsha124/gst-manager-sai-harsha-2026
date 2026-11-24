import asyncio, secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Literal
import anyio, jwt
from fastapi import FastAPI, Depends, Header, HTTPException, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import config
from .db import Base, engine, get_db, SessionLocal
from .models import *
from .security import hash_password, verify_password, hash_token, make_access, decode_access
from .otp_store import otp_store
from .hub import hub
from .ratelimit import limiter

ADMIN, AUDITOR, CLIENT = "ADMIN", "AUDITOR", "CLIENT"
ALLOWED = {  # authoritative workflow state machine (spec section 11)
    "REQUESTED": {"CLIENT_NOTIFIED", "CLIENT_APPROVED", "REJECTED", "EXPIRED", "CANCELLED"},
    "CLIENT_NOTIFIED": {"CLIENT_APPROVED", "REJECTED", "EXPIRED", "CANCELLED"},
    "CLIENT_APPROVED": {"WAITING_FOR_SMS", "EXPIRED", "CANCELLED"},
    "WAITING_FOR_SMS": {"OTP_DETECTED", "WAITING_FOR_SHARING_APPROVAL", "EXPIRED", "CANCELLED", "FAILED"},
    "OTP_DETECTED": {"WAITING_FOR_SHARING_APPROVAL", "EXPIRED", "CANCELLED"},
    "WAITING_FOR_SHARING_APPROVAL": {"OTP_AUTHORIZED", "WAITING_FOR_SMS", "EXPIRED", "CANCELLED"},
    "OTP_AUTHORIZED": {"OTP_DELIVERED", "EXPIRED", "CANCELLED", "FAILED"},
    "OTP_DELIVERED": {"PORTAL_VERIFIED", "FAILED"},
}
TERMINAL = {"PORTAL_VERIFIED", "REJECTED", "EXPIRED", "FAILED", "CANCELLED"}
PRE_DELIVERY = set(ALLOWED) - {"OTP_DELIVERED"}
BANNED_META = {"otp", "sms", "sms_body", "message", "code"}

def expire_due(db: Session):
    out = []
    for s in db.scalars(select(OtpSession).where(OtpSession.status.in_(PRE_DELIVERY), OtpSession.expires_at <= now())):
        set_status(db, s, "EXPIRED", None, "OTP_EXPIRED"); out.append(s)
    return out

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    async def loop():
        while True:
            await asyncio.sleep(5)
            def work():
                with SessionLocal() as db: return [(s, ids(db, s)) for s in expire_due(db)]
            for s, targets in await anyio.to_thread.run_sync(work):
                await hub.emit(targets, ev(s, "OTP_EXPIRED"))
    t = asyncio.create_task(loop())
    yield
    t.cancel()

app = FastAPI(title="GST OTP Reader", lifespan=lifespan)

# ---------- helpers ----------
def audit(db, org_id, session_id, actor, event_type, meta=None):
    meta = meta or {}
    assert not (BANNED_META & {k.lower() for k in meta}), "secrets must never enter audit metadata"
    db.add(AuditLog(organization_id=org_id, session_id=session_id, actor_user_id=actor, event_type=event_type, metadata_json=meta))

def set_status(db, s, new, actor, event, meta=None):
    if new not in ALLOWED.get(s.status, set()):
        raise HTTPException(409, f"Illegal transition {s.status} -> {new}")
    meta = {**(meta or {}), "from": s.status, "to": new}
    s.status, s.updated_at = new, now()
    if new in TERMINAL or new == "OTP_DELIVERED": otp_store.clear(s.id)
    audit(db, s.organization_id, s.id, actor, event, meta); db.commit()

def ev(s, event): return {"event": event, "session_id": s.id, "status": s.status, "ts": now().isoformat()}

def ids(db, s, which=("auditor", "client")):
    out = set()
    if "auditor" in which: out |= {s.requested_by, s.assigned_auditor_id}
    if "client" in which:
        out |= set(db.scalars(select(Device.user_id).join(DevicePairing, DevicePairing.device_id == Device.id).where(
            DevicePairing.client_id == s.client_id, DevicePairing.gstin_id == s.gstin_id,
            DevicePairing.status == "ACTIVE", Device.revoked_at.is_(None))))
    return out

def emit(db, s, event, which=("auditor", "client")) -> int:
    try: return anyio.from_thread.run(hub.emit, ids(db, s, which), ev(s, event))
    except Exception: return 0

def view(s):
    d = {c: getattr(s, c) for c in ("id", "client_id", "gstin_id", "requested_by", "assigned_auditor_id", "return_type",
                                     "filing_period", "purpose", "status", "filing_arn")}
    d.update(expires_at=s.expires_at.isoformat(), created_at=s.created_at.isoformat()); return d

class Principal:
    def __init__(self, user, sid): self.user, self.sid = user, sid

def auth(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> Principal:
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401, "Missing token")
    try: p = decode_access(authorization[7:])
    except jwt.PyJWTError: raise HTTPException(401, "Invalid token")
    a, u = db.get(AuthSession, p["sid"]), db.get(User, p["sub"])
    if not a or a.revoked_at or not u or u.status != "ACTIVE": raise HTTPException(401, "Session revoked")
    return Principal(u, a.id)

def need(user, *roles):
    if user.role not in roles: raise HTTPException(403, "Forbidden for role")

def load(db, user, sid) -> OtpSession:
    s = db.scalar(select(OtpSession).where(OtpSession.id == sid, OtpSession.organization_id == user.organization_id))
    ok = s and (user.role == ADMIN or (user.role == AUDITOR and user.id in (s.requested_by, s.assigned_auditor_id))
                or (user.role == CLIENT and user.client_id == s.client_id))
    if not ok:
        if s is None and db.get(OtpSession, sid):  # exists in another tenant: log, disclose nothing
            audit(db, user.organization_id, None, user.id, "SECURITY_CROSS_TENANT_ATTEMPT"); db.commit()
        raise HTTPException(404, "Session not found")
    if s.status in PRE_DELIVERY and s.expires_at <= now():
        set_status(db, s, "EXPIRED", None, "OTP_EXPIRED"); emit(db, s, "OTP_EXPIRED")
    return s

def client_device(db, user, s, device_id):
    if user.role != CLIENT or user.client_id != s.client_id: raise HTTPException(403, "Not your client")
    d = device_id and db.scalar(select(Device).where(Device.id == device_id, Device.user_id == user.id, Device.revoked_at.is_(None)))
    p = d and db.scalar(select(DevicePairing).where(DevicePairing.device_id == d.id, DevicePairing.client_id == s.client_id,
                        DevicePairing.gstin_id == s.gstin_id, DevicePairing.status == "ACTIVE"))
    if not p: raise HTTPException(403, "Device not paired for this GSTIN (X-Device-Id)")
    return d

# ---------- auth ----------
class LoginIn(BaseModel): email: EmailStr; password: str
class RefreshIn(BaseModel): refresh_token: str

def issue(db, user, device_id=None):
    secret = secrets.token_urlsafe(32)
    a = AuthSession(user_id=user.id, device_id=device_id, refresh_hash=hash_token(secret), expires_at=now() + timedelta(seconds=config.REFRESH_TTL))
    db.add(a); db.commit()
    return {"access_token": make_access(user.id, a.id), "refresh_token": f"{a.id}.{secret}", "token_type": "bearer", "role": user.role}

@app.post("/api/auth/login")
def login(b: LoginIn, db: Session = Depends(get_db)):
    limiter.check(f"login:{b.email.lower()}", 10, 60)
    u = db.scalar(select(User).where(User.email == b.email.lower()))
    if not u or u.status != "ACTIVE" or not verify_password(b.password, u.password_hash): raise HTTPException(401, "Bad credentials")
    audit(db, u.organization_id, None, u.id, "LOGIN"); return issue(db, u)

@app.post("/api/auth/refresh")
def refresh(b: RefreshIn, db: Session = Depends(get_db)):
    sid, _, secret = b.refresh_token.partition(".")
    a = db.get(AuthSession, sid)
    if not a or a.expires_at <= now() or a.revoked_at: raise HTTPException(401, "Invalid refresh token")
    if a.refresh_hash != hash_token(secret):  # reuse of a rotated token: kill the session
        a.revoked_at = now(); db.commit(); raise HTTPException(401, "Refresh token reuse detected")
    new = secrets.token_urlsafe(32); a.refresh_hash = hash_token(new); db.commit()  # rotation
    return {"access_token": make_access(a.user_id, a.id), "refresh_token": f"{a.id}.{new}", "token_type": "bearer"}

@app.post("/api/auth/logout")
def logout(p: Principal = Depends(auth), db: Session = Depends(get_db)):
    db.get(AuthSession, p.sid).revoked_at = now(); db.commit(); return {"ok": True}

# ---------- devices ----------
class DeviceIn(BaseModel): device_uuid: str; platform: str = "android"; device_name: str
class PairIn(BaseModel): device_id: str; client_id: str; gstin_id: str

@app.post("/api/devices/register", status_code=201)
def register_device(b: DeviceIn, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    d = db.scalar(select(Device).where(Device.user_id == p.user.id, Device.device_uuid == b.device_uuid, Device.revoked_at.is_(None)))
    if not d:
        d = Device(organization_id=p.user.organization_id, user_id=p.user.id, **b.model_dump()); db.add(d)
        audit(db, d.organization_id, None, p.user.id, "DEVICE_REGISTERED", {"device_name": b.device_name}); db.commit()
    return {"id": d.id}

@app.get("/api/devices")
def list_devices(p: Principal = Depends(auth), db: Session = Depends(get_db)):
    q = select(Device).where(Device.organization_id == p.user.organization_id)
    if p.user.role != ADMIN: q = q.where(Device.user_id == p.user.id)
    return [{"id": d.id, "user_id": d.user_id, "device_name": d.device_name, "platform": d.platform, "paired_at": d.paired_at,
             "revoked_at": d.revoked_at, "last_seen_at": d.last_seen_at} for d in db.scalars(q)]

@app.post("/api/devices/pair", status_code=201)
def pair(b: PairIn, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    u = p.user; need(u, ADMIN, CLIENT)
    d = db.scalar(select(Device).where(Device.id == b.device_id, Device.organization_id == u.organization_id, Device.revoked_at.is_(None)))
    g = db.scalar(select(ClientGstin).where(ClientGstin.id == b.gstin_id, ClientGstin.client_id == b.client_id,
                  ClientGstin.organization_id == u.organization_id, ClientGstin.status == "ACTIVE"))
    owner = d and db.get(User, d.user_id)
    if not d or not g or owner.role != CLIENT or owner.client_id != b.client_id: raise HTTPException(404, "Device/client/GSTIN mismatch")
    if u.role == CLIENT and d.user_id != u.id: raise HTTPException(403, "Pair your own device only")
    db.add(DevicePairing(organization_id=u.organization_id, client_id=b.client_id, gstin_id=b.gstin_id, device_id=d.id, approved_by=u.id))
    d.paired_at = now(); audit(db, u.organization_id, None, u.id, "DEVICE_PAIRED", {"device_id": d.id}); db.commit()
    return {"ok": True}

@app.post("/api/devices/{device_id}/revoke")
def revoke(device_id: str, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    u = p.user
    d = db.scalar(select(Device).where(Device.id == device_id, Device.organization_id == u.organization_id))
    if not d or (u.role != ADMIN and d.user_id != u.id): raise HTTPException(404, "Device not found")
    d.revoked_at = now()
    for x in db.scalars(select(DevicePairing).where(DevicePairing.device_id == d.id)): x.status = "REVOKED"
    for a in db.scalars(select(AuthSession).where(AuthSession.device_id == d.id, AuthSession.revoked_at.is_(None))): a.revoked_at = now()
    audit(db, u.organization_id, None, u.id, "DEVICE_REVOKED", {"device_id": d.id}); db.commit()
    try: anyio.from_thread.run(hub.drop, d.id)
    except Exception: pass
    return {"ok": True}

# ---------- OTP sessions ----------
class SessionIn(BaseModel):
    client_id: str; gstin_id: str; return_type: str; filing_period: str; purpose: str = Field(min_length=3, max_length=300)
    assigned_auditor_id: str | None = None
class OtpIn(BaseModel): otp: str = Field(pattern=r"^\d{4,8}$"); source: Literal["MANUAL", "SMS_CONSENT"] = "MANUAL"
class ShareIn(BaseModel): confirm: bool
class PortalIn(BaseModel): verified: bool; reason: str | None = Field(None, max_length=200)
class ArnIn(BaseModel): arn: str = Field(min_length=5, max_length=40)

@app.post("/api/otp/sessions", status_code=201)
def create_session(b: SessionIn, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    u = p.user; need(u, AUDITOR); limiter.check(f"create:{u.id}", 10, 60)
    org = u.organization_id
    c = db.scalar(select(Client).where(Client.id == b.client_id, Client.organization_id == org, Client.status == "ACTIVE"))
    g = db.scalar(select(ClientGstin).where(ClientGstin.id == b.gstin_id, ClientGstin.client_id == b.client_id,
                  ClientGstin.organization_id == org, ClientGstin.status == "ACTIVE"))
    if not c or not g: raise HTTPException(404, "Client/GSTIN not found")
    aud = b.assigned_auditor_id or u.id
    a = db.scalar(select(User).where(User.id == aud, User.organization_id == org, User.role == AUDITOR, User.status == "ACTIVE"))
    if not a: raise HTTPException(404, "Auditor not found")
    if db.scalar(select(OtpSession.id).where(OtpSession.gstin_id == g.id, OtpSession.status.notin_(TERMINAL))):
        raise HTTPException(409, "An active OTP session already exists for this GSTIN")
    s = OtpSession(organization_id=org, client_id=c.id, gstin_id=g.id, requested_by=u.id, assigned_auditor_id=a.id, return_type=b.return_type,
                   filing_period=b.filing_period, purpose=b.purpose, expires_at=now() + timedelta(seconds=config.SESSION_TTL))
    db.add(s); db.flush(); audit(db, org, s.id, u.id, "OTP_REQUESTED", {"return_type": b.return_type, "period": b.filing_period}); db.commit()
    emit(db, s, "OTP_REQUESTED", ("auditor",))
    if emit(db, s, "OTP_REQUEST_RECEIVED", ("client",)):  # only mark notified once delivery is confirmed
        set_status(db, s, "CLIENT_NOTIFIED", None, "CLIENT_NOTIFIED")
    return view(s)

def mark_notified(db, s, user):
    if user.role == CLIENT and s.status == "REQUESTED": set_status(db, s, "CLIENT_NOTIFIED", user.id, "CLIENT_NOTIFIED", {"via": "pull"})

@app.get("/api/otp/sessions")
def list_sessions(p: Principal = Depends(auth), db: Session = Depends(get_db)):
    u = p.user; expire_due(db)
    q = select(OtpSession).where(OtpSession.organization_id == u.organization_id).order_by(OtpSession.created_at.desc()).limit(100)
    if u.role == AUDITOR: q = q.where((OtpSession.requested_by == u.id) | (OtpSession.assigned_auditor_id == u.id))
    if u.role == CLIENT: q = q.where(OtpSession.client_id == u.client_id)
    out = list(db.scalars(q))
    for s in out: mark_notified(db, s, u)
    return [view(s) for s in out]

@app.get("/api/otp/sessions/{sid}")
def get_session(sid: str, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    s = load(db, p.user, sid); mark_notified(db, s, p.user); return view(s)

@app.get("/api/otp/sessions/{sid}/status")
def get_status(sid: str, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    s = load(db, p.user, sid); return {"status": s.status, "expires_at": s.expires_at.isoformat()}

@app.post("/api/otp/sessions/{sid}/approve")
def approve(sid: str, p: Principal = Depends(auth), db: Session = Depends(get_db), x_device_id: str | None = Header(None)):
    s = load(db, p.user, sid); client_device(db, p.user, s, x_device_id)
    set_status(db, s, "CLIENT_APPROVED", p.user.id, "CLIENT_APPROVED", {"device_id": x_device_id})
    set_status(db, s, "WAITING_FOR_SMS", p.user.id, "SMS_LISTENING_STARTED")  # app may now start consent-based listening
    emit(db, s, "CLIENT_APPROVED"); return view(s)

@app.post("/api/otp/sessions/{sid}/reject")
def reject(sid: str, p: Principal = Depends(auth), db: Session = Depends(get_db), x_device_id: str | None = Header(None)):
    s = load(db, p.user, sid); client_device(db, p.user, s, x_device_id)
    set_status(db, s, "REJECTED", p.user.id, "CLIENT_REJECTED"); emit(db, s, "CLIENT_REJECTED"); return view(s)

@app.post("/api/otp/sessions/{sid}/manual-otp")
def submit_otp(sid: str, b: OtpIn, p: Principal = Depends(auth), db: Session = Depends(get_db), x_device_id: str | None = Header(None)):
    """Used for manual entry AND for an SMS-consent-detected code the client confirmed. Held in memory only."""
    s = load(db, p.user, sid); client_device(db, p.user, s, x_device_id)
    if s.status not in ("WAITING_FOR_SMS", "WAITING_FOR_SHARING_APPROVAL"): raise HTTPException(409, f"Not accepting OTP in {s.status}")
    if s.status == "WAITING_FOR_SHARING_APPROVAL": set_status(db, s, "WAITING_FOR_SMS", p.user.id, "OTP_REENTERED")
    if b.source == "SMS_CONSENT":
        set_status(db, s, "OTP_DETECTED", p.user.id, "OTP_DETECTED"); emit(db, s, "OTP_DETECTED")
    otp_store.put(s.id, b.otp, s.assigned_auditor_id, (s.expires_at - now()).total_seconds())
    set_status(db, s, "WAITING_FOR_SHARING_APPROVAL", p.user.id, "OTP_CAPTURED", {"source": b.source}); return view(s)

@app.post("/api/otp/sessions/{sid}/authorize-share")
def authorize(sid: str, b: ShareIn, p: Principal = Depends(auth), db: Session = Depends(get_db), x_device_id: str | None = Header(None)):
    s = load(db, p.user, sid); client_device(db, p.user, s, x_device_id)
    if not b.confirm: raise HTTPException(400, "Explicit confirmation required")
    if not otp_store.has(s.id): raise HTTPException(409, "No OTP held for this session")
    set_status(db, s, "OTP_AUTHORIZED", p.user.id, "OTP_SHARING_APPROVED", {"auditor_id": s.assigned_auditor_id})
    emit(db, s, "OTP_SHARING_APPROVED"); return view(s)

@app.get("/api/otp/sessions/{sid}/otp")
def fetch_otp(sid: str, response: Response, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    """One-time delivery: only the assigned auditor, only after authorization, only once."""
    s = load(db, p.user, sid)
    if p.user.id != s.assigned_auditor_id: raise HTTPException(403, "Not the assigned auditor")
    if s.status != "OTP_AUTHORIZED": raise HTTPException(409, f"OTP not available in {s.status}")
    otp = otp_store.pop(s.id, p.user.id)
    if otp is None: raise HTTPException(410, "OTP expired or already delivered")
    set_status(db, s, "OTP_DELIVERED", p.user.id, "OTP_DELIVERED"); emit(db, s, "OTP_DELIVERED")
    response.headers["Cache-Control"] = "no-store"; return {"otp": otp}

@app.post("/api/otp/sessions/{sid}/portal-result")
def portal_result(sid: str, b: PortalIn, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    s = load(db, p.user, sid)
    if p.user.id != s.assigned_auditor_id: raise HTTPException(403, "Not the assigned auditor")
    set_status(db, s, "PORTAL_VERIFIED" if b.verified else "FAILED", p.user.id, "PORTAL_VERIFIED" if b.verified else "PORTAL_REJECTED_OTP",
               {"reason": b.reason} if b.reason else None)
    emit(db, s, "PORTAL_VERIFIED" if b.verified else "SESSION_FAILED"); return view(s)

@app.post("/api/otp/sessions/{sid}/filing-arn")
def record_arn(sid: str, b: ArnIn, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    """Filing completion is separate from OTP verification and needs the portal's ARN."""
    s = load(db, p.user, sid)
    if p.user.id != s.assigned_auditor_id: raise HTTPException(403, "Not the assigned auditor")
    if s.status != "PORTAL_VERIFIED": raise HTTPException(409, "Portal verification not recorded")
    s.filing_arn = b.arn; audit(db, s.organization_id, s.id, p.user.id, "FILING_ARN_RECORDED"); db.commit(); return view(s)

@app.post("/api/otp/sessions/{sid}/cancel")
def cancel(sid: str, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    s = load(db, p.user, sid)
    if s.status in TERMINAL: raise HTTPException(409, "Already finished")
    set_status(db, s, "CANCELLED", p.user.id, "SESSION_CANCELLED"); emit(db, s, "SESSION_CANCELLED"); return view(s)

# ---------- admin ----------
class UserIn(BaseModel): name: str; email: EmailStr; password: str = Field(min_length=10); role: Literal["ADMIN", "AUDITOR", "CLIENT"]; client_id: str | None = None
class ClientIn(BaseModel): client_name: str; contact: str | None = None
class GstinIn(BaseModel): gstin: str = Field(pattern=r"^\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d][A-Z\d]$"); registered_mobile_label: str | None = None

@app.post("/api/admin/users", status_code=201)
def add_user(b: UserIn, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    need(p.user, ADMIN)
    if b.role == CLIENT and not db.scalar(select(Client.id).where(Client.id == b.client_id, Client.organization_id == p.user.organization_id)):
        raise HTTPException(404, "client_id required for CLIENT users")
    u = User(organization_id=p.user.organization_id, name=b.name, email=b.email.lower(), role=b.role,
             client_id=b.client_id if b.role == CLIENT else None, password_hash=hash_password(b.password))
    db.add(u); db.flush(); audit(db, u.organization_id, None, p.user.id, "USER_CREATED", {"user_id": u.id, "role": b.role}); db.commit(); return {"id": u.id}

@app.post("/api/admin/clients", status_code=201)
def add_client(b: ClientIn, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    need(p.user, ADMIN); c = Client(organization_id=p.user.organization_id, **b.model_dump()); db.add(c); db.commit(); return {"id": c.id}

@app.post("/api/admin/clients/{cid}/gstins", status_code=201)
def add_gstin(cid: str, b: GstinIn, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    need(p.user, ADMIN)
    if not db.scalar(select(Client.id).where(Client.id == cid, Client.organization_id == p.user.organization_id)): raise HTTPException(404, "Client not found")
    g = ClientGstin(organization_id=p.user.organization_id, client_id=cid, **b.model_dump()); db.add(g); db.commit(); return {"id": g.id}

@app.get("/api/admin/audit")
def audit_history(session_id: str | None = None, p: Principal = Depends(auth), db: Session = Depends(get_db)):
    need(p.user, ADMIN)
    q = select(AuditLog).where(AuditLog.organization_id == p.user.organization_id).order_by(AuditLog.created_at.desc()).limit(500)
    if session_id: q = q.where(AuditLog.session_id == session_id)
    return [{"id": a.id, "session_id": a.session_id, "actor_user_id": a.actor_user_id, "event_type": a.event_type,
             "metadata": a.metadata_json, "created_at": a.created_at.isoformat()} for a in db.scalars(q)]

# ---------- websocket (token sent as first message, never in the URL) ----------
@app.websocket("/api/otp/ws/{device_id}")
async def ws_endpoint(ws: WebSocket, device_id: str):
    await ws.accept()
    def check(token):
        with SessionLocal() as db:
            try: pl = decode_access(token)
            except jwt.PyJWTError: return None
            a = db.get(AuthSession, pl["sid"])
            d = db.scalar(select(Device).where(Device.id == device_id, Device.user_id == pl["sub"], Device.revoked_at.is_(None)))
            if not a or a.revoked_at or not d: return None
            d.last_seen_at = now(); db.commit(); return pl["sub"]
    try:
        msg = await asyncio.wait_for(ws.receive_json(), 10)
        uid_ = await anyio.to_thread.run_sync(check, msg.get("token", ""))
    except Exception:
        uid_ = None
    if not uid_: await ws.close(code=4401); return
    hub.add(device_id, uid_, ws); await ws.send_json({"event": "CONNECTED"})
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: pass
    finally: hub.remove(device_id)
