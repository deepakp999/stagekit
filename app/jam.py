"""Jam mode: build a MODX setup from a genre (or a description, or at random) with a chord progression,
so the band can run on its own while you play lead.

Everything comes from the MODX itself: grooves are the MODX's own arpeggio patterns, sounds are factory
Performances. Electronic genres are assembled per instrument (the MODX names those patterns per instrument,
e.g. "Trap Sub Bass 3", "TropicalHouse1 EP"); band genres reuse the band moods.
"""
import random
import re
from collections import defaultdict

from . import modx

# ---------------------------------------------------------------- genres

# match: regex on the pattern name; sub: the Data List sub category. pools: Performance numbers per role
# (drums, perc, bass, pluck (Part "gtr" slot), chords (Part "keys" slot), wide (held), pad (held), lead).
ELECTRONIC = {
    "trance": {"label": "Trance", "bpm": 138, "match": r"trance", "sub": None, "prog": "epic",
               "pools": {"drums": [2779, 1239], "perc": [2449], "bass": [455, 2543], "gtr": [1033, 1039, 1075],
                         "keys": [1056, 1051], "strings": [481, 482], "pad": [2117, 773], "lead": [645, 694, 689]}},
    "edm": {"label": "EDM / Big room", "bpm": 128, "match": r"\bedm\b|big ?room", "sub": None, "prog": "epic",
            "pools": {"drums": [1239, 1230, 1248], "perc": [2449], "bass": [2543, 1821], "gtr": [1000, 1056, 1033],
                      "keys": [1051, 1049], "strings": [481], "pad": [778, 2117], "lead": [645, 689, 667]}},
    "house": {"label": "House", "bpm": 124, "match": r"house|garage", "sub": "House", "prog": "jazzy",
              "pools": {"drums": [1240, 1241, 1250], "perc": [2449, 2807], "bass": [1822, 2543], "gtr": [1051, 1049, 1075],
                        "keys": [90, 123, 130], "strings": [482], "pad": [778, 2117], "lead": [3, 123, 653]}},
    "tropical": {"label": "Tropical house", "bpm": 108, "match": r"tropical", "sub": None, "prog": "pop", "fallback": "house",
                 "pools": {"drums": [1238, 1250], "perc": [2449], "bass": [1822], "gtr": [1044, 1041, 1037],
                           "keys": [3, 123], "strings": [493], "pad": [2117, 778], "lead": [1044, 2010, 645]}},
    "techno": {"label": "Techno", "bpm": 128, "match": r"techno|offbeat|break bass|synth bass6", "sub": "Techno", "prog": "dark",
               "pools": {"drums": [1240, 1241, 1243], "perc": [2449], "bass": [1822, 427], "gtr": [1065, 1018, 1079],
                         "keys": [1049], "strings": [481], "pad": [771, 773], "lead": [663, 667, 701]}},
    "hiphop": {"label": "Hip hop", "bpm": 90, "match": r"hip ?hop|boom|tricky|fatty|sweetness", "sub": "Hip Hop", "prog": "soul",
               "pools": {"drums": [2770, 2768, 1232], "perc": [2449], "bass": [2543, 1822], "gtr": [1037, 1044],
                         "keys": [90, 130, 123], "strings": [486, 493], "pad": [778, 2117], "lead": [123, 653, 2010]}},
    "trap": {"label": "Trap", "bpm": 140, "match": r"trap|808", "sub": None, "prog": "dark",
             "pools": {"drums": [1287, 1289, 1234], "perc": [2449], "bass": [2543, 1822], "gtr": [1044, 1037],
                       "keys": [130, 3], "strings": [486], "pad": [771, 773], "lead": [653, 701, 2010]}},
    "dubstep": {"label": "Dubstep / bass", "bpm": 140, "match": r"dubstep|drumstep|wobble|big step|dubtastic", "sub": None, "prog": "dark",
                "pools": {"drums": [1230, 1231, 1239], "perc": [2449], "bass": [1796, 744, 2097], "gtr": [1065, 1000],
                          "keys": [1049], "strings": [481], "pad": [771, 773], "lead": [701, 716, 667]}},
    "dnb": {"label": "Drum & bass", "bpm": 172, "match": r"d&b|dnb|jungle|liquid", "sub": "D&B", "prog": "epic",
            "pools": {"drums": [1230, 1243, 1239], "perc": [2449], "bass": [1822, 427], "gtr": [1033, 1075],
                      "keys": [123, 1049], "strings": [482], "pad": [2117, 773], "lead": [645, 663]}},
    "chill": {"label": "Chill / lo-fi", "bpm": 84, "match": r"chill|lofi|lo-fi|vintage chill", "sub": "Chill", "prog": "jazzy",
              "pools": {"drums": [1237, 2781, 1238], "perc": [2449], "bass": [2537, 1822], "gtr": [1044, 1037],
                        "keys": [90, 108, 26], "strings": [486], "pad": [2117, 784], "lead": [90, 2010, 26]}},
    "reggaeton": {"label": "Reggaeton / Afro", "bpm": 95, "match": r"reggaeton|afro|dembow", "sub": None, "prog": "latin",
                  "pools": {"drums": [1232, 2770], "perc": [2808, 2807], "bass": [2543], "gtr": [1044, 1037],
                            "keys": [123, 130], "strings": [482], "pad": [778], "lead": [1044, 653, 2010]}},
    "futurebass": {"label": "Future bass", "bpm": 150, "match": r"future", "sub": None, "prog": "pop", "fallback": "edm",
                   "pools": {"drums": [1239, 1230], "perc": [2449], "bass": [2543], "gtr": [1000, 1056],
                             "keys": [123], "strings": [481], "pad": [2117, 778], "lead": [645, 1044]}},
    "disco": {"label": "Disco / funk", "bpm": 118, "match": r"disco|funk", "sub": None, "prog": "jazzy",
              "pools": {"drums": [1285, 1218], "perc": [2807], "bass": [2538, 1760], "gtr": [334, 332],
                        "keys": [90, 108], "strings": [493, 492], "pad": [2594], "lead": [645, 90]}},
}
# Band genres reuse the band moods (MODX band grooves + mood sounds).
BAND_GENRES = {"unplugged": "pop", "band": "pop", "devotional": "pop", "cinematic": "epic", "retro": "pop", "indian": "pop"}

EDM_SCENES = ["Intro", "Groove", "Build-up", "Drop", "Riser", "Fill", "Breakdown", "Outro"]
BAND_SCENES = ["Intro", "Verse", "Pre-chorus", "Chorus", "Fill A", "Fill B", "Break", "Ending"]

ROLE_CATS = {"drums": ["Dr/Pc"], "perc": ["Dr/Pc", "CPerc"], "bass": ["Bass"], "gtr": ["SynCp", "Gtr"],
             "keys": ["Keys", "Piano", "SynCp"]}
# Guitar for electronic genres (replaces the percussion Part): preferred strum/pattern style and sounds.
GENRE_GUITAR = {
    "tropical": ("muted", [2529, 1665]), "reggaeton": ("muted", [2529, 1665]), "chill": ("finger", [2529, 333]),
    "house": ("funk", [332, 331]), "disco": ("funk", [332, 334]), "hiphop": ("clean", [333, 2529]),
    "futurebass": ("clean", [333]), "edm": ("strum", [317, 323]), "trance": ("finger", [333, 316]),
    "trap": ("finger", [2529, 333]), "techno": ("muted", [332]), "dnb": ("clean", [333]), "dubstep": ("rock", [2532]),
}
GUITAR_DEFAULT_ON = {"tropical", "reggaeton", "chill", "house", "disco", "hiphop"}

ROLE_LABELS = {"drums": "Drums", "perc": "Percussion", "bass": "Bass", "gtr": "Pluck / stab", "keys": "Chords",
               "strings": "Wide synth", "pad": "Pad"}

_FAMILIES = None


def _families():
    """{(cat, family): [arps]} for every prefixed MODX pattern in 4/4."""
    global _FAMILIES
    if _FAMILIES is None:
        fam = defaultdict(list)
        for a in modx.ARPS:
            m = modx._NAME_RX.match(a["name"])
            if not m or a.get("ts") != "4/4":
                continue
            fam[(a["cat"], m.group(4).strip())].append({**a, "var": m.group(2), "n": m.group(3) or ""})
        _FAMILIES = dict(fam)
    return _FAMILIES


def _genre_match(g, a, family):
    rx = re.compile(g["match"], re.I)
    return bool(rx.search(family) or rx.search(a["name"])) or (g["sub"] and a.get("sub") == g["sub"])


def _candidates(genre, role, bpm):
    g = ELECTRONIC[genre]
    out = []
    for (cat, family), arps in _families().items():
        if cat not in ROLE_CATS[role]:
            continue
        if not _genre_match(g, arps[0], family):
            continue
        perc_like = bool(modx.PERC_RX.search(arps[0].get("sound") or "")) or cat == "CPerc"
        if role == "drums" and perc_like or role == "perc" and not perc_like:
            continue
        variety = len({a["var"] for a in arps if a["var"] in ("MA", "MB", "MC", "MD", "FA", "FB", "FC", "IA", "EA", "BA")})
        out.append((family, arps, variety, abs(arps[0]["tempo"] - bpm)))
    # More variations first (so scenes differ), then nearest tempo.
    out.sort(key=lambda x: (-min(x[2], 6), x[3]))
    return out


def _genre_guitar(genre, bpm, rng):
    style, pool = GENRE_GUITAR.get(genre, ("clean", [333]))
    opts = modx.pattern_options("gtr", "4/4", bpm)
    group = next((g for g in opts["groups"] if g["id"] == style), None) or (opts["groups"][0] if opts["groups"] else None)
    if not group or not group["options"]:
        return None
    rx = re.compile(ELECTRONIC[genre]["match"], re.I) if genre in ELECTRONIC else None
    own = [o for g in opts["groups"] for o in g["options"] if rx and rx.search(o["family"])]
    pick_from = own or group["options"][:4]
    o = (rng.choice(pick_from) if rng else pick_from[0])
    if own:
        group = next(g for g in opts["groups"] if o in g["options"])
    no = rng.choice(pool) if rng else pool[0]
    p = modx._PERF_BY_NO.get(no)
    return {"role": "gtr2", "label": "Guitar", "cat": "gtr2", "hold": False, "from": o["family"], "family": o["family"],
            "pattern_style": group["label"], "scenes": o["scenes"], "sound_no": p["no"] if p else None,
            "sound_name": p["name"] if p else None, "why": "",
            "options": [{"no": n, "name": modx._PERF_BY_NO[n]["name"]} for n in [2529, 1665, 316, 317, 333, 331, 332, 334] if n in modx._PERF_BY_NO]}


def electronic_plan(genre, bpm=None, rng=None, sounds=None, guitar=None):
    g = ELECTRONIC[genre]
    bpm = bpm or g["bpm"]
    rng = rng or random.Random()
    sounds = sounds or {}
    parts = []
    used = set()
    guitar = genre in GUITAR_DEFAULT_ON if guitar is None else guitar
    for role in ("drums", "perc", "bass", "gtr", "keys", "strings", "pad"):
        if role == "perc" and guitar:
            g_row = _genre_guitar(genre, bpm, rng)
            if g_row:
                parts.append(g_row)
                continue
        row = {"role": role, "label": ROLE_LABELS[role], "cat": role, "scenes": [None] * 8, "hold": role in ("strings", "pad"), "from": None}
        if not row["hold"]:
            cands = [c for c in _candidates(genre, role, bpm) if c[0] not in used]
            if not cands and g.get("fallback", "edm" if genre != "edm" else None):
                cands = [c for c in _candidates(g.get("fallback", "edm"), role, bpm) if c[0] not in used]
            if not cands:
                continue
            top = cands[: 4 if rng else 1]
            family, arps, _, _ = rng.choice(top) if rng else top[0]
            used.add(family)
            row["from"] = family
            row["family"] = family
            if role == "bass":
                row["pattern_style"] = modx.pattern_style("Bass", family, arps)[1]
            row["scenes"] = [{"no": a["no"], "name": a["name"], "var": a["var"]} if a else None for a in modx._scene_arps(arps)]
        pool = g["pools"].get(role, [])
        choice = sounds.get(role)
        no = choice if choice in modx._PERF_BY_NO else (rng.choice(pool) if (rng and pool) else (pool[0] if pool else None))
        p = modx._PERF_BY_NO.get(no)
        row["sound_no"], row["sound_name"], row["why"] = (p["no"], p["name"], "") if p else (None, None, "")
        row["options"] = [{"no": n, "name": modx._PERF_BY_NO[n]["name"]} for n in pool if n in modx._PERF_BY_NO]
        parts.append(row)
    leads = [{"no": n, "name": modx._PERF_BY_NO[n]["name"]} for n in g["pools"].get("lead", []) if n in modx._PERF_BY_NO]
    fx = {"reverb": [0x01, 0x21], "reverb_name": "HD Plate", "variation": [0x02, 0x28], "variation_name": "Tempo Delay Stereo", "lead_var": 30}
    if genre in ("chill", "hiphop", "trap"):
        fx = {**fx, "reverb": [0x01, 0x13], "reverb_name": "HD Room", "lead_var": 22}
    return {"family": g["label"], "ts": "4/4", "tempo": bpm, "flavor": genre, "flavor_label": g["label"], "band": True, "guitar": guitar,
            "edm": True, "scenes": EDM_SCENES, "parts": parts, "lead": leads[0] if leads else None, "leads": leads, "fx": fx}


# ---------------------------------------------------------------- chord progressions

NOTES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]
# Roman numerals per family: uppercase = major chord, lowercase = minor; "7"/"maj7" kept as written.
PROGS = {
    "epic": {"mode": "minor", "sets": [["i", "VI", "III", "VII"], ["i", "VII", "VI", "VII"], ["VI", "VII", "i", "i"], ["i", "iv", "VI", "V"], ["VI", "III", "VII", "i"]]},
    "dark": {"mode": "minor", "sets": [["i", "VI"], ["i", "iv"], ["i", "VII", "VI", "V"], ["i", "i", "VI", "VII"], ["i", "iv", "i", "V"]]},
    "pop": {"mode": "major", "sets": [["I", "V", "vi", "IV"], ["vi", "IV", "I", "V"], ["I", "vi", "IV", "V"], ["IV", "I", "V", "vi"], ["I", "IV", "vi", "V"]]},
    "jazzy": {"mode": "major", "sets": [["ii7", "V7", "Imaj7", "vi7"], ["Imaj7", "vi7", "ii7", "V7"], ["iii7", "vi7", "ii7", "V7"], ["Imaj7", "IVmaj7", "iii7", "vi7"]]},
    "soul": {"mode": "minor", "sets": [["i7", "iv7"], ["i7", "VImaj7", "iv7", "v7"], ["VImaj7", "v7", "i7", "i7"], ["i7", "VII", "VImaj7", "v7"]]},
    "latin": {"mode": "minor", "sets": [["i", "VI", "III", "VII"], ["i", "iv", "VII", "III"], ["i", "VII", "VI", "VII"]]},
}
KEYS = {"minor": ["A", "E", "D", "B", "F#", "C", "G"], "major": ["C", "G", "D", "F", "A", "E", "Bb"]}
ROMAN = {"i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6}


def roman_to_chord(r, key, mode):
    m = re.match(r"^(b?)(VII|VI|V|IV|III|II|I|vii|vi|v|iv|iii|ii|i)(maj7|7)?$", r)
    if not m:
        return r
    flat, num, ext = m.groups()
    scale = MAJOR if mode == "major" else MINOR
    root = (NOTES.index(key) + scale[ROMAN[num.lower()]] - (1 if flat else 0)) % 12
    quality = "" if num.isupper() else "m"
    if ext == "maj7":
        name = NOTES[root] + ("maj7" if num.isupper() else "m7")
    elif ext == "7":
        name = NOTES[root] + ("7" if num.isupper() else "m7")
    else:
        name = NOTES[root] + quality
    return name


def progression(style, key=None, rng=None):
    rng = rng or random.Random()
    fam = PROGS.get(style, PROGS["pop"])
    mode = fam["mode"]
    key = key or rng.choice(KEYS[mode])
    a, b = rng.sample(fam["sets"], 2)
    A = [roman_to_chord(r, key, mode) for r in a]
    B = [roman_to_chord(r, key, mode) for r in b]
    # Per scene: intro/outro on the first chords, build-up on progression B, drop/chorus on A, breakdown on B.
    sections = [A[:2], A, B, A, A, A, B, A[:1]]
    return {"key": key + ("m" if mode == "minor" else ""), "mode": mode, "sections": sections, "roman": [a, b]}


# ---------------------------------------------------------------- shuffle

def all_genres():
    g = [{"id": k, "label": v["label"], "bpm": v["bpm"], "kind": "electronic"} for k, v in ELECTRONIC.items()]
    g += [{"id": k, "label": modx.BAND_LABELS[k], "bpm": None, "kind": "band"} for k in modx.BAND_POOLS]
    return g


def build(genre, bpm=None, key=None, seed=None, sounds=None, prog_style=None, randomize=True, guitar=None):
    rng = random.Random(seed) if randomize else None
    prng = random.Random(seed)
    if genre in ELECTRONIC:
        plan = electronic_plan(genre, bpm, rng, sounds, guitar)
        style = prog_style or ELECTRONIC[genre]["prog"]
    else:
        fams = [f for f, s in modx.STYLES.items() if s["ts"] == "4/4"]
        if bpm:
            fams.sort(key=lambda f: abs(modx.STYLES[f]["tempo"] - bpm))
            fams = fams[:12]
        family = (rng or prng).choice(fams)
        plan = modx.band_plan(family, genre)
        plan["scenes"] = BAND_SCENES
        bpm = bpm or plan["tempo"]
        plan["tempo"] = bpm
        style = prog_style or BAND_GENRES.get(genre, "pop")
    plan["progression"] = progression(style, key, prng)
    plan["bpm"] = bpm or plan["tempo"]
    return plan


def shuffle(genre=None, seed=None, guitar=None):
    seed = seed if seed is not None else random.randrange(1 << 30)
    rng = random.Random(seed)
    if not genre or genre == "any":
        genre = rng.choice(list(ELECTRONIC) + list(modx.BAND_POOLS))
    g = ELECTRONIC.get(genre)
    bpm = round((g["bpm"] if g else rng.choice([76, 84, 92, 100, 110, 120])) * rng.uniform(0.96, 1.04))
    plan = build(genre, bpm=bpm, seed=seed, guitar=guitar)
    plan["seed"] = seed
    return plan
