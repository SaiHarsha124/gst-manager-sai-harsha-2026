from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
import csv
import io
import re
import os

import jwt

from dotenv import load_dotenv
from pwdlib import PasswordHash

load_dotenv()

from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from pydantic import BaseModel, Field

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Text,
    func,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker


# =====================================================
# DATABASE CONFIGURATION
# =====================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "gst_manager.db"

engine = create_engine(
    f"sqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


# =====================================================
# AUTHENTICATION CONFIGURATION
# =====================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable is missing"
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

password_hasher = PasswordHash.recommended()

security = HTTPBearer(auto_error=False)


# =====================================================
# FASTAPI APPLICATION
# =====================================================

app = FastAPI(
    title="GST Manager API",
    version="4.0.0",
    description="GST Manager with enhanced admin security",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================
# DATABASE MODELS
# =====================================================

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(160), nullable=False)

    gstin = Column(
        String(15),
        nullable=False,
        unique=True,
        index=True,
    )

    email = Column(String(160), default="")
    phone = Column(String(30), default="")
    state = Column(String(80), default="")

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


class DemoRequest(Base):
    __tablename__ = "demo_requests"

    id = Column(Integer, primary_key=True, index=True)

    client_name = Column(String(160), nullable=False)

    email = Column(String(160), default="")
    gstin = Column(String(15), default="")
    message = Column(Text, default="")

    status = Column(String(30), default="Pending")

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


class GSTHistory(Base):
    __tablename__ = "gst_history"

    id = Column(Integer, primary_key=True, index=True)

    gstin = Column(String(15), nullable=False)
    result = Column(String(30), nullable=False)
    message = Column(String(255), default="")

    checked_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = Column(
        String(255),
        nullable=False,
    )

    token_version = Column(
        Integer,
        nullable=False,
        default=0,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


# Create tables without deleting existing data.
Base.metadata.create_all(bind=engine)


# =====================================================
# DATABASE MIGRATION
# =====================================================

with engine.connect() as connection:

    columns = connection.execute(
        text("PRAGMA table_info(admins)")
    ).fetchall()

    column_names = [
        column[1]
        for column in columns
    ]

    if "token_version" not in column_names:

        connection.execute(
            text(
                "ALTER TABLE admins "
                "ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"
            )
        )

        connection.commit()


# =====================================================
# PYDANTIC REQUEST MODELS
# =====================================================

class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    gstin: str = Field(min_length=15, max_length=15)

    email: str = ""
    phone: str = ""
    state: str = ""


class RequestIn(BaseModel):
    client_name: str = Field(min_length=1, max_length=160)

    email: str = ""
    gstin: str = ""
    message: str = ""


class ActionIn(BaseModel):
    status: str


class VerifyIn(BaseModel):
    gstin: str = Field(min_length=1, max_length=30)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)


# =====================================================
# LOGIN ATTEMPT PROTECTION
# =====================================================

login_attempts = {}
login_lock = Lock()

MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_MINUTES = 15


def check_login_attempts(key):

    now = datetime.now(timezone.utc)

    with login_lock:

        attempts = login_attempts.get(key, [])

        attempts = [
            attempt
            for attempt in attempts
            if now - attempt < timedelta(
                minutes=LOGIN_WINDOW_MINUTES
            )
        ]

        login_attempts[key] = attempts

        if len(attempts) >= MAX_LOGIN_ATTEMPTS:

            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Try again after 15 minutes.",
            )


def record_failed_login(key):

    with login_lock:

        login_attempts.setdefault(
            key,
            [],
        ).append(
            datetime.now(timezone.utc)
        )


def clear_login_attempts(key):

    with login_lock:
        login_attempts.pop(key, None)


# =====================================================
# JWT TOKEN CREATION
# =====================================================

def create_access_token(admin: Admin):

    expiration = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": admin.username,
        "ver": admin.token_version,
        "exp": expiration,
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


# =====================================================
# AUTHENTICATION VALIDATION
# =====================================================

def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):

    if credentials is None:

        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:

        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )

        username = payload.get("sub")
        token_version = payload.get("ver", 0)

        if not username:

            raise HTTPException(
                status_code=401,
                detail="Invalid authentication token",
            )

    except jwt.InvalidTokenError:

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db = SessionLocal()

    try:

        admin = (
            db.query(Admin)
            .filter(Admin.username == username)
            .first()
        )

        if not admin:

            raise HTTPException(
                status_code=401,
                detail="Administrator account not found",
            )

        if token_version != admin.token_version:

            raise HTTPException(
                status_code=401,
                detail="Session expired. Please log in again.",
            )

        return admin

    finally:
        db.close()


# =====================================================
# ADMIN LOGIN
# =====================================================

@app.post("/api/auth/login")
def admin_login(
    data: LoginIn,
    request: Request,
):

    username = data.username.strip()

    client_ip = (
        request.client.host
        if request.client
        else "unknown"
    )

    attempt_key = f"{client_ip}:{username}"

    check_login_attempts(attempt_key)

    db = SessionLocal()

    try:

        admin = (
            db.query(Admin)
            .filter(Admin.username == username)
            .first()
        )

        if not admin or not password_hasher.verify(
            data.password,
            admin.password_hash,
        ):

            record_failed_login(attempt_key)

            raise HTTPException(
                status_code=401,
                detail="Incorrect username or password",
            )

        clear_login_attempts(attempt_key)

        token = create_access_token(admin)

        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "username": admin.username,
        }

    finally:
        db.close()


# =====================================================
# ADMIN PROFILE
# =====================================================

@app.get("/api/auth/me")
def get_admin_profile(
    admin: Admin = Depends(get_current_admin),
):

    return {
        "id": admin.id,
        "username": admin.username,
        "created_at": (
            admin.created_at.isoformat()
            if admin.created_at else None
        ),
    }


# =====================================================
# CHANGE ADMIN PASSWORD
# =====================================================

@app.post("/api/auth/change-password")
def change_admin_password(
    data: PasswordChangeIn,
    admin: Admin = Depends(get_current_admin),
):

    if data.current_password == data.new_password:

        raise HTTPException(
            status_code=400,
            detail="New password must be different from current password",
        )

    db = SessionLocal()

    try:

        current_admin = db.get(Admin, admin.id)

        if not current_admin:

            raise HTTPException(
                status_code=404,
                detail="Administrator not found",
            )

        if not password_hasher.verify(
            data.current_password,
            current_admin.password_hash,
        ):

            raise HTTPException(
                status_code=400,
                detail="Current password is incorrect",
            )

        current_admin.password_hash = password_hasher.hash(
            data.new_password
        )

        # Invalidate all previously issued tokens.
        current_admin.token_version += 1

        db.commit()

        return {
            "message": "Password changed successfully. Please log in again."
        }

    finally:
        db.close()


# =====================================================
# GSTIN FORMAT VALIDATION
# =====================================================

GSTIN_PATTERN = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
)


def validate_gstin(gstin):

    gstin = gstin.strip().upper()

    return bool(
        GSTIN_PATTERN.fullmatch(gstin)
    )


# =====================================================
# RESPONSE CONVERSION FUNCTIONS
# =====================================================

def client_dict(item):

    return {
        "id": item.id,
        "name": item.name,
        "gstin": item.gstin,
        "email": item.email,
        "phone": item.phone,
        "state": item.state,
        "created_at": (
            item.created_at.isoformat()
            if item.created_at else None
        ),
    }


def request_dict(item):

    return {
        "id": item.id,
        "client_name": item.client_name,
        "email": item.email,
        "gstin": item.gstin,
        "message": item.message,
        "status": item.status,
        "created_at": (
            item.created_at.isoformat()
            if item.created_at else None
        ),
    }


def history_dict(item):

    return {
        "id": item.id,
        "gstin": item.gstin,
        "result": item.result,
        "message": item.message,
        "checked_at": (
            item.checked_at.isoformat()
            if item.checked_at else None
        ),
    }


# =====================================================
# ROOT AND HEALTH CHECK
# =====================================================

@app.get("/")
def root():

    return {
        "message": "GST Manager API is running",
        "version": "4.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health():

    try:

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "connected",
            "mode": "simulation-only",
            "version": "4.0.0",
        }

    except Exception:

        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )


# =====================================================
# CLIENT MANAGEMENT
# =====================================================

@app.get("/api/clients")
def get_clients(
    admin: Admin = Depends(get_current_admin),
):

    db = SessionLocal()

    try:

        clients = (
            db.query(Client)
            .order_by(Client.id.desc())
            .all()
        )

        return [
            client_dict(client)
            for client in clients
        ]

    finally:
        db.close()


@app.post("/api/clients")
def add_client(
    data: ClientIn,
    admin: Admin = Depends(get_current_admin),
):

    db = SessionLocal()

    try:

        gstin = data.gstin.strip().upper()

        if not validate_gstin(gstin):

            raise HTTPException(
                status_code=400,
                detail="Invalid GSTIN format",
            )

        existing = (
            db.query(Client)
            .filter(Client.gstin == gstin)
            .first()
        )

        if existing:

            raise HTTPException(
                status_code=409,
                detail="Client with this GSTIN already exists",
            )

        client = Client(
            name=data.name.strip(),
            gstin=gstin,
            email=data.email.strip(),
            phone=data.phone.strip(),
            state=data.state.strip(),
        )

        db.add(client)
        db.commit()
        db.refresh(client)

        return client_dict(client)

    finally:
        db.close()


@app.delete("/api/clients/{client_id}")
def delete_client(
    client_id: int,
    admin: Admin = Depends(get_current_admin),
):

    db = SessionLocal()

    try:

        client = db.get(Client, client_id)

        if not client:

            raise HTTPException(
                status_code=404,
                detail="Client not found",
            )

        db.delete(client)
        db.commit()

        return {
            "message": "Client deleted successfully"
        }

    finally:
        db.close()


# =====================================================
# DEMO REQUEST MANAGEMENT
# =====================================================

@app.get("/api/requests")
def get_requests(
    admin: Admin = Depends(get_current_admin),
):

    db = SessionLocal()

    try:

        requests = (
            db.query(DemoRequest)
            .order_by(DemoRequest.id.desc())
            .all()
        )

        return [
            request_dict(item)
            for item in requests
        ]

    finally:
        db.close()


@app.post("/api/requests")
def add_request(
    data: RequestIn,
    admin: Admin = Depends(get_current_admin),
):

    db = SessionLocal()

    try:

        request = DemoRequest(
            client_name=data.client_name.strip(),
            email=data.email.strip(),
            gstin=data.gstin.strip().upper(),
            message=data.message.strip(),
            status="Pending",
        )

        db.add(request)
        db.commit()
        db.refresh(request)

        return request_dict(request)

    finally:
        db.close()


@app.post("/api/requests/{request_id}/action")
def update_request(
    request_id: int,
    data: ActionIn,
    admin: Admin = Depends(get_current_admin),
):

    allowed_statuses = [
        "Pending",
        "Approved",
        "Rejected",
        "Completed",
    ]

    if data.status not in allowed_statuses:

        raise HTTPException(
            status_code=400,
            detail="Invalid request status",
        )

    db = SessionLocal()

    try:

        request = db.get(
            DemoRequest,
            request_id,
        )

        if not request:

            raise HTTPException(
                status_code=404,
                detail="Request not found",
            )

        request.status = data.status

        db.commit()
        db.refresh(request)

        return request_dict(request)

    finally:
        db.close()


@app.delete("/api/requests/{request_id}")
def delete_request(
    request_id: int,
    admin: Admin = Depends(get_current_admin),
):

    db = SessionLocal()

    try:

        request = db.get(
            DemoRequest,
            request_id,
        )

        if not request:

            raise HTTPException(
                status_code=404,
                detail="Request not found",
            )

        db.delete(request)
        db.commit()

        return {
            "message": "Request deleted successfully"
        }

    finally:
        db.close()


# =====================================================
# GST VERIFICATION
# =====================================================

@app.post("/api/gst/verify")
def verify_gst(
    data: VerifyIn,
    admin: Admin = Depends(get_current_admin),
):

    gstin = data.gstin.strip().upper()

    valid = validate_gstin(gstin)

    if valid:

        result = "Format valid"

        message = (
            "GSTIN format looks valid. "
            "This is not a live GST portal verification."
        )

    else:

        result = "Invalid"

        message = "GSTIN format is invalid."

    db = SessionLocal()

    try:

        record = GSTHistory(
            gstin=gstin,
            result=result,
            message=message,
        )

        db.add(record)
        db.commit()
        db.refresh(record)

        return {
            **history_dict(record),
            "valid": valid,
            "mode": "simulation-only",
        }

    finally:
        db.close()


# =====================================================
# GST VERIFICATION HISTORY
# =====================================================

@app.get("/api/gst/history")
def get_history(
    admin: Admin = Depends(get_current_admin),
):

    db = SessionLocal()

    try:

        records = (
            db.query(GSTHistory)
            .order_by(GSTHistory.id.desc())
            .limit(100)
            .all()
        )

        return [
            history_dict(record)
            for record in records
        ]

    finally:
        db.close()


@app.delete("/api/gst/history")
def clear_history(
    admin: Admin = Depends(get_current_admin),
):

    db = SessionLocal()

    try:

        db.query(GSTHistory).delete()

        db.commit()

        return {
            "message": "GST history cleared successfully"
        }

    finally:
        db.close()


@app.delete("/api/gst/history/{record_id}")
def delete_history(
    record_id: int,
    admin: Admin = Depends(get_current_admin),
):

    db = SessionLocal()

    try:

        record = db.get(
            GSTHistory,
            record_id,
        )

        if not record:

            raise HTTPException(
                status_code=404,
                detail="History record not found",
            )

        db.delete(record)
        db.commit()

        return {
            "message": "History record deleted successfully"
        }

    finally:
        db.close()


# =====================================================
# ANALYTICS AND DASHBOARD STATISTICS
# =====================================================

@app.get("/api/analytics")
@app.get("/api/dashboard")
@app.get("/api/dashboard/stats")
@app.get("/api/stats")
@app.get("/api/gst/analytics")
def analytics(
    admin: Admin = Depends(get_current_admin),
):

    db = SessionLocal()

    try:

        total_clients = (
            db.query(func.count(Client.id)).scalar()
            or 0
        )

        total_requests = (
            db.query(func.count(DemoRequest.id)).scalar()
            or 0
        )

        pending = (
            db.query(func.count(DemoRequest.id))
            .filter(DemoRequest.status == "Pending")
            .scalar()
            or 0
        )

        approved = (
            db.query(func.count(DemoRequest.id))
            .filter(DemoRequest.status == "Approved")
            .scalar()
            or 0
        )

        rejected = (
            db.query(func.count(DemoRequest.id))
            .filter(DemoRequest.status == "Rejected")
            .scalar()
            or 0
        )

        completed = (
            db.query(func.count(DemoRequest.id))
            .filter(DemoRequest.status == "Completed")
            .scalar()
            or 0
        )

        gst_checks = (
            db.query(func.count(GSTHistory.id)).scalar()
            or 0
        )

        valid_checks = (
            db.query(func.count(GSTHistory.id))
            .filter(GSTHistory.result == "Format valid")
            .scalar()
            or 0
        )

        return {
            "total_clients": total_clients,
            "total_requests": total_requests,
            "pending_requests": pending,
            "approved_requests": approved,
            "rejected_requests": rejected,
            "completed_requests": completed,
            "gst_checks": gst_checks,
            "valid_gst_checks": valid_checks,
        }

    finally:
        db.close()


# =====================================================
# CSV EXPORT FUNCTION
# =====================================================

def csv_response(rows, headers, filename):

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow(headers)

    for row in rows:
        writer.writerow(row)

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                f'attachment; filename="{filename}"'
        },
    )


# =====================================================
# EXPORT CLIENTS
# =====================================================

@app.get("/api/export/clients")
def export_clients(
    admin: Admin = Depends(get_current_admin),
):

    db = SessionLocal()

    try:

        clients = (
            db.query(Client)
            .order_by(Client.id)
            .all()
        )

        rows = [
            [
                item.id,
                item.name,
                item.gstin,
                item.email,
                item.phone,
                item.state,
                item.created_at,
            ]
            for item in clients
        ]

        headers = [
            "ID",
            "Name",
            "GSTIN",
            "Email",
            "Phone",
            "State",
            "Created At",
        ]

        return csv_response(
            rows,
            headers,
            "clients.csv",
        )

    finally:
        db.close()


# =====================================================
# EXPORT DEMO REQUESTS
# =====================================================

@app.get("/api/export/requests")
def export_requests(
    admin: Admin = Depends(get_current_admin),
):

    db = SessionLocal()

    try:

        requests = (
            db.query(DemoRequest)
            .order_by(DemoRequest.id)
            .all()
        )

        rows = [
            [
                item.id,
                item.client_name,
                item.email,
                item.gstin,
                item.message,
                item.status,
                item.created_at,
            ]
            for item in requests
        ]

        headers = [
            "ID",
            "Client Name",
            "Email",
            "GSTIN",
            "Message",
            "Status",
            "Created At",
        ]

        return csv_response(
            rows,
            headers,
            "requests.csv",
        )

    finally:
        db.close()


# =====================================================
# INITIAL ADMIN CREATION
# =====================================================

@app.on_event("startup")
def startup_event():

    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if not admin_username or not admin_password:

        raise RuntimeError(
            "ADMIN_USERNAME and ADMIN_PASSWORD must be configured"
        )

    db = SessionLocal()

    try:

        existing_admin = (
            db.query(Admin)
            .filter(Admin.username == admin_username)
            .first()
        )

        if not existing_admin:

            new_admin = Admin(
                username=admin_username,
                password_hash=password_hasher.hash(
                    admin_password
                ),
            )

            db.add(new_admin)
            db.commit()

            print(
                "Initial administrator created successfully."
            )

    finally:
        db.close()

    print("====================================")
    print("       GST MANAGER BACKEND")
    print("====================================")
    print("Backend: http://127.0.0.1:8000")
    print("API Docs: http://127.0.0.1:8000/docs")
    print("Health: http://127.0.0.1:8000/api/health")
    print("Database:", DB_PATH)
    print("Authentication: ENABLED")
    print("Security: PHASE 2")
    print("====================================")
