"""Data model from spec section 8. There is deliberately NO otp_value column anywhere."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, JSON, event
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def uid() -> str: return uuid.uuid4().hex
def now() -> datetime: return datetime.now(timezone.utc).replace(tzinfo=None)

def pk(): return mapped_column(String(32), primary_key=True, default=uid)
def fk(t, null=False): return mapped_column(String(32), ForeignKey(f"{t}.id"), nullable=null, index=True)
def ts(null=False): return mapped_column(DateTime, default=None if null else now, nullable=null)

class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = pk(); name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE"); created_at: Mapped[datetime] = ts()

class Client(Base):
    __tablename__ = "clients"
    id: Mapped[str] = pk(); organization_id: Mapped[str] = fk("organizations")
    client_name: Mapped[str] = mapped_column(String(200)); contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

class User(Base):  # client_id (CLIENT role only) links a client login to its client record
    __tablename__ = "users"
    id: Mapped[str] = pk(); organization_id: Mapped[str] = fk("organizations"); client_id: Mapped[str | None] = fk("clients", True)
    name: Mapped[str] = mapped_column(String(200)); email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300)); role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE"); created_at: Mapped[datetime] = ts()

class ClientGstin(Base):
    __tablename__ = "client_gstins"
    id: Mapped[str] = pk(); organization_id: Mapped[str] = fk("organizations"); client_id: Mapped[str] = fk("clients")
    gstin: Mapped[str] = mapped_column(String(15)); registered_mobile_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

class Device(Base):
    __tablename__ = "otp_devices"
    id: Mapped[str] = pk(); organization_id: Mapped[str] = fk("organizations"); user_id: Mapped[str] = fk("users")
    device_uuid: Mapped[str] = mapped_column(String(100)); platform: Mapped[str] = mapped_column(String(20))
    device_name: Mapped[str] = mapped_column(String(100)); paired_at: Mapped[datetime | None] = ts(True)
    revoked_at: Mapped[datetime | None] = ts(True); last_seen_at: Mapped[datetime | None] = ts(True)

class DevicePairing(Base):
    __tablename__ = "otp_device_pairings"
    id: Mapped[str] = pk(); organization_id: Mapped[str] = fk("organizations"); client_id: Mapped[str] = fk("clients")
    gstin_id: Mapped[str] = fk("client_gstins"); device_id: Mapped[str] = fk("otp_devices")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE"); approved_by: Mapped[str] = fk("users"); created_at: Mapped[datetime] = ts()

class OtpSession(Base):
    __tablename__ = "otp_sessions"
    id: Mapped[str] = pk(); organization_id: Mapped[str] = fk("organizations"); client_id: Mapped[str] = fk("clients")
    gstin_id: Mapped[str] = fk("client_gstins"); requested_by: Mapped[str] = fk("users"); assigned_auditor_id: Mapped[str] = fk("users")
    return_type: Mapped[str] = mapped_column(String(20)); filing_period: Mapped[str] = mapped_column(String(20))
    purpose: Mapped[str] = mapped_column(String(300)); status: Mapped[str] = mapped_column(String(40), default="REQUESTED")
    filing_arn: Mapped[str | None] = mapped_column(String(40), nullable=True)  # recorded separately from portal verification
    expires_at: Mapped[datetime] = ts(); created_at: Mapped[datetime] = ts(); updated_at: Mapped[datetime] = ts()

class AuditLog(Base):
    __tablename__ = "otp_audit_logs"
    id: Mapped[str] = pk(); organization_id: Mapped[str] = fk("organizations"); session_id: Mapped[str | None] = fk("otp_sessions", True)
    actor_user_id: Mapped[str | None] = fk("users", True); event_type: Mapped[str] = mapped_column(String(60))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict); created_at: Mapped[datetime] = ts()

@event.listens_for(AuditLog, "before_update")
@event.listens_for(AuditLog, "before_delete")
def _append_only(*_):
    raise RuntimeError("otp_audit_logs is append-only")

class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = pk(); user_id: Mapped[str] = fk("users"); device_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    refresh_hash: Mapped[str] = mapped_column(String(64)); created_at: Mapped[datetime] = ts()
    expires_at: Mapped[datetime] = ts(); revoked_at: Mapped[datetime | None] = ts(True)
