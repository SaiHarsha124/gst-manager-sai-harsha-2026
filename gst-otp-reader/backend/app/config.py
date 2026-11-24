import os

# DATABASE CONFIGURATION

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./gst_otp.db"
)

# JWT SECURITY CONFIGURATION

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is missing. "
        "Set a secure SECRET_KEY environment variable."
    )

if len(SECRET_KEY) < 64:
    raise RuntimeError(
        "SECRET_KEY must contain at least 64 characters."
    )

# TOKEN EXPIRATION

ACCESS_TTL = 15 * 60

REFRESH_TTL = 14 * 24 * 60 * 60

# OTP SESSION CONFIGURATION

SESSION_TTL = int(
    os.getenv("OTP_SESSION_TTL_SECONDS", "300")
)

if SESSION_TTL <= 0:
    raise RuntimeError(
        "OTP_SESSION_TTL_SECONDS must be greater than zero."
    )