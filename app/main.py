"""StageKit API: song import, stems, song cards, set lists."""
import io
import json
import os
import re
import shutil
import zipfile
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth as auth_mod
from . import db, modx, worker

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "web")
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "200"))
AUDIO_EXT = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".aif", ".aiff", ".opus", ".webm", ".mp4"}

app = FastAPI(title="StageKit")


@app.on_event("startup")
def _startup():
    db.init()
    auth_mod.init()
    worker.start()


# ---------- auth (one user, from .env) ----------

auth = auth_mod.require


class Login(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    token = auth_mod.login(request, body.username, body.password)
    auth_mod.set_cookie(response, token)
    return {"ok": True, "user": auth_mod.APP_USER}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    auth_mod.logout(request.cookies.get(auth_mod.COOKIE, ""))
    auth_mod.clear_cookie(response)
    return {"ok": True}


@app.post("/api/logout-all", dependencies=[Depends(auth)])
def logout_all(response: Response):
    auth_mod.logout_everywhere()
    auth_mod.clear_cookie(response)
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    if not auth_mod.enabled():
        return {"ok": True, "auth_required": False}
    ok = auth_mod.valid(request.cookies.get(auth_mod.COOKIE, ""))
    return {"ok": ok, "auth_required": True, "configured": auth_mod.configured(),
            **({"user": auth_mod.APP_USER} if ok else {})}


# ---------- songs ----------

YT_RE = re.compile(r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})")


def _public(song):
    d = db.song_dir(song["id"])
    song["stems"] = [s for s in worker.STEMS if os.path.exists(os.path.join(d, "preview", f"{s}.mp3"))]
    song["quick"] = worker.is_quick(song["id"])
    song["has_chords"] = os.path.exists(os.path.join(d, "chords.json"))
    return song


def _mark_quick(sid, quick):
    if quick:
        open(os.path.join(db.song_dir(sid), "quick"), "w").close()


class AddUrl(BaseModel):
    url: str
    title: Optional[str] = None
    quick: bool = False


@app.post("/api/songs", dependencies=[Depends(auth)])
def add_url(body: AddUrl):
    m = YT_RE.search(body.url)
    if not m:
        raise HTTPException(400, "Paste a YouTube link (youtube.com/watch?v=… or youtu.be/…)")
    sid = db.create_song(body.title or "Loading…", "youtube", body.url.strip(), m.group(1))
    _mark_quick(sid, body.quick)
    return _public(db.get_song(sid))


@app.post("/api/songs/upload", dependencies=[Depends(auth)])
async def add_file(file: UploadFile = File(...), title: str = Form(""), quick: bool = Form(False)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in AUDIO_EXT:
        raise HTTPException(400, f"Unsupported file type {ext or '(none)'}")
    name = title or os.path.splitext(os.path.basename(file.filename))[0]
    sid = db.create_song(name, "upload")
    dest = os.path.join(db.song_dir(sid), f"upload{ext}")
    size = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD_MB << 20:
                f.close()
                shutil.rmtree(db.song_dir(sid), ignore_errors=True)
                db.delete_song(sid)
                raise HTTPException(413, f"File larger than {MAX_UPLOAD_MB} MB")
            f.write(chunk)
    _mark_quick(sid, quick)
    return _public(db.get_song(sid))


@app.get("/api/songs", dependencies=[Depends(auth)])
def songs():
    return [_public(s) for s in db.list_songs()]


@app.get("/api/songs/{sid}", dependencies=[Depends(auth)])
def song(sid: str):
    s = db.get_song(sid)
    if not s:
        raise HTTPException(404, "Song not found")
    return _public(s)


class SongPatch(BaseModel):
    title: Optional[str] = None
    card: Optional[dict] = None


@app.patch("/api/songs/{sid}", dependencies=[Depends(auth)])
def patch_song(sid: str, body: SongPatch):
    s = db.get_song(sid)
    if not s:
        raise HTTPException(404, "Song not found")
    fields = {}
    if body.title is not None:
        fields["title"] = body.title.strip() or s["title"]
    if body.card is not None:
        card = {**db.DEFAULT_CARD, **s["card"], **body.card}
        card["detected"] = s["card"].get("detected", {})  # detection results are read-only
        fields["card"] = card
    if fields:
        db.update_song(sid, **fields)
    return _public(db.get_song(sid))


@app.post("/api/songs/{sid}/retry", dependencies=[Depends(auth)])
def retry(sid: str):
    s = db.get_song(sid)
    if not s:
        raise HTTPException(404, "Song not found")
    db.update_song(sid, status="queued", stage="Waiting", progress=0, error=None)
    return _public(db.get_song(sid))


@app.post("/api/songs/{sid}/stems", dependencies=[Depends(auth)])
def make_stems(sid: str):
    """Turn a chords-only song into a full one (separates stems from the saved audio)."""
    s = db.get_song(sid)
    if not s:
        raise HTTPException(404, "Song not found")
    if busy(s["status"]):
        raise HTTPException(409, "Already processing")
    try:
        os.remove(os.path.join(db.song_dir(sid), "quick"))
    except FileNotFoundError:
        pass
    db.update_song(sid, status="queued", stage="Waiting", progress=0, error=None)
    return _public(db.get_song(sid))


@app.get("/api/songs/{sid}/chords", dependencies=[Depends(auth)])
def chords(sid: str):
    p = os.path.join(db.song_dir(sid), "chords.json")
    if not os.path.exists(p):
        raise HTTPException(404, "No chords yet")
    with open(p) as f:
        return json.load(f)


def busy(status):
    return status in ("queued", "downloading", "separating", "analysing")


@app.delete("/api/songs/{sid}", dependencies=[Depends(auth)])
def remove(sid: str):
    s = db.get_song(sid)
    if not s:
        raise HTTPException(404, "Song not found")
    if s["status"] in ("downloading", "separating", "analysing"):
        raise HTTPException(409, "This song is being processed; delete it when it finishes")
    shutil.rmtree(db.song_dir(sid), ignore_errors=True)
    db.delete_song(sid)
    return {"ok": True}


def _safe_stem(name):
    if name not in worker.STEMS + ["original"]:
        raise HTTPException(404, "Unknown stem")
    return name


@app.get("/api/songs/{sid}/preview/{name}.mp3", dependencies=[Depends(auth)])
def preview(sid: str, name: str):
    p = os.path.join(db.song_dir(sid), "preview", f"{_safe_stem(name)}.mp3")
    if not os.path.exists(p):
        raise HTTPException(404, "Not ready")
    return FileResponse(p, media_type="audio/mpeg")


def _fname(sid, name, ext):
    s = db.get_song(sid)
    base = re.sub(r"[^\w\- ]+", "", (s or {}).get("title") or sid).strip()[:60] or sid
    return f"{base} - {name}.{ext}"


@app.get("/api/songs/{sid}/stem/{name}.wav", dependencies=[Depends(auth)])
def stem_wav(sid: str, name: str):
    name = _safe_stem(name)
    d = db.song_dir(sid)
    p = os.path.join(d, "original.wav" if name == "original" else f"stems/{name}.wav")
    if not os.path.exists(p):
        raise HTTPException(404, "Not ready")
    return FileResponse(p, media_type="audio/wav", filename=_fname(sid, name, "wav"))


@app.get("/api/songs/{sid}/stems.zip", dependencies=[Depends(auth)])
def stems_zip(sid: str):
    d = os.path.join(db.song_dir(sid), "stems")
    if not os.path.isdir(d):
        raise HTTPException(404, "Not ready")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for f in sorted(os.listdir(d)):
            z.write(os.path.join(d, f), _fname(sid, f[:-4], "wav"))
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{_fname(sid, "stems", "zip")}"'})


# ---------- set lists ----------

class SetlistBody(BaseModel):
    name: str
    song_ids: list[str] = []


@app.get("/api/setlists", dependencies=[Depends(auth)])
def setlists():
    return db.list_setlists()


@app.post("/api/setlists", dependencies=[Depends(auth)])
def create_setlist(body: SetlistBody):
    return {"id": db.save_setlist(body.name, body.song_ids)}


@app.put("/api/setlists/{slid}", dependencies=[Depends(auth)])
def update_setlist(slid: str, body: SetlistBody):
    return {"id": db.save_setlist(body.name, body.song_ids, slid)}


@app.delete("/api/setlists/{slid}", dependencies=[Depends(auth)])
def remove_setlist(slid: str):
    db.delete_setlist(slid)
    return {"ok": True}


# ---------- MODX M preset data (sound finder) ----------

@app.get("/api/modx/categories", dependencies=[Depends(auth)])
def modx_categories():
    return modx.categories()


@app.get("/api/modx/performances", dependencies=[Depends(auth)])
def modx_perfs(q: str = "", main: str = "", sub: str = "", limit: int = 60):
    return modx.search_perfs(q, main, sub, min(limit, 300))


@app.get("/api/modx/arps", dependencies=[Depends(auth)])
def modx_arps(q: str = "", cat: str = "", sub: str = "", ts: str = "", bpm: Optional[float] = None, limit: int = 60):
    return modx.search_arps(q, cat, sub, ts, bpm, min(limit, 300))


@app.get("/api/modx/suggest", dependencies=[Depends(auth)])
def modx_suggest(feel: str = "pop", meter: str = "4/4", bpm: Optional[float] = None):
    return modx.suggest(feel, meter, bpm)


@app.get("/api/modx/styles", dependencies=[Depends(auth)])
def modx_styles(q: str = "", meter: str = "", bpm: Optional[float] = None):
    return modx.list_styles(q, meter, bpm)


@app.get("/api/modx/scene-plan", dependencies=[Depends(auth)])
def modx_scene_plan(family: str):
    plan = modx.scene_plan(family)
    if not plan:
        raise HTTPException(404, "Style not found")
    return plan


# ---------- small saved settings (tabla key map and pattern edits) ----------

KV_KEYS = {"tabla"}


@app.get("/api/kv/{key}", dependencies=[Depends(auth)])
def kv_get(key: str):
    if key not in KV_KEYS:
        raise HTTPException(404, "Unknown setting")
    return {"value": db.get_kv(key)}


@app.put("/api/kv/{key}", dependencies=[Depends(auth)])
async def kv_put(key: str, request: Request):
    if key not in KV_KEYS:
        raise HTTPException(404, "Unknown setting")
    body = await request.body()
    if len(body) > 256 * 1024:
        raise HTTPException(413, "Too large")
    db.set_kv(key, json.loads(body or b"null"))
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True}


# Front end (PWA) — mounted last so /api routes win.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
