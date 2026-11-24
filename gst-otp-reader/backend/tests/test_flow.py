import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import *
from app.seed import seed
from conftest import DB_PATH

PW, OTP = "Demo@12345", "482913"

@pytest.fixture(scope="module")
def env():
    from app.db import Base, engine
    Base.metadata.create_all(engine)
    with SessionLocal() as db: ids = seed(db)
    with TestClient(app) as c:
        def login(email):
            return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": email, "password": PW}).json()["access_token"]}
        aud, cli, oth = login("auditor@sharma.test"), login("client@acme.test"), login("auditor@other.test")
        dev = c.post("/api/devices/register", headers=cli, json={"device_uuid": "u1", "device_name": "Raj phone"}).json()["id"]
        assert c.post("/api/devices/pair", headers=cli, json={"device_id": dev, "client_id": ids["client"], "gstin_id": ids["gstin"]}).status_code == 201
        yield dict(c=c, ids=ids, aud=aud, cli={**cli, "X-Device-Id": dev}, cli_nodev=cli, oth=oth, login=login, dev=dev)

def new_session(e):
    r = e["c"].post("/api/otp/sessions", headers=e["aud"], json=dict(client_id=e["ids"]["client"], gstin_id=e["ids"]["gstin"],
                    return_type="GSTR-3B", filing_period="10-2026", purpose="Monthly return filing"))
    assert r.status_code == 201, r.text; return r.json()["id"]

def test_full_flow_and_no_otp_persisted(env):
    c, a, k = env["c"], env["aud"], env["cli"]; sid = new_session(env)
    assert c.get(f"/api/otp/sessions/{sid}", headers=k).json()["status"] == "CLIENT_NOTIFIED"
    # nothing may happen before approval
    assert c.post(f"/api/otp/sessions/{sid}/manual-otp", headers=k, json={"otp": OTP}).status_code == 409
    assert c.post(f"/api/otp/sessions/{sid}/approve", headers=k).json()["status"] == "WAITING_FOR_SMS"
    assert c.post(f"/api/otp/sessions/{sid}/manual-otp", headers=k, json={"otp": OTP, "source": "SMS_CONSENT"}).json()["status"] == "WAITING_FOR_SHARING_APPROVAL"
    assert c.get(f"/api/otp/sessions/{sid}/otp", headers=a).status_code == 409           # not authorized yet
    assert c.post(f"/api/otp/sessions/{sid}/authorize-share", headers=k, json={"confirm": False}).status_code == 400
    assert c.post(f"/api/otp/sessions/{sid}/authorize-share", headers=k, json={"confirm": True}).json()["status"] == "OTP_AUTHORIZED"
    assert c.get(f"/api/otp/sessions/{sid}/otp", headers=env["oth"]).status_code == 404   # other tenant
    r = c.get(f"/api/otp/sessions/{sid}/otp", headers=a); assert r.json() == {"otp": OTP} and r.headers["cache-control"] == "no-store"
    assert c.get(f"/api/otp/sessions/{sid}/otp", headers=a).status_code == 409           # one-time
    assert c.post(f"/api/otp/sessions/{sid}/filing-arn", headers=a, json={"arn": "AA3610261234567"}).status_code == 409
    assert c.post(f"/api/otp/sessions/{sid}/portal-result", headers=a, json={"verified": True}).json()["status"] == "PORTAL_VERIFIED"
    assert c.post(f"/api/otp/sessions/{sid}/filing-arn", headers=a, json={"arn": "AA3610261234567"}).json()["filing_arn"]
    with SessionLocal() as db:  # OTP absent from audit rows and from the database file itself
        assert OTP not in str([x.metadata_json for x in db.scalars(select(AuditLog))])
    assert OTP.encode() not in open(DB_PATH, "rb").read()

def test_reject_and_one_active_session(env):
    c = env["c"]; sid = new_session(env)
    assert c.post("/api/otp/sessions", headers=env["aud"], json=dict(client_id=env["ids"]["client"], gstin_id=env["ids"]["gstin"],
                  return_type="GSTR-1", filing_period="10-2026", purpose="dup")).status_code == 409
    assert c.post(f"/api/otp/sessions/{sid}/reject", headers=env["cli"]).json()["status"] == "REJECTED"
    assert c.get(f"/api/otp/sessions/{sid}/otp", headers=env["aud"]).status_code == 409

def test_unpaired_device_and_wrong_role_blocked(env):
    c = env["c"]; sid = new_session(env)
    assert c.post(f"/api/otp/sessions/{sid}/approve", headers=env["cli_nodev"]).status_code == 403
    assert c.post(f"/api/otp/sessions/{sid}/approve", headers=env["aud"]).status_code == 403
    c.post(f"/api/otp/sessions/{sid}/cancel", headers=env["aud"])

def test_cross_tenant_isolation_and_security_event(env):
    c = env["c"]; sid = new_session(env)
    assert c.get(f"/api/otp/sessions/{sid}", headers=env["oth"]).status_code == 404
    assert c.get("/api/otp/sessions", headers=env["oth"]).json() == []
    assert c.post("/api/otp/sessions", headers=env["oth"], json=dict(client_id=env["ids"]["client"], gstin_id=env["ids"]["gstin"],
                  return_type="GSTR-3B", filing_period="10-2026", purpose="attack")).status_code == 404
    with SessionLocal() as db: assert db.scalar(select(AuditLog).where(AuditLog.event_type == "SECURITY_CROSS_TENANT_ATTEMPT"))
    c.post(f"/api/otp/sessions/{sid}/cancel", headers=env["aud"])

def test_expiry(env):
    c = env["c"]; sid = new_session(env)
    with SessionLocal() as db:
        s = db.get(OtpSession, sid); s.expires_at = now() - timedelta(seconds=1); db.commit()
    assert c.get(f"/api/otp/sessions/{sid}/status", headers=env["aud"]).json()["status"] == "EXPIRED"
    assert c.post(f"/api/otp/sessions/{sid}/approve", headers=env["cli"]).status_code == 409

def test_logout_and_device_revocation(env):
    c = env["c"]; h = env["login"]("auditor@sharma.test")
    assert c.get("/api/otp/sessions", headers=h).status_code == 200
    c.post("/api/auth/logout", headers=h); assert c.get("/api/otp/sessions", headers=h).status_code == 401
    admin = env["login"]("admin@sharma.test")
    assert c.post(f"/api/devices/{env['dev']}/revoke", headers=admin).status_code == 200
    sid = new_session(env)
    assert c.post(f"/api/otp/sessions/{sid}/approve", headers=env["cli"]).status_code == 403

def test_refresh_rotation_and_reuse_detection(env):
    c = env["c"]; r = c.post("/api/auth/login", json={"email": "admin@sharma.test", "password": PW}).json()
    r2 = c.post("/api/auth/refresh", json={"refresh_token": r["refresh_token"]}).json()
    assert c.post("/api/auth/refresh", json={"refresh_token": r["refresh_token"]}).status_code == 401   # reuse
    assert c.post("/api/auth/refresh", json={"refresh_token": r2["refresh_token"]}).status_code == 401   # session killed

def test_websocket_requires_auth_and_is_status_only(env):
    c = env["c"]
    with pytest.raises(Exception):
        with c.websocket_connect(f"/api/otp/ws/{env['dev']}") as ws:
            ws.send_json({"token": "bad"}); ws.receive_json()
