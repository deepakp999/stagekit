"""Key and tempo estimates. These are suggestions; the song card always lets the player override them."""
import re

import numpy as np

# Krumhansl-Schmuckler key profiles
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def estimate_key(y, sr):
    import librosa
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    best, scores = None, []
    for i in range(12):
        for mode, prof in (("major", _MAJOR), ("minor", _MINOR)):
            r = np.corrcoef(chroma, np.roll(prof, i))[0, 1]
            scores.append((r, f"{_NAMES[i]} {mode}"))
    scores.sort(reverse=True)
    best_r, best = scores[0]
    second_r = scores[1][0]
    # confidence: margin between best and runner-up, scaled to 0..1
    conf = float(max(0.0, min(1.0, (best_r - second_r) * 10)))
    return best, conf, [s[1] for s in scores[1:3]]


def estimate_tempo(y, sr):
    import librosa
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])
    # Half/double-time alternatives for the player to choose from.
    alts = sorted({round(tempo / 2, 1), round(tempo * 2, 1)})
    return round(tempo, 1), alts


_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _chord_templates():
    """24 triads (12 major, 12 minor) plus a 'no chord' state."""
    names, temps = [], []
    for root in range(12):
        for qual, ivs in (("", (0, 4, 7)), ("m", (0, 3, 7))):
            t = np.zeros(12)
            for iv in ivs:
                t[(root + iv) % 12] = 1.0
            t[root] += 0.5  # root a little stronger than third and fifth
            names.append(_SHARP[root] + qual)
            temps.append(t / np.linalg.norm(t))
    names.append("N.C.")
    temps.append(np.ones(12) / np.sqrt(12))
    return names, np.array(temps)


def detect_chords(path, max_seconds=900):
    """Approximate chord timeline: list of {"t": start_s, "d": duration_s, "c": "Am"}.

    Beat-synchronous chroma from the harmonic part of the audio, matched to
    major/minor triad templates, smoothed with a Viterbi pass so chords don't
    flicker. Good for playable first drafts; 7ths, sus and slash chords are
    reported as their nearest triad.
    """
    import librosa

    sr = 22050
    hop = 512
    y, _ = librosa.load(path, sr=sr, mono=True, duration=max_seconds)
    if len(y) < sr:
        return []
    y_harm = librosa.effects.harmonic(y, margin=4)
    chroma = librosa.feature.chroma_cqt(y=y_harm, sr=sr, hop_length=hop, bins_per_octave=36)
    # Bass chroma (low register) helps pick the right root.
    bass = librosa.feature.chroma_cqt(y=y_harm, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("C1"),
                                      n_octaves=3, bins_per_octave=36)

    _, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop)
    beats = np.unique(np.concatenate([[0], beats, [chroma.shape[1]]])).astype(int)
    c_sync = librosa.util.sync(chroma, beats, aggregate=np.median)
    b_sync = librosa.util.sync(bass, beats, aggregate=np.median)
    feat = c_sync + 0.35 * b_sync
    energy = feat.sum(axis=0)
    feat = feat / (np.linalg.norm(feat, axis=0, keepdims=True) + 1e-9)

    names, temps = _chord_templates()
    sim = temps @ feat                       # (25, beats)
    quiet = energy < (0.05 * np.median(energy) + 1e-9)
    sim[-1] = np.where(quiet, 1.0, 0.55)    # 'no chord' wins only in near-silence
    prob = np.exp(sim * 12)
    prob /= prob.sum(axis=0, keepdims=True)
    trans = librosa.sequence.transition_loop(len(names), 0.8)
    path_ = librosa.sequence.viterbi_discriminative(prob, trans)

    times = librosa.frames_to_time(beats, sr=sr, hop_length=hop)
    out = []
    for i, s in enumerate(path_):
        t0, t1 = float(times[i]), float(times[i + 1])
        if out and out[-1]["c"] == names[s]:
            out[-1]["d"] = round(t1 - out[-1]["t"], 2)
        else:
            out.append({"t": round(t0, 2), "d": round(t1 - t0, 2), "c": names[s]})
    # Fold blips shorter than ~half a second into the previous chord.
    clean = []
    for seg in out:
        if clean and seg["d"] < 0.45:
            clean[-1]["d"] = round(clean[-1]["d"] + seg["d"], 2)
            continue
        if clean and clean[-1]["c"] == seg["c"]:
            clean[-1]["d"] = round(clean[-1]["d"] + seg["d"], 2)
            continue
        clean.append(seg)
    return clean


def analyse(path, drums_path=None):
    """Returns a dict of suggestions. Uses the drum stem for tempo when available."""
    import librosa
    y, sr = librosa.load(path, sr=22050, mono=True, duration=240)
    key, kconf, kalts = estimate_key(y, sr)
    tempo_src = y
    if drums_path:
        try:
            tempo_src, _ = librosa.load(drums_path, sr=22050, mono=True, duration=240)
        except Exception:
            pass
    bpm, balts = estimate_tempo(tempo_src, sr)
    return {
        "key": key,
        "key_confidence": round(kconf, 2),
        "key_alternatives": kalts,
        "bpm": bpm,
        "bpm_alternatives": balts,
    }


def add_slash_bass(chords, bass_path):
    """Mark bass movement from the bass stem: a chord whose bass note isn't its root becomes a slash
    chord ("C" over B -> "C/B"), when the bass is clear and the note is a chord tone or a common
    passing note. Returns a new list; chords without a clear bass stay as they are."""
    import librosa

    sr, hop = 11025, 256
    y, _ = librosa.load(bass_path, sr=sr, mono=True, duration=900)
    if len(y) < sr:
        return chords
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("C1"), n_octaves=3, bins_per_octave=36)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop)
    loud = np.percentile(rms, 60) * 0.5
    out = []
    for seg in chords:
        name = seg["c"]
        m = re.match(r"^([A-G]#?)(m?)$", name)
        if not m:
            out.append(seg)
            continue
        sel = (times >= seg["t"]) & (times < seg["t"] + seg["d"])
        sel &= rms[: len(times)] > loud
        if sel.sum() < 4:
            out.append(seg)
            continue
        prof = np.median(chroma[:, sel], axis=1)
        pc = int(np.argmax(prof))
        strength = prof[pc] / (prof.sum() + 1e-9)
        root = _SHARP.index(m.group(1))
        iv = (pc - root) % 12
        allowed = {3, 7, 10, 11, 2, 9} | ({4} if not m.group(2) else set())
        if strength > 0.22 and iv != 0 and iv in allowed:
            out.append({**seg, "c": f"{name}/{_SHARP[pc]}"})
        else:
            out.append(seg)
    return out
