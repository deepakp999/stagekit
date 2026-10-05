"""SQLite storage for songs and set lists."""
import json
import os
import sqlite3
import threading
import time
import uuid

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "stagekit.db")
_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    os.makedirs(os.path.join(DATA_DIR, "songs"), exist_ok=True)
    with _lock, _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS songs (
                id TEXT PRIMARY KEY,
                title TEXT,
                source TEXT,
                source_url TEXT,
                youtube_id TEXT,
                status TEXT,
                stage TEXT,
                progress REAL,
                error TEXT,
                duration REAL,
                card TEXT,
                created REAL,
                updated REAL)"""
        )
        c.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
        c.execute(
            """CREATE TABLE IF NOT EXISTS setlists (
                id TEXT PRIMARY KEY,
                name TEXT,
                song_ids TEXT,
                created REAL)"""
        )
        # Jobs interrupted by a restart go back to the queue.
        c.execute(
            "UPDATE songs SET status='queued', stage='Waiting', progress=0 "
            "WHERE status IN ('downloading','separating','analysing')"
        )


DEFAULT_CARD = {
    "key": "",
    "bpm": None,
    "meter": "4/4",
    "detected": {},
    "modx": {"performance": "", "bank_msb": None, "bank_lsb": None, "program": None},
    "sections": [],
    "notes": "",
}


def _row(r):
    if r is None:
        return None
    d = dict(r)
    d["card"] = json.loads(d["card"] or "{}")
    return d


def create_song(title, source, source_url=None, youtube_id=None):
    sid = uuid.uuid4().hex[:12]
    now = time.time()
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO songs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, title, source, source_url, youtube_id, "queued", "Waiting", 0,
             None, None, json.dumps(DEFAULT_CARD), now, now),
        )
    os.makedirs(song_dir(sid), exist_ok=True)
    return sid


def song_dir(sid):
    return os.path.join(DATA_DIR, "songs", sid)


def get_song(sid):
    with _conn() as c:
        return _row(c.execute("SELECT * FROM songs WHERE id=?", (sid,)).fetchone())


def list_songs():
    with _conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM songs ORDER BY created DESC")]


def queued_ids():
    with _conn() as c:
        return [r["id"] for r in c.execute("SELECT id FROM songs WHERE status='queued' ORDER BY created")]


def update_song(sid, **fields):
    if "card" in fields:
        fields["card"] = json.dumps(fields["card"])
    fields["updated"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock, _conn() as c:
        c.execute(f"UPDATE songs SET {cols} WHERE id=?", (*fields.values(), sid))


def delete_song(sid):
    with _lock, _conn() as c:
        c.execute("DELETE FROM songs WHERE id=?", (sid,))


def list_setlists():
    with _conn() as c:
        out = []
        for r in c.execute("SELECT * FROM setlists ORDER BY created DESC"):
            d = dict(r)
            d["song_ids"] = json.loads(d["song_ids"] or "[]")
            out.append(d)
        return out


def save_setlist(name, song_ids, slid=None):
    slid = slid or uuid.uuid4().hex[:12]
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO setlists VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, song_ids=excluded.song_ids",
            (slid, name, json.dumps(song_ids), time.time()),
        )
    return slid


def delete_setlist(slid):
    with _lock, _conn() as c:
        c.execute("DELETE FROM setlists WHERE id=?", (slid,))


def get_kv(key, default=None):
    with _conn() as c:
        r = c.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
    return json.loads(r["v"]) if r else default


def set_kv(key, value):
    with _lock, _conn() as c:
        c.execute("INSERT INTO kv VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, json.dumps(value)))
