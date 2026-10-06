"""Key change for a song's stems: pitch-shift every stem by n semitones, tempo unchanged.

Uses ffmpeg's Rubber Band filter. Much lighter than separation: about 30 s of CPU per stem for a
5-minute song, run three at a time, so a key change is ready in roughly a minute on the 4-core VM.
Results are cached per key in <song>/preview/key<+n>/ and reused.
"""
import json
import logging
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

from . import db

log = logging.getLogger("stagekit.pitch")
NAMES = ["vocals", "drums", "bass", "other", "instrumental", "original"]
_lock = threading.Lock()
_has_rubberband = None


def key_dir(sid, n):
    return os.path.join(db.song_dir(sid), "preview", f"key{n:+d}")


def status_path(sid):
    return os.path.join(db.song_dir(sid), "preview", "key_job.json")


def available(sid):
    have = [n for n in range(-6, 7) if n and os.path.exists(os.path.join(key_dir(sid, n), "done"))]
    return sorted(have)


def job(sid):
    try:
        with open(status_path(sid)) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def _job(sid, **kw):
    with open(status_path(sid), "w") as f:
        json.dump(kw, f)


def rubberband_ok():
    global _has_rubberband
    if _has_rubberband is None:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
        _has_rubberband = " rubberband " in r.stdout
    return _has_rubberband


def _filter(n, name):
    ratio = 2 ** (n / 12)
    if rubberband_ok():
        # Keep the voice's character (formants) on vocals and the full mix; instruments shift plainly.
        formant = ":formant=preserved" if name in ("vocals", "original") else ""
        return f"rubberband=pitch={ratio:.6f}{formant}"
    # Fallback without Rubber Band: resample to change pitch, then restore the tempo.
    return f"asetrate=44100*{ratio:.6f},aresample=44100,atempo={1 / ratio:.6f}"


def _source(sid, name):
    d = db.song_dir(sid)
    wav = os.path.join(d, "original.wav" if name == "original" else f"stems/{name}.wav")
    if os.path.exists(wav):
        return wav
    mp3 = os.path.join(d, "preview", f"{name}.mp3")
    return mp3 if os.path.exists(mp3) else None


def _shift(sid, n, name, out_dir):
    src = _source(sid, name)
    if not src:
        return
    out = os.path.join(out_dir, f"{name}.mp3")
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src, "-af", _filter(n, name),
                        "-codec:a", "libmp3lame", "-b:a", "192k", out + ".tmp.mp3"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{name}: {r.stderr.strip()[:200]}")
    os.replace(out + ".tmp.mp3", out)


def run(sid, n):
    out_dir = key_dir(sid, n)
    os.makedirs(out_dir, exist_ok=True)
    names = [x for x in NAMES if _source(sid, x)]
    try:
        with _lock:  # one key change at a time; the CPU is shared with separation
            _job(sid, status="running", key=n, message=f"Changing key {n:+d}…")
            with ThreadPoolExecutor(max_workers=3) as ex:
                list(ex.map(lambda x: _shift(sid, n, x, out_dir), names))
        open(os.path.join(out_dir, "done"), "w").close()
        _job(sid, status="done", key=n, message=f"Key {n:+d} ready")
    except Exception as e:
        log.exception("key change %s %s failed", sid, n)
        _job(sid, status="error", key=n, message=str(e)[:300])


def start(sid, n):
    j = job(sid)
    if j and j.get("status") == "running":
        return False
    _job(sid, status="running", key=n, message=f"Changing key {n:+d}…")
    threading.Thread(target=run, args=(sid, n), daemon=True).start()
    return True


def reset_stale_jobs():
    root = os.path.join(db.DATA_DIR, "songs")
    if not os.path.isdir(root):
        return
    for sid in os.listdir(root):
        j = job(sid) if os.path.isdir(os.path.join(root, sid, "preview")) else None
        if j and j.get("status") == "running":
            _job(sid, status="error", key=j.get("key"), message="Interrupted by a server restart — try again.")
