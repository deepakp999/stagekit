"""Single-user login.

The one account comes from .env (APP_USER / APP_PASSWORD); change it there and
restart. Sessions are random tokens stored in SQLite, so logging out really ends
the session, and changing the password signs out every device.
"""
import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time

from fastapi import HTTPException, Request

from . import db

APP_USER = os.environ.get("APP_USER", "admin").strip()
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "180"))
COOKIE = "sk_session"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") == "1"
# Dev only: run without a login when no password is set and this is "1".
ALLOW_NO_AUTH = os.environ.get("ALLOW_NO_AUTH", "0") == "1"

MAX_FAILS = 5          # failed attempts per IP…
LOCK_SECONDS = 300     # …then locked out for 5 minutes
_fails: dict[str, list[float]] = {}
_lock = threading.Lock()

_salt = b""
_hash = b""


def _kdf(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)


def _pw_fingerprint() -> str:
    # Stored with each session: a new password in .env invalidates old sessions.
    return hashlib.sha256(_hash).hexdigest()[:16]


def init():
    global _salt, _hash
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, pw TEXT, created REAL, expires REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v BLOB)")
        row = c.execute("SELECT v FROM settings WHERE k='salt'").fetchone()
        if row:
            _salt = row[0]
        else:
            _salt = secrets.token_bytes(16)
            c.execute("INSERT INTO settings VALUES ('salt', ?)", (_salt,))
        c.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
    _hash = _kdf(APP_PASSWORD, _salt) if APP_PASSWORD else b""


def enabled() -> bool:
    return bool(APP_PASSWORD) or not ALLOW_NO_AUTH


def configured() -> bool:
    return bool(APP_PASSWORD)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else "") or (request.client.host if request.client else "?")


def check_lock(ip: str):
    now = time.time()
    with _lock:
        recent = [t for t in _fails.get(ip, []) if now - t < LOCK_SECONDS]
        _fails[ip] = recent
        if len(recent) >= MAX_FAILS:
            wait = int(LOCK_SECONDS - (now - recent[0])) + 1
            raise HTTPException(429, f"Too many attempts. Try again in {wait // 60 + 1} min.")


def _fail(ip: str):
    with _lock:
        _fails.setdefault(ip, []).append(time.time())


def login(request: Request, username: str, password: str) -> str:
    if not configured():
        raise HTTPException(503, "Login isn't set up. Put APP_USER and APP_PASSWORD in .env and restart.")
    ip = _client_ip(request)
    check_lock(ip)
    ok_user = hmac.compare_digest(username.strip().lower(), APP_USER.lower())
    ok_pw = hmac.compare_digest(_kdf(password, _salt), _hash)
    if not (ok_user and ok_pw):
        _fail(ip)
        time.sleep(0.5)  # slows guessing a little more
        raise HTTPException(401, "Wrong username or password")
    with _lock:
        _fails.pop(ip, None)
    token = secrets.token_urlsafe(32)
    now = time.time()
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("INSERT INTO sessions VALUES (?,?,?,?)", (token, _pw_fingerprint(), now, now + SESSION_DAYS * 86400))
    return token


def logout(token: str):
    if token:
        with sqlite3.connect(db.DB_PATH) as c:
            c.execute("DELETE FROM sessions WHERE token=?", (token,))


def logout_everywhere():
    with sqlite3.connect(db.DB_PATH) as c:
        c.execute("DELETE FROM sessions")


def valid(token: str) -> bool:
    if not token or not configured():
        return False
    with sqlite3.connect(db.DB_PATH) as c:
        r = c.execute("SELECT pw, expires FROM sessions WHERE token=?", (token,)).fetchone()
    return bool(r) and r[0] == _pw_fingerprint() and r[1] > time.time()


def require(request: Request):
    """FastAPI dependency for every protected route."""
    if not enabled():
        return
    if not valid(request.cookies.get(COOKIE, "")):
        raise HTTPException(401, "Login required")


def set_cookie(response, token: str):
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", secure=COOKIE_SECURE)


def clear_cookie(response):
    response.delete_cookie(COOKIE)
