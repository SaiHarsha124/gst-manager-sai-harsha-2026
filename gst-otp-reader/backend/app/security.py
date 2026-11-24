import hashlib, hmac, os, time
import jwt
from . import config

def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    return salt.hex() + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000).hex()

def verify_password(pw: str, stored: str) -> bool:
    salt, h = stored.split("$")
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex(), h)

def hash_token(t: str) -> str: return hashlib.sha256(t.encode()).hexdigest()

def make_access(user_id: str, sid: str) -> str:
    n = int(time.time())
    return jwt.encode({"sub": user_id, "sid": sid, "iat": n, "exp": n + config.ACCESS_TTL}, config.SECRET_KEY, "HS256")

def decode_access(t: str) -> dict: return jwt.decode(t, config.SECRET_KEY, algorithms=["HS256"])
