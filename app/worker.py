"""Background job runner: download -> separate (UVR models) -> analyse -> previews.

One job at a time. Separation is CPU-heavy, so running songs in parallel on a
4-core VM would only make every song slower.
"""
import glob
import logging
import os
import shutil
import subprocess
import threading
import time
import traceback

from . import db
import json

from .analysis import add_slash_bass, analyse, detect_chords

log = logging.getLogger("stagekit.worker")

# Pass 1 splits vocals from the instrumental with a UVR model; pass 2 splits the
# instrumental into drums / bass / other with Demucs. Measured on 2 CPU cores,
# per minute of audio: balanced ~3.5 min, fast ~2 min, best ~30 min (RoFormer is
# GPU-class; only worth it on a GPU machine).
PRESETS = {
    "balanced": ("Kim_Vocal_2.onnx", "htdemucs.yaml"),
    "best": ("model_bs_roformer_ep_317_sdr_12.9755.ckpt", "htdemucs_ft.yaml"),
    "fast": (None, "htdemucs.yaml"),
}
SEPARATION_MODE = os.environ.get("SEPARATION_MODE", "balanced")
if SEPARATION_MODE not in PRESETS:
    SEPARATION_MODE = "balanced"
VOCAL_MODEL = os.environ.get("VOCAL_MODEL") or PRESETS[SEPARATION_MODE][0]
STEM_MODEL = os.environ.get("STEM_MODEL") or PRESETS[SEPARATION_MODE][1]
MODEL_DIR = os.path.join(db.DATA_DIR, "models")
YTDLP_COOKIES = os.environ.get("YTDLP_COOKIES", "")  # path to a cookies.txt, helps on cloud IPs

STEMS = ["vocals", "drums", "bass", "other", "instrumental"]


def is_quick(sid):
    """Chords-only songs skip stem separation until the player asks for stems."""
    return os.path.exists(os.path.join(db.song_dir(sid), "quick"))


class JobError(Exception):
    pass


def _set(sid, **kw):
    db.update_song(sid, **kw)


def _ffmpeg(*args):
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise JobError(f"ffmpeg failed: {r.stderr.strip()[:300]}")


def _duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def download(sid, url, out_dir):
    import yt_dlp

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                _set(sid, progress=round(0.1 * d.get("downloaded_bytes", 0) / total, 3))

    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(out_dir, "download.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "progress_hooks": [hook],
    }
    if YTDLP_COOKIES and os.path.exists(YTDLP_COOKIES):
        opts["cookiefile"] = YTDLP_COOKIES
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        msg = str(e)
        if "Sign in to confirm" in msg or "bot" in msg.lower() or "429" in msg:
            msg = ("YouTube blocked the download from this server (common on cloud IPs). "
                   "Add a cookies.txt (see README) or upload the audio file instead.")
        raise JobError(msg[:400])
    files = [f for f in glob.glob(os.path.join(out_dir, "download.*")) if not f.endswith(".part")]
    if not files:
        raise JobError("Download finished but no audio file was found.")
    return files[0], info.get("title") or "Untitled"


def _find(outputs, out_dir, word):
    for f in outputs:
        p = f if os.path.isabs(f) else os.path.join(out_dir, f)
        if f"({word})".lower() in os.path.basename(p).lower():
            return p
    return None


def separate(sid, wav, d):
    from audio_separator.separator import Separator

    tmp = os.path.join(d, "sep_tmp")
    os.makedirs(tmp, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)

    def sep(model):
        s = Separator(output_dir=tmp, output_format="WAV", model_file_dir=MODEL_DIR)
        s.load_model(model_filename=model)
        return s.separate(wav_in)

    stems = {}
    if VOCAL_MODEL:
        _set(sid, stage=f"Separating vocals (UVR {VOCAL_MODEL.split('.')[0]})", progress=0.15)
        wav_in = wav
        out1 = sep(VOCAL_MODEL)
        stems["vocals"] = _find(out1, tmp, "vocals")
        stems["instrumental"] = _find(out1, tmp, "instrumental")
        if not stems["vocals"] or not stems["instrumental"]:
            raise JobError(f"Vocal model output not recognised: {out1}")
        _set(sid, stage="Separating drums, bass, other (Demucs)", progress=0.5)
        wav_in = stems["instrumental"]
        out2 = sep(STEM_MODEL)
        for w in ("drums", "bass", "other"):
            stems[w] = _find(out2, tmp, w)
    else:
        _set(sid, stage="Separating stems (Demucs)", progress=0.2)
        wav_in = wav
        out = sep(STEM_MODEL)
        for w in ("vocals", "drums", "bass", "other"):
            stems[w] = _find(out, tmp, w)

    missing = [k for k in ("vocals", "drums", "bass", "other") if not stems.get(k)]
    if missing:
        raise JobError(f"Separation did not produce: {', '.join(missing)}")

    stem_dir = os.path.join(d, "stems")
    os.makedirs(stem_dir, exist_ok=True)
    for name, path in stems.items():
        if path:
            shutil.move(path, os.path.join(stem_dir, f"{name}.wav"))
    shutil.rmtree(tmp, ignore_errors=True)
    return stem_dir


def previews(sid, d, stem_dir):
    """Compressed copies for streaming to phones; WAVs stay for download."""
    _set(sid, stage="Making previews", progress=0.9)
    pdir = os.path.join(d, "preview")
    os.makedirs(pdir, exist_ok=True)
    for name in (STEMS if stem_dir else []):
        src = os.path.join(stem_dir, f"{name}.wav")
        if os.path.exists(src):
            _ffmpeg("-i", src, "-codec:a", "libmp3lame", "-b:a", "192k", os.path.join(pdir, f"{name}.mp3"))
    _ffmpeg("-i", os.path.join(d, "original.wav"), "-codec:a", "libmp3lame", "-b:a", "192k",
            os.path.join(pdir, "original.mp3"))


def run_job(sid):
    song = db.get_song(sid)
    d = db.song_dir(sid)
    os.makedirs(d, exist_ok=True)
    wav = os.path.join(d, "original.wav")
    try:
        if song["source"] == "youtube" and not os.path.exists(wav):
            _set(sid, status="downloading", stage="Downloading", progress=0.01)
            src, title = download(sid, song["source_url"], d)
            if song["title"] in (None, "", "Loading…"):
                _set(sid, title=title)
        else:
            cands = glob.glob(os.path.join(d, "upload.*"))
            src = cands[0] if cands else wav
        if not os.path.exists(wav):
            _set(sid, stage="Converting audio", progress=0.1)
            _ffmpeg("-i", src, "-ac", "2", "-ar", "44100", wav)
        _set(sid, duration=_duration(wav))

        quick = is_quick(sid)
        stem_dir = None
        if not quick:
            _set(sid, status="separating")
            stem_dir = separate(sid, wav, d)

        _set(sid, status="analysing", stage="Detecting key and tempo", progress=0.8)
        card = db.get_song(sid)["card"]
        try:
            det = analyse(wav, os.path.join(stem_dir, "drums.wav") if stem_dir else None)
            card["detected"] = det
            if not card.get("key"):
                card["key"] = det["key"]
            if not card.get("bpm"):
                card["bpm"] = det["bpm"]
        except Exception as e:  # analysis is optional; never fail the song for it
            card["detected"] = {"error": str(e)[:200]}
        _set(sid, card=card)

        _set(sid, stage="Detecting chords", progress=0.85)
        try:
            # The instrumental stem has no vocal melody, so chords come out cleaner.
            src_c = os.path.join(stem_dir, "instrumental.wav") if stem_dir else wav
            if not os.path.exists(src_c):
                src_c = wav
            chords = detect_chords(src_c)
            bass_wav = os.path.join(stem_dir, "bass.wav") if stem_dir else None
            if bass_wav and os.path.exists(bass_wav):
                try:  # bass movement -> slash chords (C/B, Am/G)
                    chords = add_slash_bass(chords, bass_wav)
                    open(os.path.join(d, "chords.bass"), "w").close()
                except Exception as e:
                    log.error("slash bass failed for %s: %s", sid, e)
            with open(os.path.join(d, "chords.json"), "w") as f:
                json.dump(chords, f)
        except Exception as e:
            log.error("chords failed for %s: %s", sid, e)

        previews(sid, d, stem_dir)
        for f in glob.glob(os.path.join(d, "download.*")) + glob.glob(os.path.join(d, "upload.*")):
            os.remove(f)
        _set(sid, status="ready", stage="Ready", progress=1.0, error=None)
    except Exception as e:
        log.error("job %s failed: %s", sid, traceback.format_exc())
        _set(sid, status="error", stage="Failed", error=str(e)[:500])


def loop():
    while True:
        ids = db.queued_ids()
        # Chords-only songs jump the queue: someone is waiting to play them now.
        sid = next((i for i in ids if is_quick(i)), ids[0] if ids else None)
        if sid:
            run_job(sid)
        else:
            time.sleep(2)


def start():
    threading.Thread(target=loop, daemon=True, name="stagekit-worker").start()
