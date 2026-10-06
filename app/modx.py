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


# ---------- arranger-style band (Parts 2–8) ----------
# Part 1 stays your right-hand sound. The left hand drives the band: drums, percussion, bass, guitar and
# keys play arpeggio patterns; strings and pad hold the chord you play. Missing instruments are borrowed
# from other grooves with the same time signature (nearest tempo).
PERC_RX = re.compile(r"percussion|latin|conga|bongo|shaker|cajon|tabla", re.I)
ACOUSTIC_GTR_RX = re.compile(r"acoustic|steel|nylon|12str|finger", re.I)
BAND_ROLES = [("drums", "Drums"), ("perc", "Percussion"), ("bass", "Bass"), ("gtr", "Guitar"),
              ("keys", "Piano / keys"), ("strings", "Strings"), ("pad", "Pad")]
# Sound pools per band mood and instrument (preset Performance numbers), ordered warm/dark -> bright.
# A song picks from each pool by what it sounds like (brightness, strummed vs picked, sustained parts);
# 0 = leave the instrument out; "lead" = suggested melody sounds for the right hand.
BAND_POOLS = {
    "unplugged": {"drums": [1226, 1225, 2753], "perc": [2807, 2830], "bass": [2537, 2491],
                  "gtr": {"pick": [2529, 316, 314], "strum": [317, 323, 322]}, "keys": [26, 29, 31, 3],
                  "strings": [493, 492, 494], "pad": [784, 2132, 2594], "lead": [3, 26, 2010]},
    "band": {"drums": [], "perc": [2807, 2830], "bass": [], "gtr": {"pick": [333, 331], "strum": [334, 332]},
             "keys": [], "strings": [493, 492, 494], "pad": [2132, 2594, 2117], "lead": [3, 90]},
    "devotional": {"drums": [1226, 1225], "perc": [2830, 2807], "bass": [2537, 2491],
                   "gtr": {"pick": [316, 2529], "strum": [317, 316]}, "keys": [2749],
                   "strings": [493, 492], "pad": [784, 2132], "lead": [2010, 2011, 2749, 2428]},
    "cinematic": {"drums": [1255, 1219], "perc": [2752, 2830], "bass": [491], "gtr": 0, "keys": [25, 26, 3],
                  "strings": [486, 482, 481], "pad": [796, 773, 2117], "lead": [634, 629, 26]},
    "remix": {"drums": [1238, 1237, 1239], "perc": [2449, 2807], "bass": [1822, 2543],
              "gtr": {"pick": [1019, 1027], "strum": [1027, 1023]}, "keys": [130, 123, 108],
              "strings": [481, 482], "pad": [778, 773, 2117], "lead": [3, 123]},
    "retro": {"drums": [1218, 1220], "perc": [2807, 2808], "bass": [2538, 1760],
              "gtr": {"pick": [333, 331], "strum": [334, 332]}, "keys": [90, 108],
              "strings": [493, 494], "pad": [2594, 2132], "lead": [2011, 2010, 90]},
    "indian": {"drums": [2420, 2423], "perc": [2830, 2807], "bass": [2537], "gtr": [2407, 2419],
               "keys": [2749], "strings": [493, 492], "pad": [2418, 784], "lead": [2010, 2428, 2419]},
}
BAND_LABELS = {"unplugged": "Unplugged", "band": "Full band", "devotional": "Devotional", "cinematic": "Cinematic",
               "remix": "Remix / dance", "retro": "Retro film", "indian": "Indian"}
BAND_SOUNDS = BAND_POOLS  # moods available (kept name for callers)
# Instruments that hold your chord instead of playing a pattern (harmonium sustains in devotional songs).
BAND_HOLD = {"devotional": {"strings", "pad", "keys"}, "indian": {"strings", "pad", "keys"}}
# Where each role's patterns come from (remix: synth comping instead of guitar).
BAND_SOURCE = {"remix": {"gtr": ["SynCp", "Gtr"]}}
FEEL_BAND = {"ballad": "unplugged", "devotional": "devotional", "indian": "indian", "cinematic": "cinematic",
             "dance": "remix", "pop": "band", "": "band"}
_PERF_BY_NO = {p["no"]: p for p in PERFS}


def _role_arps(style, role, flavor=""):
    parts = style["parts"]
    for cat in BAND_SOURCE.get(flavor, {}).get(role, []):
        if parts.get(cat):
            return parts[cat]
    if role in ("drums", "perc"):
        dr = parts.get("Dr/Pc", [])
        kit = [a for a in dr if not PERC_RX.search(a.get("sound") or "")]
        perc = [a for a in dr if PERC_RX.search(a.get("sound") or "")]
        # Families keep kit and percussion arps under one name; tell them apart by the sound they were made for,
        # and when a family has no sound labels, the lower-numbered set is the kit.
        return kit or (dr if role == "drums" else []) if role == "drums" else perc
    if role == "bass":
        return parts.get("Bass", [])
    if role == "gtr":
        return parts.get("Gtr", [])
    if role == "keys":
        return parts.get("Piano") or parts.get("Keys") or []
    return []


def _borrow(style, role, flavor):
    """Same instrument from another groove in the same meter, nearest tempo; acoustic guitars first when unplugged."""
    best, best_key = None, None
    for f, s in STYLES.items():
        if f == style["family"] or s["ts"] != style["ts"]:
            continue
        arps = _role_arps(s, role, flavor)
        if not arps or not any(a["var"] in ("MA", "MB", "MC", "MD") for a in arps):
            continue
        acoustic = role == "gtr" and any(ACOUSTIC_GTR_RX.search(a.get("sound") or "") for a in arps)
        k = (0 if (flavor == "unplugged" and acoustic) or role != "gtr" or flavor != "unplugged" else 1,
             0 if s["sub"] == style["sub"] else 1,
             1 if re.search(r"salsa|latin|reggae|merengue|bomba|montuno|guaguanco|samba|hip|trap|edm|house", f, re.I) else 0,
             abs(s["tempo"] - style["tempo"]))
        if best_key is None or k < best_key:
            best, best_key = (f, arps), k
    return best


def _pick_sound(pool, role, tone):
    """(perf no, reason, options) from a mood's pool for this song."""
    if pool == 0:
        return 0, "", []
    if isinstance(pool, dict):
        strum = bool(tone and tone.get("strummed"))
        lst = pool["strum" if strum else "pick"]
        opts = pool["strum"] + [x for x in pool["pick"] if x not in pool["strum"]]
        why = "strummed part in the song" if strum else "picked / sparse part in the song"
    else:
        lst, opts, why = pool, list(pool), ""
    if not lst:
        return None, "", []
    i = 0
    if tone and len(lst) > 1 and role in ("keys", "strings", "pad", "drums", "gtr", "bass"):
        i = min(len(lst) - 1, int(round(tone.get("brightness", 0.4) * (len(lst) - 1))))
        why = ", ".join(x for x in (why, "brighter mix" if tone["brightness"] > 0.6 else "warmer mix" if tone["brightness"] < 0.35 else "") if x)
    return lst[i], why, opts


def pattern_family(cat, family):
    return _pattern_families().get((cat, family))


def band_plan(family, flavor="unplugged", perc=True, tone=None, overrides=None, patterns=None):
    style = STYLES.get(family)
    if not style:
        return None
    flavor = flavor if flavor in BAND_POOLS else "band"
    pools = BAND_POOLS[flavor]
    hold = BAND_HOLD.get(flavor, {"strings", "pad"})
    overrides = overrides or {}
    parts = []
    for role, label in BAND_ROLES:
        if (role == "perc" and not perc) or pools.get(role) == 0:
            continue
        label = {("remix", "gtr"): "Synth comp", ("devotional", "keys"): "Harmonium", ("indian", "keys"): "Harmonium",
                 ("indian", "gtr"): "Santoor / sitar", ("indian", "pad"): "Tambura / pad", ("indian", "drums"): "Tabla"}.get((flavor, role), label)
        row = {"role": role, "label": label, "cat": role, "scenes": [None] * 8, "hold": role in hold, "from": None}
        if not row["hold"]:
            arps = _role_arps(style, role, flavor)
            src = family
            if not arps:
                b = _borrow(style, role, flavor)
                if not b:
                    continue  # nothing suitable in this meter (e.g. no percussion grooves): leave the Part out
                src, arps = b
            pcat = {"gtr": "Gtr", "bass": "Bass"}.get(role)
            chosen = (patterns or {}).get(role)
            if pcat and chosen and pattern_family(pcat, chosen):     # your pattern choice for this song
                src, arps = chosen, pattern_family(pcat, chosen)
            row["from"] = src if src != family else None
            row["family"] = src
            row["scenes"] = [{"no": a["no"], "name": a["name"], "var": a["var"]} if a else None for a in _scene_arps(arps)]
            row["sound"] = next((a.get("sound") for a in arps if a.get("sound")), None)
            if pcat:
                row["pattern_style"] = pattern_style(pcat, src, arps)[1]
        no, why, opts = _pick_sound(pools.get(role, []), role, tone)
        if not no and not row["hold"]:
            p = resolve_sound({"drums": "Dr/Pc", "bass": "Bass", "gtr": "Gtr", "keys": "Piano", "perc": "Dr/Pc"}.get(role, role), row.get("sound"))
            no, why = (p["no"] if p else None), "the sound this groove was written for"
            opts = [no] if no else []
        ov = overrides.get(role)
        if ov and _PERF_BY_NO.get(ov.get("no")):
            no, why = ov["no"], "your choice"
            if no not in opts:
                opts = [no] + opts
        p = _PERF_BY_NO.get(no)
        row["sound_no"], row["sound_name"], row["why"] = (p["no"], p["name"], why) if p else (None, None, "")
        row["options"] = [{"no": o, "name": _PERF_BY_NO[o]["name"]} for o in opts if o in _PERF_BY_NO]
        parts.append(row)
    leads = [{"no": n, "name": _PERF_BY_NO[n]["name"]} for n in pools.get("lead", []) if n in _PERF_BY_NO]
    return {"family": family, "ts": style["ts"], "tempo": style["tempo"], "sub": style["sub"], "flavor": flavor,
            "flavor_label": BAND_LABELS[flavor], "scenes": [name for name, _ in SCENE_SLOTS], "parts": parts, "band": True,
            "lead": leads[0] if leads else None, "leads": leads, "fx": BAND_FX.get(flavor, BAND_FX["band"]), "tone": tone}


# Effects per mood. Types are (MSB, LSB) from the Effect Type List; sends are per-role scene values.
BAND_FX = {
    "unplugged": {"reverb": [0x01, 0x03], "reverb_name": "HD Hall", "variation": [0x02, 0x28], "variation_name": "Tempo Delay Stereo", "lead_var": 18},
    "band": {"reverb": [0x01, 0x13], "reverb_name": "HD Room", "variation": [0x02, 0x28], "variation_name": "Tempo Delay Stereo", "lead_var": 12},
    "devotional": {"reverb": [0x01, 0x03], "reverb_name": "HD Hall", "variation": [0x02, 0x28], "variation_name": "Tempo Delay Stereo", "lead_var": 30},
    "cinematic": {"reverb": [0x01, 0x00], "reverb_name": "REV-X Hall", "variation": [0x02, 0x10], "variation_name": "Tempo Cross Delay", "lead_var": 34},
    "remix": {"reverb": [0x01, 0x21], "reverb_name": "HD Plate", "variation": [0x02, 0x28], "variation_name": "Tempo Delay Stereo", "lead_var": 22},
    "retro": {"reverb": [0x01, 0x20], "reverb_name": "R3 Plate", "variation": [0x02, 0x20], "variation_name": "Tempo Delay Mono", "lead_var": 24},
    "indian": {"reverb": [0x01, 0x03], "reverb_name": "HD Hall", "variation": [0x02, 0x28], "variation_name": "Tempo Delay Stereo", "lead_var": 28},
}


# ---------- guitar strums and bass lines: pick the pattern style per Part ----------
# The MODX names patterns by groove ("MA_FingerPickin", "MB_Reggaeton1 Mute Gtr"), not by technique, so
# the style comes from name hints, the sound the pattern was written for and the groove family.
GTR_STYLES = [
    ("strum", "Strum (acoustic)", re.compile(r"strum|folk|country|cntry|unplug|8beat|8bt|8 beat|acoustic|steel|mega steel|campfire|worship|wrshp", re.I)),
    ("muted", "Muted / chop", re.compile(r"mute|chop|reggae|ska|skank|cutting|dancehall|reggaeton", re.I)),
    ("funk", "Funk / R&B", re.compile(r"funk|disco|wah|r&b|motown|soul|philly|slow&easy", re.I)),
    ("finger", "Fingerpick / arpeggio", re.compile(r"finger|pickin|nylon|classical|bossa|jazz|harp|arpeg|ballad|bld|12str|steel ?guitar|ambient|chill|delay", re.I)),
    ("rock", "Rock / power", re.compile(r"rock|punk|metal|grunge|power|od/dist|dist|drive|hard", re.I)),
    ("clean", "Clean / pop", re.compile(r".", re.I)),
]
BASS_STYLES = [
    ("walking", "Walking / jazz", re.compile(r"walk|jazz|swing|bebop|blues", re.I)),
    ("slap", "Slap / funk", re.compile(r"slap|funk|disco|yay area|motown", re.I)),
    ("synth", "Synth / sub", re.compile(r"synth|sub|808|trap|wobble|edm|house|techno|dirty|trance|dub|electro|step", re.I)),
    ("reggae", "Reggae / Latin", re.compile(r"reggae|latin|salsa|bossa|afro|reggaeton|samba|cumbia|merengue|montuno", re.I)),
    ("picked", "Picked / rock", re.compile(r"pick|rock|punk|metal|grunge", re.I)),
    ("octave", "Octave / disco", re.compile(r"octave|oct\b|disco|dance", re.I)),
    ("root", "Root & fifth / ballad", re.compile(r".", re.I)),   # everything else
]
_PATTERN_FAMS = None


def _pattern_families():
    """{(cat, family): [arps]} for every prefixed Gtr / Bass pattern."""
    global _PATTERN_FAMS
    if _PATTERN_FAMS is None:
        fam = {}
        for a in ARPS:
            if a["cat"] not in ("Gtr", "Bass"):
                continue
            m = _NAME_RX.match(a["name"])
            if not m:
                continue
            fam.setdefault((a["cat"], m.group(4).strip()), []).append({**a, "var": m.group(2), "n": m.group(3) or ""})
        _PATTERN_FAMS = fam
    return _PATTERN_FAMS


def pattern_style(cat, family, arps):
    sound = next((a.get("sound") for a in arps if a.get("sound")), "") or ""
    text = family + " " + sound
    for sid, label, rx in (GTR_STYLES if cat == "Gtr" else BASS_STYLES):
        if rx.search(text):
            return sid, label
    return ("clean", "Clean / pop") if cat == "Gtr" else ("root", "Root & fifth / ballad")


def pattern_options(role, ts="4/4", bpm=None, per_style=8):
    """Pattern choices for a guitar or bass Part, grouped by style, nearest tempo first."""
    cat = "Gtr" if role in ("gtr", "gtr2", "Gtr") else "Bass"
    styles = GTR_STYLES if cat == "Gtr" else BASS_STYLES
    groups = {sid: {"id": sid, "label": label, "options": []} for sid, label, _ in styles}
    for (c, family), arps in _pattern_families().items():
        if c != cat or arps[0].get("ts") != ts:
            continue
        if not any(a["var"] in ("MA", "MB", "MC", "MD") for a in arps):
            continue
        sid, _ = pattern_style(cat, family, arps)
        tempo = arps[0].get("tempo") or 120
        dist = abs(tempo - bpm) if bpm else 0
        groups[sid]["options"].append({"family": family, "tempo": tempo, "sound": arps[0].get("sound"),
                                       "variations": len({a["var"] for a in arps}), "dist": dist,
                                       "scenes": [{"no": a["no"], "name": a["name"], "var": a["var"]} if a else None
                                                  for a in _scene_arps(arps)]})
    out = []
    for sid, _, _ in styles:
        g = groups[sid]
        g["options"].sort(key=lambda o: (o["dist"] > 25, -min(o["variations"], 6), o["dist"]))
        g["options"] = g["options"][:per_style]
        if g["options"]:
            out.append(g)
    return {"role": role, "cat": cat, "ts": ts, "groups": out}
