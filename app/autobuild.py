"""Auto-build: listen to a song and propose a complete MODX setup.

1. Groove analysis on the drum stem (or the percussive part of the mix):
   how busy the drums are, straight vs swung, 8th vs 16th feel, syncopation.
2. Section detection: structural segments of the song, labelled Intro / Verse /
   Chorus / Bridge / Break / Ending by repetition and loudness, mapped to scenes.
3. Style matching: scores the 172 MODX groove styles against meter, tempo,
   groove and the chosen feel, and returns the best few with reasons.

Everything is a suggestion the player can change before sending to the MODX.
"""
import json
import math
import os
import re

import numpy as np

from . import modx

SR = 22050
HOP = 512

# Scene layout shared with the scene builder: 1 Intro, 2–4 mains (light → full), 5–6 fills, 7 break, 8 ending.
SECTION_SCENE = {"Intro": 1, "Verse": 2, "Pre-chorus": 3, "Chorus": 4, "Bridge": 3, "Interlude": 2,
                 "Break": 7, "Ending": 8}


# ---------------------------------------------------------------- groove

def groove_features(path, bpm_hint=None):
    """Drum-feel descriptors from a drum stem (or full mix, using its percussive part)."""
    import librosa

    y, _ = librosa.load(path, sr=SR, mono=True, duration=300)
    if len(y) < SR * 5:
        return None
    if not os.path.basename(path).startswith("drums"):
        y = librosa.effects.percussive(y, margin=3)
    onset_env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=SR, hop_length=HOP,
                                           start_bpm=bpm_hint or 110)
    tempo = float(np.atleast_1d(tempo)[0])
    beat_t = librosa.frames_to_time(beats, sr=SR, hop_length=HOP)
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=SR, hop_length=HOP, units="time",
                                        backtrack=False)
    if len(beat_t) < 8 or len(onsets) < 8:
        return None
    on_strength = np.interp(librosa.time_to_frames(onsets, sr=SR, hop_length=HOP),
                            np.arange(len(onset_env)), onset_env)

    # Position of every onset inside its beat (0 = on the beat, 0.5 = straight 8th, ~0.67 = swung 8th).
    phases, weights = [], []
    for t, w in zip(onsets, on_strength):
        i = np.searchsorted(beat_t, t) - 1
        if i < 0 or i + 1 >= len(beat_t):
            continue
        span = beat_t[i + 1] - beat_t[i]
        if span <= 0:
            continue
        phases.append((t - beat_t[i]) / span)
        weights.append(w)
    phases, weights = np.array(phases), np.array(weights)
    total = weights.sum() + 1e-9

    def mass(lo, hi):
        return float(weights[(phases >= lo) & (phases < hi)].sum() / total)

    on_beat = mass(0.0, 0.12) + mass(0.9, 1.0)
    straight8 = mass(0.42, 0.58)
    swing8 = mass(0.6, 0.74)
    sixteenth = mass(0.18, 0.32) + mass(0.68, 0.82) - 0.5 * swing8  # 0.75 overlaps the swing zone a little
    swing = swing8 / (swing8 + straight8 + 1e-9)

    duration = beat_t[-1] - beat_t[0]
    density = len(phases) / max(1, len(beat_t) - 1)            # onsets per beat
    syncopation = 1 - on_beat                                   # share of drum energy off the beat
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    loud = float(np.percentile(rms, 90))

    feel = "swung" if swing > 0.5 else "straight"
    subdivision = "16th" if sixteenth > 0.18 and density > 2.4 else "8th" if density > 1.2 else "quarter"
    busy = "sparse" if density < 1.4 else "busy" if density > 3.0 else "medium"
    return {
        "tempo": round(tempo, 1), "density": round(density, 2), "swing": round(swing, 2),
        "sixteenth": round(max(0.0, sixteenth), 2), "syncopation": round(syncopation, 2),
        "loudness": round(loud, 4), "feel": feel, "subdivision": subdivision, "busy": busy,
        "seconds": round(float(duration), 1),
    }


# ---------------------------------------------------------------- sections

def detect_sections(path, chords=None, meter="4/4", max_sections=14):
    """Split the song into sections and label them. Returns [{name, start, end, scene, energy, chords, cue}].

    Boundaries come from a novelty curve over a beat-synchronous self-similarity matrix (a 3-bar
    checkerboard kernel); sections that sound alike are grouped, the loudest repeated group is the
    chorus, the most frequent other repeated group is the verse.
    """
    import librosa

    y, _ = librosa.load(path, sr=SR, mono=True, duration=600)
    dur = len(y) / SR
    if dur < 30:
        return []
    _, beats = librosa.beat.beat_track(y=y, sr=SR, hop_length=HOP)
    if len(beats) < 16:
        return []
    beats = _full_grid(beats, len(y))
    per_bar = int(str(meter).split("/")[0]) if str(meter).split("/")[0].isdigit() else 4
    per_bar = {6: 3, 12: 6}.get(per_bar, per_bar) if str(meter).endswith("/8") else per_bar
    chroma = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP)
    mfcc = librosa.feature.mfcc(y=y, sr=SR, hop_length=HOP, n_mfcc=13)
    rms_db = librosa.amplitude_to_db(librosa.feature.rms(y=y, hop_length=HOP))

    def z(m):
        return (m - m.mean(1, keepdims=True)) / (m.std(1, keepdims=True) + 1e-9)

    feat = np.vstack([z(chroma) / np.sqrt(12), z(mfcc) / np.sqrt(13), z(rms_db)])
    sync = librosa.util.sync(feat, beats, aggregate=np.mean)
    loud = librosa.util.sync(rms_db, beats, aggregate=np.mean)[0]
    times = librosa.frames_to_time(np.concatenate([[0], beats]), sr=SR, hop_length=HOP)
    n = sync.shape[1]

    L = max(6, 3 * per_bar)
    S = np.nan_to_num(np.corrcoef(sync.T))
    kern = np.ones((2 * L, 2 * L))
    kern[:L, L:] = -1
    kern[L:, :L] = -1
    kern *= np.outer(np.hanning(2 * L), np.hanning(2 * L))
    P = np.pad(S, L, mode="edge")
    nov = np.array([np.sum(P[i:i + 2 * L, i:i + 2 * L] * kern) for i in range(n)])
    peaks = librosa.util.peak_pick(nov, pre_max=L, post_max=L, pre_avg=L, post_avg=L,
                                   delta=float(np.std(nov)) * 0.3, wait=L)
    peaks = sorted(peaks, key=lambda i: -nov[i])[:max_sections - 1]
    bounds = sorted(set([0] + [int(i) for i in peaks] + [n]))

    # Absorb slivers (< ~4 s) into the next section.
    beat_len = float(np.median(np.diff(times[1:]))) if len(times) > 2 else 0.5
    min_beats = max(2, int(round(4.0 / max(beat_len, 1e-3))))
    clean = [bounds[0]]
    for bnd in bounds[1:-1]:
        if bnd - clean[-1] >= min_beats:
            clean.append(bnd)
    if n - clean[-1] < min_beats and len(clean) > 1:
        clean.pop()
    bounds = clean + [n]

    segs = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        v = np.mean(sync[:25, a:b], axis=1)   # harmony + timbre only; loudness is judged separately
        segs.append({"start": float(times[min(a, len(times) - 1)]), "end": float(times[min(b, len(times) - 1)]),
                     "loud": float(np.mean(loud[a:b])), "vec": v / (np.linalg.norm(v) + 1e-9)})
    if len(segs) < 2:
        return []
    segs[0]["start"] = 0.0
    segs[-1]["end"] = dur

    # Group repeats: greedy clustering on the section fingerprints.
    centers, groups = [], []
    for s in segs:
        sims = [float(s["vec"] @ c) for c in centers]
        if sims and max(sims) > 0.6:
            groups.append(int(np.argmax(sims)))
        else:
            centers.append(s["vec"])
            groups.append(len(centers) - 1)
    e = np.array([s["loud"] for s in segs])
    e_norm = (e - e.min()) / (e.max() - e.min() + 1e-9)
    gset = set(groups)
    g_energy = {g: float(np.mean([e_norm[i] for i in range(len(segs)) if groups[i] == g])) for g in gset}
    g_count = {g: groups.count(g) for g in gset}
    last_i = len(segs) - 1
    inner_count = {g: sum(1 for i in range(1, last_i) if groups[i] == g) for g in gset}
    inner = [g for g in gset if inner_count[g] > 0]
    repeated = [g for g in inner if inner_count[g] > 1] or inner or list(gset)
    chorus_g = max(repeated, key=lambda g: (g_energy[g], inner_count[g]))
    verse_pool = [g for g in repeated if g != chorus_g]
    first_pos = {g: min(i for i in range(len(segs)) if groups[i] == g and 0 < i < last_i) for g in inner}
    verse_g = max(verse_pool, key=lambda g: (inner_count[g], -first_pos[g])) if verse_pool else None

    out = []
    last = len(segs) - 1
    for i, s in enumerate(segs):
        g, en, length = groups[i], e_norm[i], s["end"] - s["start"]
        if i == 0 and g != chorus_g and (en < 0.5 or length < 20):
            name = "Intro"
        elif i == last and g != chorus_g and (en < 0.6 or length < 20):
            name = "Ending"
        elif g == chorus_g:
            name = "Chorus"
        elif g == verse_g:
            name = "Verse"
        elif en < 0.15 and 0 < i < last:
            name = "Break"
        else:
            name = "Bridge"
        out.append({"name": name, "start": round(s["start"], 1), "end": round(s["end"], 1),
                    "energy": round(float(en), 2)})

    # Short non-chorus part right before a chorus → pre-chorus.
    for i in range(1, len(out) - 1):
        if out[i]["name"] in ("Verse", "Bridge") and out[i + 1]["name"] == "Chorus" and \
                out[i]["end"] - out[i]["start"] < 14 and out[i - 1]["name"] == "Verse":
            out[i]["name"] = "Pre-chorus"

    counts = {}
    for s in out:
        counts[s["name"]] = counts.get(s["name"], 0) + 1
    seen = {}
    for i, s in enumerate(out):
        base = s["name"]
        seen[base] = seen.get(base, 0) + 1
        if counts[base] > 1 and base not in ("Intro", "Ending"):
            s["name"] = f"{base} {seen[base]}"
        s["scene"] = SECTION_SCENE.get(base, 2)
        s["chords"] = _chords_between(chords or [], s["start"], s["end"])
        nxt = out[i + 1]["name"].split(" ")[0] if i + 1 < len(out) else None
        s["cue"] = ("Fill (S5) into chorus" if nxt == "Chorus" and base != "Chorus"
                    else "Fill (S6) into ending" if nxt == "Ending" else "")
    return out


def _full_grid(beats, n_samples):
    """Extend the tracked beats with a steady grid over quiet intros/endings where tracking drops out."""
    period = float(np.median(np.diff(beats)))
    last_frame = n_samples // HOP
    head = np.arange(beats[0] - period, 0, -period)[::-1]
    tail = np.arange(beats[-1] + period, last_frame, period)
    return np.unique(np.concatenate([head, beats, tail]).round().astype(int))


def _chords_between(chords, t0, t1, limit=16):
    seq = []
    for c in chords:
        if c["t"] + c["d"] <= t0 + 0.2 or c["t"] >= t1 - 0.2 or c["c"] == "N.C.":
            continue
        name = c["c"].replace("A#", "Bb").replace("D#", "Eb").replace("G#", "Ab")
        if not seq or seq[-1] != name:
            seq.append(name)
    return "  ".join(seq[:limit])


# ---------------------------------------------------------------- style matching

_SWUNG = re.compile(r"shuffle|swing|12/8|jazz|blues|hymn|waltz|gospel|6/8", re.I)
_SPARSE = re.compile(r"ballad|unplugged|slow|soft|acoustic|folk|hymn|chill|lounge|bossa", re.I)
_SIXTEEN = re.compile(r"16|funk|r&b|hip|disco|house|dance|latin|samba|groove", re.I)
_EIGHT = re.compile(r"8beat|8 ?beat|rock|pop|country|brit", re.I)
FEEL_SUBS = {
    "ballad": {"Ballad", "Pop Rock", "Chill"}, "pop": {"Pop Rock", "Rock", "Modern R&B"},
    "devotional": {"Ballad", "Pop Rock", "Classic R&B"}, "cinematic": {"Ballad", "Pop Rock", "Chill"},
    "dance": {"House", "Techno", "Hip Hop", "Modern R&B", "Funk"}, "indian": {"World", "Pop Rock", "Ballad"},
}


def match_styles(meter, bpm, groove, feel="", top=5):
    tss = modx.METER_TS.get(meter or "4/4", {"4/4"})
    out = []
    for fam, st in modx.STYLES.items():
        if st["ts"] not in tss:
            continue
        score, why = 0.0, []
        # Tempo: arps follow the MODX tempo, but a groove sounds most natural near its original speed.
        if bpm and st["tempo"]:
            r = abs(math.log2(bpm / st["tempo"]))
            r = min(r, abs(math.log2(bpm * 2 / st["tempo"])) + 0.25, abs(math.log2(bpm / 2 / st["tempo"])) + 0.25)
            score -= r * 3
            if r < 0.12:
                why.append(f"tempo close ({st['tempo']} BPM)")
        name = fam + " " + (st["sub"] or "")
        if groove:
            swung_style = bool(_SWUNG.search(name)) or st["ts"] in ("6/8", "6/4", "12/8")
            if groove["feel"] == "swung" and swung_style:
                score += 1.5; why.append("swung feel")
            elif groove["feel"] == "straight" and swung_style and st["ts"] == "4/4":
                score -= 1.5
            if groove["busy"] == "sparse":
                if _SPARSE.search(name): score += 1.5; why.append("light drums")
                if _SIXTEEN.search(name): score -= 1
            elif groove["busy"] == "busy" or groove["subdivision"] == "16th":
                if _SIXTEEN.search(name): score += 1.5; why.append("16th-note drive")
                if _SPARSE.search(name): score -= 1
            else:
                if _EIGHT.search(name): score += 1.2; why.append("steady 8th feel")
            if groove["syncopation"] > 0.55 and re.search(r"funk|latin|r&b|reggae|hip", name, re.I):
                score += 0.8; why.append("syncopated")
        subs = FEEL_SUBS.get(feel)
        if subs:
            if st["sub"] in subs:
                score += 1.0; why.append(f"{feel} feel")
            else:
                score -= 0.5
        # Prefer complete band sets (drums + bass + guitar/keys).
        parts = set(st["parts"])
        score += 0.3 * len(parts & {"Bass", "Gtr", "Piano", "Keys"})
        out.append({"family": fam, "score": round(score, 2), "ts": st["ts"], "tempo": st["tempo"],
                    "sub": st["sub"], "why": why[:3],
                    "instruments": [modx.INSTR_LABEL.get(c, c) for c in modx.INSTR_ORDER if c in parts]})
    out.sort(key=lambda s: -s["score"])
    return out[:top]


# ---------------------------------------------------------------- one call for the UI

def recommend(song_dir, card, feel=""):
    stems = os.path.join(song_dir, "stems")
    drums = os.path.join(stems, "drums.wav")
    wav = os.path.join(song_dir, "original.wav")
    meter = card.get("meter") or "4/4"
    bpm = card.get("bpm") or (card.get("detected") or {}).get("bpm")
    groove = groove_features(drums if os.path.exists(drums) else wav, bpm)
    try:
        chords = json.load(open(os.path.join(song_dir, "chords.json")))
    except (OSError, ValueError):
        chords = []
    sections = detect_sections(wav, chords, meter)
    styles = match_styles(meter, bpm, groove, feel)
    plan = modx.scene_plan(styles[0]["family"]) if styles else None
    return {"meter": meter, "bpm": bpm, "groove": groove, "feel": feel, "styles": styles,
            "sections": sections, "plan": plan, "used_drum_stem": os.path.exists(drums)}
