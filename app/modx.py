"""MODX M preset data (from Yamaha's MODX M Data List, Jan 2026) and a simple sound finder.

Performances: 3,487 presets with main/sub category.
Arpeggios: 10,922 types with category, meter, length and original tempo.
"""
import json
import os
import re

_DIR = os.path.join(os.path.dirname(__file__), "data")
PERFS = json.load(open(os.path.join(_DIR, "performances.json")))
ARPS = json.load(open(os.path.join(_DIR, "arpeggios.json")))
_PERF_BY_NO = {p["no"]: p for p in PERFS}

# A "feel" maps to Performance categories / name hints and arpeggio categories.
# Hand-written starting points; tune them as you learn which presets you like.
FEELS = {
    "indian": {
        "label": "Indian / ethnic",
        "perf_names": r"tabla|dhol|khol|sitar|tambura|shehnai|harmonium|india|naan|santur|pungi|snake charmer|ethnology",
        "perf_cats": [("Ethnic", None)],
        "arp_cats": [("Ethnc", None), ("Dr/Pc", "World")],
        "arp_exclude": r"reggae|bluegrass|irish|spanish|rumba|japan|berimbau",
    },
    "ballad": {
        "label": "Ballad / melody",
        "perf_cats": [("Piano", "Acoustic"), ("Strings", None), ("Pad/Choir", None), ("Keyboard", "Electric Piano")],
        "arp_cats": [("Dr/Pc", "Ballad"), ("Piano", "Ballad"), ("Gtr", None)],
    },
    "devotional": {
        "label": "Devotional / church",
        "perf_names": r"harmonium|organ|choir|bell|tambura",
        "perf_cats": [("Organ", None), ("Pad/Choir", "Choir"), ("Strings", None)],
        "arp_cats": [("Dr/Pc", "Ballad"), ("Organ", None)],
    },
    "pop": {
        "label": "Pop / rock",
        "perf_cats": [("Keyboard", None), ("Piano", None), ("Guitar", None), ("Syn Comp", None)],
        "arp_cats": [("Dr/Pc", "Pop Rock"), ("Dr/Pc", "Rock"), ("Bass", None), ("Gtr", None)],
    },
    "cinematic": {
        "label": "Cinematic / epic",
        "perf_names": r"cinema|epic|taiko|orchestra|ostinato|riser|hit",
        "perf_cats": [("Strings", None), ("Brass", None), ("Musical FX", None), ("Drum / Perc", None)],
        "arp_cats": [("Str", None), ("Dr/Pc", None), ("SynCp", None)],
    },
    "dance": {
        "label": "Dance / electronic",
        "perf_cats": [("Syn Comp", None), ("Syn Lead", None), ("Bass", None)],
        "arp_cats": [("Dr/Pc", "House"), ("Dr/Pc", "Techno"), ("Dr/Pc", "Hip Hop"), ("SynCp", None)],
    },
}

# Meter of the song -> arpeggio time signatures that fit.
METER_TS = {
    "4/4": {"4/4"}, "2/4": {"2/4", "4/4"}, "3/4": {"3/4", "6/8"}, "6/8": {"6/8", "6/4", "3/4"},
    "12/8": {"6/4", "6/8"}, "5/4": {"5/4"}, "7/8": {"7/4", "9/8"},
}


def _match_cat(item_cat, item_sub, cats):
    return any(item_cat == c and (s is None or item_sub == s) for c, s in cats)


def search_perfs(q="", main="", sub="", limit=60):
    rx = re.compile(re.escape(q.strip()), re.I) if q.strip() else None
    out = [p for p in PERFS
           if (not main or p["main"] == main) and (not sub or p["sub"] == sub)
           and (not rx or rx.search(p["name"]) or rx.search(f'{p["main"]} {p["sub"]}'))]
    return out[:limit]


def _tempo_fit(arp_tempo, bpm):
    """0 = perfect. Half/double time count as nearly as good."""
    if not bpm or not arp_tempo:
        return 1.0
    return min(abs(arp_tempo - bpm), abs(arp_tempo - bpm * 2) + 4, abs(arp_tempo - bpm / 2) + 4) / max(bpm, 1)


def search_arps(q="", cat="", sub="", ts="", bpm=None, limit=60):
    rx = re.compile(re.escape(q.strip()), re.I) if q.strip() else None
    tss = METER_TS.get(ts, {ts}) if ts else None
    out = [a for a in ARPS
           if (not cat or a["cat"] == cat) and (not sub or a["sub"] == sub)
           and (not tss or a["ts"] in tss)
           and (not rx or rx.search(a["name"]) or rx.search(f'{a["cat"]} {a["sub"]} {a.get("sound") or ""}'))]
    if bpm:
        out.sort(key=lambda a: _tempo_fit(a["tempo"], bpm))
    return out[:limit]


def _base_name(arp_name):
    # "MA_70s Rock _N" -> "70s Rock" (variations A/B/C share a base groove)
    return re.sub(r"\s*_[NC]$", "", re.sub(r"^(\[\w+\])?[A-Z]{1,2}\d?_", "", arp_name)).strip()


def suggest(feel, meter="4/4", bpm=None, limit_perfs=24, limit_arps=30):
    f = FEELS.get(feel) or FEELS["pop"]
    rxn = re.compile(f["perf_names"], re.I) if f.get("perf_names") else None
    named = [p for p in PERFS if rxn and rxn.search(p["name"])]
    by_cat = [p for p in PERFS if _match_cat(p["main"], p["sub"], f["perf_cats"]) and p not in named]
    perfs = (named + by_cat)[:limit_perfs]

    tss = METER_TS.get(meter, {"4/4"})
    rxx = re.compile(f["arp_exclude"], re.I) if f.get("arp_exclude") else None
    arps = [a for a in ARPS if _match_cat(a["cat"], a["sub"], f["arp_cats"]) and a["ts"] in tss
            and not (rxx and rxx.search(a["name"]))]
    if len({_base_name(a["name"]) for a in arps if a["cat"] == "Dr/Pc"}) < 4:  # few grooves in this meter for this feel: widen to any drum groove in the meter
        arps += [a for a in ARPS if a["cat"] == "Dr/Pc" and a["ts"] in tss and a not in arps]
    # Drum grooves first (they set the feel), then by how close the original tempo is.
    arps.sort(key=lambda a: (a["cat"] != "Dr/Pc", _tempo_fit(a["tempo"], bpm)))
    # One entry per groove family, so suggestions aren't 16 variations of the same thing.
    seen, uniq = set(), []
    for a in arps:
        b = (a["cat"], _base_name(a["name"]))
        if b in seen:
            continue
        seen.add(b)
        uniq.append({**a, "family": _base_name(a["name"])})
        if len(uniq) >= limit_arps:
            break
    note = None
    if feel == "indian":
        note = ("The MODX has no Indian drum arpeggios. These are the closest: Middle-Eastern and world grooves, "
                "plus sitar and harmonium arps. Your own tabla arps will replace these.")
    elif meter in ("6/8", "12/8", "3/4") and len(uniq) < 8:
        note = f"The MODX has very few {meter} drum arpeggios — your own patterns will fill this gap."
    return {"feel": feel, "meter": meter, "bpm": bpm, "performances": perfs, "arpeggios": uniq, "note": note}


def categories():
    cats = {}
    for p in PERFS:
        cats.setdefault(p["main"], set()).add(p["sub"])
    return {"performance": {k: sorted(v) for k, v in sorted(cats.items())},
            "feels": {k: v["label"] for k, v in FEELS.items()},
            "counts": {"performances": len(PERFS), "arpeggios": len(ARPS)}}


def perf(no):
    return _PERF_BY_NO.get(no)


# ---------- styles and scene plans ----------
# Arpeggio names carry a variation prefix: IA intro, MA–MD main grooves, FA–FD fills, BA break, EA/EB endings.
# Many grooves exist as a matched set across drums, bass, guitar and keys ("70s Rock", "12/8 Pop", …).

_NAME_RX = re.compile(r"^(\[\w+\])?([A-Z]{1,2})(\d?)_(.*?)(\s*_[NC])?$")
SCENE_SLOTS = [
    ("Intro", ["IA", "MA"]), ("Main A", ["MA"]), ("Main B", ["MB", "MA"]), ("Main C", ["MC", "MD", "MB"]),
    ("Fill A", ["FA", "FB", "FC"]), ("Fill B", ["FB", "FC", "FA"]), ("Break", ["BA", "MA"]), ("Ending", ["EA", "EB", "MA"]),
]
INSTR_ORDER = ["Dr/Pc", "Bass", "Gtr", "Piano", "Keys", "Pad", "Organ", "Str", "Brass", "WW", "SynCp"]
INSTR_LABEL = {"Dr/Pc": "Drums", "Bass": "Bass", "Gtr": "Guitar", "Piano": "Piano", "Keys": "Keys", "Pad": "Pad",
               "Organ": "Organ", "Str": "Strings", "Brass": "Brass", "WW": "Woodwind", "SynCp": "Synth"}

_STYLES = {}
for _a in ARPS:
    _m = _NAME_RX.match(_a["name"])
    if not _m:
        continue
    _fam = _m.group(4).strip()
    _st = _STYLES.setdefault(_fam, {"family": _fam, "parts": {}, "ts": _a["ts"], "tempo": _a["tempo"], "sub": _a["sub"]})
    _st["parts"].setdefault(_a["cat"], []).append({**_a, "var": _m.group(2), "n": _m.group(3) or ""})
    if _a["cat"] == "Dr/Pc":
        _st["ts"], _st["tempo"], _st["sub"] = _a["ts"], _a["tempo"], _a["sub"]
# A style = a groove family that has drums plus at least one band instrument.
STYLES = {k: v for k, v in _STYLES.items()
          if "Dr/Pc" in v["parts"] and any(c in v["parts"] for c in ("Bass", "Gtr", "Piano", "Keys"))}


def list_styles(q="", meter="", bpm=None, limit=200):
    rx = re.compile(re.escape(q.strip()), re.I) if q.strip() else None
    tss = METER_TS.get(meter, {meter}) if meter else None
    out = []
    for s in STYLES.values():
        if tss and s["ts"] not in tss:
            continue
        if rx and not (rx.search(s["family"]) or rx.search(s["sub"] or "")):
            continue
        out.append({"family": s["family"], "ts": s["ts"], "tempo": s["tempo"], "sub": s["sub"],
                    "instruments": [INSTR_LABEL.get(c, c) for c in INSTR_ORDER if c in s["parts"]]})
    out.sort(key=lambda s: _tempo_fit(s["tempo"], bpm) if bpm else s["family"])
    return out[:limit]


def _pick(arps, prefixes):
    for pre in prefixes:
        cands = sorted([a for a in arps if a["var"] == pre], key=lambda a: (a["n"] != "" and a["n"] != "1", a["no"]))
        if cands:
            return cands[0]
    return None


def _scene_arps(arps):
    """One arp per scene, rising in energy: Main A < Main B < Main C, using whichever main
    variations (MA–MD) this instrument actually has, so neighbouring scenes don't repeat."""
    def best(var):
        c = sorted([a for a in arps if a["var"] == var], key=lambda a: (a["n"] not in ("", "1"), a["no"]))
        return c[0] if c else None
    mains = [best(v) for v in ("MA", "MB", "MC", "MD") if best(v)]
    fills = [best(v) for v in ("FA", "FB", "FC") if best(v)]
    if not mains:
        mains = [sorted(arps, key=lambda a: a["no"])[0]]
    lo, hi = mains[0], mains[-1]
    mid = mains[1] if len(mains) > 2 else mains[-1] if len(mains) == 2 else lo
    if len(mains) == 2:  # only two: A = low, B and C = high
        mid = hi
    fill_a = fills[0] if fills else hi
    fill_b = fills[1] if len(fills) > 1 else fill_a
    return [best("IA") or lo, lo, mid, hi, fill_a, fill_b, best("BA") or lo, best("EA") or best("EB") or lo]


def scene_plan(family):
    s = STYLES.get(family)
    if not s:
        return None
    parts = []
    for cat in INSTR_ORDER:
        arps = s["parts"].get(cat)
        if not arps:
            continue
        row = [{"no": a["no"], "name": a["name"], "var": a["var"]} if a else None for a in _scene_arps(arps)]
        kit = next((a.get("sound") for a in arps if a.get("sound")), None)
        parts.append({"cat": cat, "label": INSTR_LABEL.get(cat, cat), "sound": kit, "scenes": row})
    return {"family": family, "ts": s["ts"], "tempo": s["tempo"], "sub": s["sub"],
            "scenes": [name for name, _ in SCENE_SLOTS], "parts": parts}


# ---------- sounds for each Part of a scene plan ----------
# Arpeggios name the sound they were made for ("Dry Standard Kit", "Clean Guitar", "Acoustic Piano").
# Most match a preset Performance name; the rest fall back to a sensible preset of that category.
_PERF_BY_NAME = {p["name"].lower(): p for p in PERFS}
_FALLBACK = {  # (main category, sub category or None, name hint or None)
    "Dr/Pc": ("Drum / Perc", "Drums", None), "Bass": ("Bass", None, "^finger bass$|finger"), "Gtr": ("Guitar", None, "^clean guitar$|clean"),
    "Piano": ("Piano", "Acoustic", "^CFX Concert$"), "Keys": ("Keyboard", "Electric Piano", None), "Pad": ("Pad/Choir", None, None),
    "Organ": ("Organ", None, None), "Str": ("Strings", None, None), "Brass": ("Brass", None, None),
    "WW": ("Woodwind", None, None), "SynCp": ("Syn Comp", None, None),
}
_HINTS = [  # sound name keyword -> (main, sub, name hint)
    (r"acoustic piano", ("Piano", "Acoustic", "^CFX Concert$")), (r"finger", ("Bass", None, "^finger bass$|finger")), (r"electric piano", ("Keyboard", "Electric Piano", None)),
    (r"acoustic guitar|nylon", ("Guitar", None, "nylon|steel|acoustic")), (r"od/dist|dist", ("Guitar", "Distortion", None)),
    (r"synth bass", ("Bass", None, "syn")), (r"slap", ("Bass", None, "slap")), (r"kit", ("Drum / Perc", "Drums", "standard|kit")),
    (r"percussion", ("Drum / Perc", "Percussion", None)), (r"sax", ("Woodwind", None, "sax")), (r"strings", ("Strings", None, None)),
    (r"organ", ("Organ", None, None)), (r"clavi", ("Keyboard", None, "clav")),
]


def _first(main, sub, hint):
    cands = [p for p in PERFS if p["main"] == main and (sub is None or p["sub"] == sub)]
    for alt in (hint.split("|") if hint else []):  # try each hint in order, most specific first
        rx = re.compile(alt, re.I)
        hinted = [p for p in cands if rx.search(p["name"])]
        if hinted:
            return hinted[0]
    return cands[0] if cands else None


def resolve_sound(cat, sound):
    """Preset Performance to load into a Part for this instrument (best effort)."""
    if sound:
        clean = re.sub(r"\s*\(.*?\)\s*", " ", sound).strip().lower()
        if clean in _PERF_BY_NAME:
            return _PERF_BY_NAME[clean]
        for rx, spec in _HINTS:
            if re.search(rx, clean):
                p = _first(*spec)
                if p:
                    return p
    spec = _FALLBACK.get(cat)
    return _first(*spec) if spec else None


_orig_scene_plan = scene_plan


def scene_plan(family):  # noqa: F811 — extends the plan with a suggested sound per Part
    plan = _orig_scene_plan(family)
    if not plan:
        return plan
    for row in plan["parts"]:
        p = resolve_sound(row["cat"], row.get("sound"))
        row["sound_no"], row["sound_name"] = (p["no"], p["name"]) if p else (None, None)
    return plan
