"""'Describe it': turn a sentence ("trance DJ mix, euphoric, 138") into a jam plan using an LLM via OpenRouter.

The model only chooses from what the MODX has: a genre from the jam list, sounds from that genre's
MODX sound options, a tempo, a key and chord progressions. StageKit builds the actual plan (grooves,
scenes, layers) itself and checks every value, so a bad answer can't send anything odd to the keyboard.
"""
import json
import os
import re
import urllib.error
import urllib.request

from . import jam, modx

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
CHORD_RX = re.compile(r"^[A-G](#|b)?(m|maj7|m7|7|sus2|sus4|dim|add9|6|m6|9|m9)?(/[A-G](#|b)?)?$")


def enabled():
    return bool(OPENROUTER_KEY)


def _catalog():
    lines = []
    for gid, g in jam.ELECTRONIC.items():
        snd = {r: [f"{n}:{modx._PERF_BY_NO[n]['name']}" for n in pool if n in modx._PERF_BY_NO]
               for r, pool in g["pools"].items()}
        lines.append({"id": gid, "label": g["label"], "default_bpm": g["bpm"], "progression_style": g["prog"], "sounds": snd})
    for gid in modx.BAND_POOLS:
        pools = modx.BAND_POOLS[gid]
        snd = {}
        for r, pool in pools.items():
            lst = pool if isinstance(pool, list) else (pool["strum"] + pool["pick"] if isinstance(pool, dict) else [])
            snd[r] = [f"{n}:{modx._PERF_BY_NO[n]['name']}" for n in lst if n in modx._PERF_BY_NO]
        lines.append({"id": gid, "label": modx.BAND_LABELS[gid], "default_bpm": None,
                      "progression_style": jam.BAND_GENRES.get(gid, "pop"), "sounds": snd})
    return lines


SYSTEM = """You arrange live jams on a Yamaha MODX M6 keyboard. You can ONLY use what is listed in the catalog:
pick one genre id, sounds by their number from that genre's options, a tempo, a key and chord progressions.
The 8 scenes are, in order: Intro, Groove/Verse, Build-up/Pre-chorus, Drop/Chorus, Fill A/Riser, Fill B, Breakdown/Break, Outro/Ending.
Reply with ONLY a JSON object, no other text:
{"genre": "<id>", "bpm": <60-180>, "key": "<A, C#, Eb ...>", "mode": "minor"|"major",
 "sections": [[chords for scene 1], ... 8 lists, 1-4 chords each, e.g. ["Am","F","C","G"]],
 "sounds": {"drums": <number>, "perc": <number>, "bass": <number>, "gtr": <number>, "keys": <number>, "strings": <number>, "pad": <number>},
 "lead": <number from the genre's lead options>, "title": "<short name>", "notes": "<one line on how to play it>"}
Chords: plain names like Am, F#m, Bb, Cmaj7, Dm7, G7, Esus4, C/E. Make the progressions musical and fitting the mood."""


def describe(text):
    if not enabled():
        raise RuntimeError("Add OPENROUTER_API_KEY to the server's .env to use Describe it (Shuffle works without it).")
    body = {"model": OPENROUTER_MODEL, "temperature": 0.8, "max_tokens": 900,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": "Catalog:\n" + json.dumps(_catalog(), ensure_ascii=False)
                          + "\n\nRequest: " + text.strip()[:500]}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json",
                                          "HTTP-Referer": "https://stage.lumivoxx.com", "X-Title": "StageKit"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenRouter error {e.code}: {e.read().decode(errors='ignore')[:200]}")
    content = data["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise RuntimeError("The AI didn't return a plan. Try again or rephrase.")
    return _validated(json.loads(m.group(0)), text)


def _validated(a, text):
    genres = set(jam.ELECTRONIC) | set(modx.BAND_POOLS)
    genre = a.get("genre") if a.get("genre") in genres else "edm"
    try:
        bpm = max(60, min(180, int(round(float(a.get("bpm") or 0)))))
    except (TypeError, ValueError):
        bpm = None
    key = a.get("key") if a.get("key") in jam.NOTES or a.get("key") in ("Db", "D#", "Gb", "G#", "A#") else None
    key = {"Db": "C#", "D#": "Eb", "Gb": "F#", "G#": "Ab", "A#": "Bb"}.get(key, key)
    sounds = {r: n for r, n in (a.get("sounds") or {}).items() if isinstance(n, int) and n in modx._PERF_BY_NO}
    plan = jam.build(genre, bpm=bpm, key=key, sounds=sounds) if genre in jam.ELECTRONIC else jam.build(genre, bpm=bpm, key=key)
    secs = a.get("sections")
    if isinstance(secs, list) and len(secs) >= 8:
        clean = [[c for c in (s if isinstance(s, list) else []) if isinstance(c, str) and CHORD_RX.match(c.strip())][:4] for s in secs[:8]]
        if all(clean):
            plan["progression"]["sections"] = clean
            if key:
                plan["progression"]["key"] = key + ("m" if a.get("mode") == "minor" else "")
    lead = a.get("lead")
    if isinstance(lead, int) and lead in modx._PERF_BY_NO:
        plan["lead"] = {"no": lead, "name": modx._PERF_BY_NO[lead]["name"]}
    plan["title"] = str(a.get("title") or text)[:60]
    plan["notes"] = str(a.get("notes") or "")[:200]
    plan["ai"] = True
    return plan
