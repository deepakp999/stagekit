"""Lyrics for a song, timed line by line so chords can sit over the words.

Sources, in the order worth trying:
  1. LRCLIB (free, no key): community time-synced lyrics; has many Malayalam/Hindi/Tamil film songs.
  2. Whisper (faster-whisper, runs on the server CPU): transcribes the vocal stem with word timings.
     Fine for English/Hindi; rougher for Malayalam, so check it before relying on it.
  3. Paste: your own lyrics (plain lines or .lrc); time plain lines by tapping along in the app.

Stored as <song dir>/lyrics.json: {"source", "lines": [{"t", "text", "words"?: [{"t", "w"}]}]}.
"""
import json
import logging
import os
import re
import threading
import urllib.parse
import urllib.request

from . import db

log = logging.getLogger("stagekit.lyrics")

LYRICS_MODEL = os.environ.get("LYRICS_MODEL", "small")  # tiny / base / small / medium
WHISPER_DIR = os.path.join(db.DATA_DIR, "models", "whisper")
_lock = threading.Lock()  # one transcription at a time; the CPU is shared with separation


def path(sid):
    return os.path.join(db.song_dir(sid), "lyrics.json")


def job_path(sid):
    return os.path.join(db.song_dir(sid), "lyrics_job.json")


def load(sid):
    p = path(sid)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(sid, data):
    with open(path(sid), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def job(sid):
    try:
        with open(job_path(sid), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def _job(sid, **kw):
    with open(job_path(sid), "w", encoding="utf-8") as f:
        json.dump(kw, f, ensure_ascii=False)


# ---------- parsing ----------

LRC_TIME = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


def parse_text(text):
    """LRC ('[01:02.30] words') or plain lines (untimed, t=None)."""
    lines = []
    for raw in (text or "").splitlines():
        stamps = LRC_TIME.findall(raw)
        words = LRC_TIME.sub("", raw).strip()
        if re.match(r"^\[[a-z]+:", raw.strip(), re.I):  # [ar:..] [ti:..] tags
            continue
        if stamps:
            for m, sec in stamps:
                lines.append({"t": round(int(m) * 60 + float(sec), 2), "text": words})
        elif words:
            lines.append({"t": None, "text": words})
    if any(x["t"] is not None for x in lines):
        lines = sorted([x for x in lines if x["t"] is not None], key=lambda x: x["t"])
    return lines


# ---------- LRCLIB ----------

NOISE = re.compile(
    r"\((?:[^)]*(?:official|video|lyric|audio|full|song|hd|4k|remaster|from|movie|film)[^)]*)\)|"
    r"\[[^\]]*\]|official\s*(?:music\s*)?video|lyric(?:al)?\s*video|video\s*song|full\s*song|"
    r"\bhd\b|\b4k\b|\baudio\b", re.I)


def clean_title(title):
    t = NOISE.sub(" ", title or "")
    t = re.split(r"\s[|•]\s|\s\|\s?|\|", t)[0]  # "Song | Movie | Singer" → "Song"
    return re.sub(r"\s+", " ", t).strip(" -–—:")


def lrclib_search(query, duration=None):
    url = "https://lrclib.net/api/search?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": "StageKit/1.0 (personal performance tool)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        results = json.load(r)
    synced = [x for x in results if x.get("syncedLyrics")]
    if not synced:
        return None, results[:5]
    if duration:  # prefer the version whose length matches this recording
        synced.sort(key=lambda x: abs((x.get("duration") or 0) - duration))
    best = synced[0]
    return best, synced[:5]


# ---------- Whisper ----------

def transcribe(audio, language=None):
    from faster_whisper import WhisperModel  # heavy import; only when used

    os.makedirs(WHISPER_DIR, exist_ok=True)
    model = WhisperModel(LYRICS_MODEL, device="cpu", compute_type="int8", download_root=WHISPER_DIR,
                         cpu_threads=max(1, (os.cpu_count() or 2) - 1))
    segments, info = model.transcribe(audio, language=language or None, word_timestamps=True,
                                      vad_filter=True, beam_size=5, condition_on_previous_text=False)
    lines = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        words = [{"t": round(w.start, 2), "w": w.word.strip()} for w in (seg.words or []) if w.word.strip()]
        lines.append({"t": round(seg.start, 2), "text": text, **({"words": words} if words else {})})
    return lines, info.language


# ---------- background job ----------

def fetch(sid, source, query="", language=""):
    """Runs in a thread. Writes lyrics_job.json for progress and lyrics.json on success."""
    song = db.get_song(sid)
    d = db.song_dir(sid)
    try:
        if source == "lrclib":
            q = query.strip() or clean_title(song["title"])
            _job(sid, status="running", message=f"Searching LRCLIB for “{q}”…")
            best, others = lrclib_search(q, song.get("duration"))
            if not best:
                names = ", ".join(f"{x.get('trackName')} – {x.get('artistName')}" for x in others) or "nothing"
                raise RuntimeError(f"No synced lyrics on LRCLIB for “{q}” (found: {names}). "
                                   "Try a shorter search (song name + film), Transcribe, or paste the lyrics.")
            lines = parse_text(best["syncedLyrics"])
            save(sid, {"source": "lrclib", "match": f"{best.get('trackName')} – {best.get('artistName')}",
                       "query": q, "lines": lines})
            _job(sid, status="done", message=f"Found: {best.get('trackName')} – {best.get('artistName')}")
        elif source == "whisper":
            if not _lock.acquire(blocking=False):
                raise RuntimeError("Another song is being transcribed; try again in a few minutes.")
            try:
                audio = os.path.join(d, "stems", "vocals.wav")
                if not os.path.exists(audio):
                    audio = os.path.join(d, "original.wav")
                _job(sid, status="running", message=f"Transcribing the vocals (Whisper {LYRICS_MODEL}, a few minutes; "
                                                    "the first run also downloads the model)…")
                lines, lang = transcribe(audio, language)
            finally:
                _lock.release()
            if not lines:
                raise RuntimeError("No singing found to transcribe.")
            save(sid, {"source": "whisper", "language": lang, "lines": lines})
            _job(sid, status="done", message=f"Transcribed ({lang}). Check the words — speech-to-text on songs is rough.")
        else:
            raise RuntimeError("Unknown lyrics source")
    except Exception as e:
        log.exception("lyrics %s failed", sid)
        _job(sid, status="error", message=str(e)[:400])


def start(sid, source, query="", language=""):
    j = job(sid)
    if j and j.get("status") == "running":
        return False
    _job(sid, status="running", message="Starting…")
    threading.Thread(target=fetch, args=(sid, source, query, language), daemon=True).start()
    return True


def reset_stale_jobs():
    """A restart kills running threads; don't leave songs stuck on 'running'."""
    root = os.path.join(db.DATA_DIR, "songs")
    if not os.path.isdir(root):
        return
    for sid in os.listdir(root):
        j = job(sid)
        if j and j.get("status") == "running":
            _job(sid, status="error", message="Interrupted by a server restart — try again.")


# ---------- Malayalam → Manglish (roman letters, the way people text it) ----------

_V = {"അ": "a", "ആ": "aa", "ഇ": "i", "ഈ": "ee", "ഉ": "u", "ഊ": "oo", "ഋ": "ru", "എ": "e", "ഏ": "e",
      "ഐ": "ai", "ഒ": "o", "ഓ": "o", "ഔ": "au"}
_S = {"ാ": "aa", "ി": "i", "ീ": "ee", "ു": "u", "ൂ": "oo", "ൃ": "ru", "െ": "e", "േ": "e", "ൈ": "ai",
      "ൊ": "o", "ോ": "o", "ൌ": "au", "ൗ": "au"}
_C = {"ക": "k", "ഖ": "kh", "ഗ": "g", "ഘ": "gh", "ങ": "ng", "ച": "ch", "ഛ": "chh", "ജ": "j", "ഝ": "jh",
      "ഞ": "nj", "ട": "t", "ഠ": "th", "ഡ": "d", "ഢ": "dh", "ണ": "n", "ത": "th", "ഥ": "th", "ദ": "d",
      "ധ": "dh", "ന": "n", "പ": "p", "ഫ": "ph", "ബ": "b", "ഭ": "bh", "മ": "m", "യ": "y", "ര": "r",
      "ല": "l", "വ": "v", "ശ": "sh", "ഷ": "sh", "സ": "s", "ഹ": "h", "ള": "l", "ഴ": "zh", "റ": "r"}
_CHILLU = {"ൻ": "n", "ൽ": "l", "ർ": "r", "ൾ": "l", "ൺ": "n", "ൿ": "k", "ം": "m", "ഃ": "h"}
_PAIRS = {"ന്റ": "nt", "റ്റ": "tt", "ങ്ങ": "ng", "ഞ്ഞ": "nj", "ണ്ട": "nd", "ന്ത": "nth", "ങ്ക": "nk"}
VIRAMA = "്"


def manglish(text):
    out, i, n = [], 0, len(text)
    while i < n:
        three = text[i:i + 3]
        if three in _PAIRS:
            out.append(_PAIRS[three]); i += 3
            base = True
        elif text[i] in _C:
            out.append(_C[text[i]]); i += 1
            base = True
        else:
            base = False
            ch = text[i]
            out.append(_V.get(ch) or _CHILLU.get(ch) or ch); i += 1
        if base:  # consonant: vowel sign, virama, or inherent "a"
            nxt = text[i] if i < n else ""
            if nxt in _S:
                out.append(_S[nxt]); i += 1
            elif nxt == VIRAMA:
                i += 1
                after = text[i] if i < n else ""
                if not after or not ("ഀ" <= after <= "ൿ"):
                    out.append("u")  # word-final ് is a short "u" sound
            else:
                out.append("a")
    return "".join(out)


def has_malayalam(text):
    return any("ഀ" <= c <= "ൿ" for c in text or "")
