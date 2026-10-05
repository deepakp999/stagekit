/* Tabla studio: bol → key map, taal pattern sets laid out for the 8 scenes, MIDI preview and .mid export.
   Exported MIDI files load on the MODX as Songs; "Put Track to Arpeggio" turns each into a user arpeggio. */
"use strict";

const BOLS = ["Dha", "Dhin", "Na", "Tin", "Tun", "Ge", "Ke", "Ti", "Ra"];
const BOL_ALIAS = {dhi: "Dhin", ta: "Na", ka: "Ke", ki: "Ke", kat: "Ke", ghe: "Ge", ga: "Ge", te: "Ti", tit: "Ti", tu: "Tun", re: "Ra"};
const SCENE_NAMES = ["Intro", "Main A", "Main B", "Main C", "Fill A", "Fill B", "Break", "Ending"];

// Key maps use Yamaha note names (middle C = C3), the same as the MODX Data List.
const KIT_PRESETS = {
  hands: {
    label: "MODX built-in: Hands Kit (preset #2813) — basic, 4 tabla strokes", perf: 2813,
    map: {Dha: "B0", Dhin: "G#1+A#1", Na: "A#1", Tin: "A#1", Tun: "A#1", Ge: "G#1", Ke: "F#1", Ti: "F#1", Ra: "F#1"},
  },
  custom: {
    label: "Your own tabla samples (imported as a drum kit)", perf: null,
    map: {Dha: "C3", Dhin: "C#3", Na: "D3", Tin: "D#3", Tun: "E3", Ge: "F3", Ke: "F#3", Ti: "G3", Ra: "G#3"},
  },
};

// Starting patterns — edit any of them; your edits are saved. "-" is a rest, "|" is just a visual bar line.
// beats/steps: beats per bar and steps per beat; tokens run left to right across the whole pattern.
const TAALS = {
  keherwa: {
    label: "Keherwa (8 matras, 4/4 film/bhajan)", ts: [4, 4], steps: 4, bpm: 90,
    scenes: [
      "Dha - - - Na - - - Na - - - Dhin - - -",
      "Dha - Ge - Na - Ti - Na - Ke - Dhin - Na -",
      "Dha - Ge Na Ti - Na - Na - Ke - Dhin - Na Ge",
      "Dha Ge Na Ti Na Ke Dhin Na Dha Ge Na Ti Na Ke Dhin Na",
      "Dha - Ge - Na - Ti - Ti Ra Ki Ta Ti Ra Ki Ta",
      "Ti Ra Ki Ta Dha - Ti Ra Ki Ta Dha - Dha - Dha -",
      "Dha - - - - - - - - - - - - - - -",
      "Dha Ti Dha - Dha Ti Dha - Dha Ti Dha - - - - - | Dha - - - - - - - - - - - - - - -",
    ],
  },
  dadra: {
    label: "Dadra (6 matras, 6/8 film ballads)", ts: [6, 8], steps: 2, bpm: 80,
    scenes: [
      "Dha - - - Na - Dha - - - Na -",
      "Dha - Dhin - Na - Dha - Tin - Na -",
      "Dha - Dhin Na Na - Dha - Tin Na Na -",
      "Dha Ge Dhin Na Na Ke Dha Ge Tin Na Na Ke",
      "Dha - Dhin - Na - Ti Ra Ki Ta Ti Ra",
      "Ti Ra Ki Ta Dha - Ti Ra Ki Ta Dha -",
      "Dha - - - - - - - - - - -",
      "Dha Ti Dha - Dha Ti Dha - Dha Ti Dha - | Dha - - - - - - - - - - -",
    ],
  },
  rupak: {
    label: "Rupak (7 matras, 7/8)", ts: [7, 8], steps: 2, bpm: 80,
    scenes: [
      "Tin - - - Na - Dhin - - - Dhin - - -",
      "Tin - Tin - Na - Dhin - Na - Dhin - Na -",
      "Tin - Tin Na Na - Dhin - Na Ke Dhin - Na Ke",
      "Tin Na Tin Na Na Ke Dhin Na Na Ke Dhin Na Na Ke",
      "Tin - Tin - Na - Ti Ra Ki Ta Ti Ra Ki Ta",
      "Ti Ra Ki Ta Tin - Ti Ra Ki Ta Dhin - Na -",
      "Tin - - - - - - - - - - - - -",
      "Dha Ti Dha - Dha Ti Dha - Dha Ti Dha - - - | Tin - - - - - - - - - - - - -",
    ],
  },
  teentaal: {
    label: "Teentaal (16 matras, 4 bars of 4/4)", ts: [4, 4], steps: 2, bpm: 100,
    scenes: [
      "Dha - - - Dha - - - Dha - - - Ta - - - | Ta - - - Dha - - - Dha - - - Dha - - -",
      "Dha - Dhin - Dhin - Dha - Dha - Dhin - Dhin - Dha - | Dha - Tin - Tin - Ta - Ta - Dhin - Dhin - Dha -",
      "Dha - Dhin - Dhin - Dha Ge Dha - Dhin - Dhin - Dha Ge | Dha - Tin - Tin - Ta Ke Ta - Dhin - Dhin - Dha Ge",
      "Dha Ge Dhin Na Dhin Na Dha Ge Dha Ge Dhin Na Dhin Na Dha Ge | Dha Ke Tin Na Tin Na Ta Ke Ta Ke Dhin Na Dhin Na Dha Ge",
      "Dha - Dhin - Ti Ra Ki Ta",
      "Ti Ra Ki Ta Dha - Ti Ra",
      "Dha - - - - - - -",
      "Dha Ti Dha - Dha Ti Dha - Dha Ti Dha - - - - - | Dha - - - - - - -",
    ],
  },
  jhaptaal: {
    label: "Jhaptaal (10 matras, 5/4)", ts: [5, 4], steps: 2, bpm: 90,
    scenes: [
      "Dhi - Na - Dhi - - - Na - | Ti - Na - Dhi - - - Na -",
      "Dhi - Na - Dhi - Dhi - Na - | Ti - Na - Dhi - Dhi - Na -",
      "Dhi Na Na - Dhi - Dhi Na Na - | Ti Na Na - Dhi - Dhi Na Na -",
      "Dhi Na Na Ke Dhi Na Dhi Na Na Ke | Ti Na Na Ke Dhi Na Dhi Na Na Ke",
      "Dhi - Na - Ti Ra Ki Ta Ti Ra",
      "Ti Ra Ki Ta Dhi - Ti Ra Ki Ta",
      "Dhi - - - - - - - - -",
      "Dha Ti Dha - Dha Ti Dha - Dha Ti | Dha - - - - - - - - -",
    ],
  },
};

const NOTE_PC = {C: 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, F: 5, "F#": 6, Gb: 6, G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11};
// "G#1" → MIDI note, Yamaha convention (C3 = 60, C-2 = 0). "G#1+A#1" → several notes.
function parseNotes(spec) {
  return String(spec || "").split("+").map(x => x.trim()).filter(Boolean).map(x => {
    const m = /^([A-Ga-g][#b]?)(-?\d)$/.exec(x);
    if (!m) return null;
    const pc = NOTE_PC[m[1][0].toUpperCase() + m[1].slice(1)];
    const n = (+m[2] + 2) * 12 + pc;
    return pc == null || n < 0 || n > 127 ? null : n;
  }).filter(n => n != null);
}
const canonBol = t => {
  const k = t.toLowerCase();
  return BOLS.find(b => b.toLowerCase() === k) || BOL_ALIAS[k] || null;
};

// Pattern text → timed events. Accents: sam loudest, beat starts strong, off-beats softer, rolls lighter.
function patternEvents(text, taal, map) {
  const toks = text.replace(/\|/g, " ").split(/\s+/).filter(Boolean);
  const perBar = taal.ts[0] * taal.steps;
  const bars = Math.max(1, Math.ceil(toks.length / perBar));
  const ev = [], unknown = new Set();
  toks.forEach((t, i) => {
    if (t === "-" || t === ".") return;
    const bol = canonBol(t);
    if (!bol) { unknown.add(t); return; }
    const notes = parseNotes(map[bol]);
    const inBar = i % perBar;
    const roll = /^(ti|ra|ki|ta|te|re)$/i.test(t) && (toks[i + 1] && /^(ra|ki|ta)$/i.test(toks[i + 1]) || /^(ra|ki|ta)$/i.test(t));
    let vel = inBar === 0 ? (i === 0 ? 120 : 110) : inBar % taal.steps === 0 ? 98 : 80;
    if (roll) vel = Math.min(vel, 76);
    if (bol === "Ge") vel = Math.max(70, vel - 6);
    notes.forEach(n => ev.push({step: i, note: n, vel}));
  });
  return {events: ev, steps: bars * perBar, bars, unknown: [...unknown]};
}

// --- minimal Standard MIDI File (format 0) ---
function vlq(n) { const b = [n & 127]; while ((n >>= 7)) b.unshift((n & 127) | 128); return b; }
function buildMidi(pat, taal, bpm, ch) {
  const ppq = 480, beatUnit = taal.ts[1];
  const stepTicks = Math.round(ppq * (4 / beatUnit) / taal.steps);
  const len = Math.max(1, Math.round(stepTicks * 0.8));
  const tempo = Math.round(60000000 / bpm);
  const msgs = [];
  for (const e of pat.events) {
    msgs.push({t: e.step * stepTicks, d: [0x90 | ch, e.note, e.vel]});
    msgs.push({t: e.step * stepTicks + len, d: [0x80 | ch, e.note, 0]});
  }
  msgs.sort((a, b) => a.t - b.t || (a.d[0] & 0xF0) - (b.d[0] & 0xF0));
  const tr = [0x00, 0xFF, 0x51, 0x03, (tempo >> 16) & 255, (tempo >> 8) & 255, tempo & 255,
    0x00, 0xFF, 0x58, 0x04, taal.ts[0], Math.log2(beatUnit), 24, 8];
  let last = 0;
  for (const m of msgs) { tr.push(...vlq(m.t - last), ...m.d); last = m.t; }
  tr.push(...vlq(pat.steps * stepTicks - last), 0xFF, 0x2F, 0x00);
  const u32 = n => [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255];
  return new Uint8Array([0x4D, 0x54, 0x68, 0x64, ...u32(6), 0, 0, 0, 1, (ppq >> 8) & 255, ppq & 255,
    0x4D, 0x54, 0x72, 0x6B, ...u32(tr.length), ...tr]);
}

// --- minimal zip (stored, no compression) ---
const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
const crc32 = b => { let c = 0xFFFFFFFF; for (const x of b) c = CRC[(c ^ x) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
function buildZip(files) {
  const enc = new TextEncoder(), parts = [], central = [];
  let off = 0;
  const le = (n, k) => Array.from({length: k}, (_, i) => (n >>> (8 * i)) & 255);
  for (const f of files) {
    const name = enc.encode(f.name), crc = crc32(f.data), sz = f.data.length;
    const head = [0x50, 0x4B, 0x03, 0x04, 20, 0, 0, 0, 0, 0, 0, 0, 0, 0, ...le(crc, 4), ...le(sz, 4), ...le(sz, 4), ...le(name.length, 2), 0, 0];
    parts.push(new Uint8Array(head), name, f.data);
    central.push(new Uint8Array([0x50, 0x4B, 0x01, 0x02, 20, 0, 20, 0, 0, 0, 0, 0, 0, 0, 0, 0, ...le(crc, 4), ...le(sz, 4), ...le(sz, 4),
      ...le(name.length, 2), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ...le(off, 4)]), name);
    off += head.length + name.length + sz;
  }
  const cdSize = central.reduce((a, b) => a + b.length, 0);
  const end = new Uint8Array([0x50, 0x4B, 0x05, 0x06, 0, 0, 0, 0, ...le(files.length, 2), ...le(files.length, 2), ...le(cdSize, 4), ...le(off, 4), 0, 0]);
  return new Blob([...parts, ...central, end], {type: "application/zip"});
}
function download(blob, name) {
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}
const fileSafe = s => s.replace(/[^\w\- ]+/g, "").trim();

async function tablaView() {
  const saved = (await api("kv/tabla")).value || {};
  const st = {
    kit: saved.kit || "hands",
    maps: {hands: {...KIT_PRESETS.hands.map, ...(saved.maps?.hands || {})}, custom: {...KIT_PRESETS.custom.map, ...(saved.maps?.custom || {})}},
    edits: saved.edits || {}, taal: saved.taal || "keherwa", bpm: saved.bpm || null, part: saved.part || 1,
  };
  let playTimer = null;
  const taal = () => TAALS[st.taal];
  const map = () => st.maps[st.kit];
  const text = i => st.edits[st.taal]?.[i] ?? taal().scenes[i];
  const bpm = () => st.bpm || taal().bpm;
  const save = async () => { try { await api("kv/tabla", {method: "PUT", json: st}); toast("Saved"); } catch (e) { toast(e.message); } };

  view.innerHTML = `
    <h1>Tabla studio</h1>
    <div class="grid2">
      <div class="panel">
        <b>Kit and key map</b>
        <select id="tkit" style="margin-top:10px">${Object.entries(KIT_PRESETS).map(([k, v]) => `<option value="${k}">${esc(v.label)}</option>`).join("")}</select>
        <div class="row" style="margin-top:8px"><label class="f" style="margin:0">Part</label>
          <select id="tpart" style="width:70px">${[1, 2, 3, 4, 5, 6, 7, 8].map(n => `<option>${n}</option>`).join("")}</select>
          <button class="btn sm" id="tloadkit">Load kit on MODX</button><span class="grow"></span><button class="btn primary sm" id="tsave">Save</button></div>
        <table class="sec" style="margin-top:8px"><thead><tr><th>Bol</th><th>MODX key(s)</th><th></th></tr></thead><tbody id="tmap"></tbody></table>
        <div class="small muted">Yamaha note names (middle C = C3). Use + for two keys at once, e.g. G#1+A#1. Tap ▶ to hear a stroke on the MODX.</div>
      </div>
      <div class="panel">
        <b>How to turn these into scenes</b>
        <ol class="small" style="padding-left:18px;margin:8px 0 0;line-height:1.6">
          <li>Choose a taal, set the tempo, check each pattern with ▶ (plays on your MODX).</li>
          <li><b>Download all 8</b>, unzip and copy the .mid files to a USB stick.</li>
          <li>On the MODX, load each file as a Song, then use <b>Put Track to Arpeggio</b> to make a user arpeggio. Keep the names (S1 Intro … S8 Ending).</li>
          <li>In your tabla Performance, give the tabla Part those 8 user arps (Arp Select 1–8) and point Scene 1–8 to Arp Select 1–8 — the same layout the scene builder uses — then <b>Store</b>.</li>
        </ol>
        <div class="small muted" style="margin-top:8px">Each pattern uses at most 9 different keys, well under the MODX limit of 16 per user arpeggio.</div>
      </div>
    </div>
    <div class="panel" style="margin-top:14px">
      <div class="row">
        <select id="ttaal" style="max-width:340px">${Object.entries(TAALS).map(([k, v]) => `<option value="${k}">${esc(v.label)}</option>`).join("")}</select>
        <label class="f" style="margin:0">Tempo</label><input id="tbpm" type="number" min="30" max="300" style="width:90px">
        <span class="grow"></span>
        <button class="btn sm" id="treset">Reset patterns</button>
        <button class="btn primary sm" id="tzip">⬇ Download all 8 (.mid zip)</button>
      </div>
      <div id="tpats" class="tpats"></div>
    </div>`;

  const drawMap = () => {
    $("#tmap").innerHTML = BOLS.map(b => `<tr><td><b>${b}</b></td>
      <td><input type="text" data-bol="${b}" value="${esc(map()[b] || "")}" style="width:140px"></td>
      <td><button class="btn sm" data-hear="${b}">▶</button><span class="small" data-bad="${b}" style="color:var(--danger);margin-left:6px"></span></td></tr>`).join("");
    $$("#tmap input").forEach(inp => inp.oninput = () => {
      map()[inp.dataset.bol] = inp.value.trim();
      $(`[data-bad="${inp.dataset.bol}"]`).textContent = inp.value.trim() && !parseNotes(inp.value).length ? "not a note" : "";
      drawPats();
    });
    $$("[data-hear]").forEach(b => b.onclick = async () => {
      const out = await MIDI.ensure(); if (!out) return;
      const ch = (st.part - 1) & 15, now = performance.now();
      parseNotes(map()[b.dataset.hear]).forEach(n => { out.send([0x90 | ch, n, 110], now); out.send([0x80 | ch, n, 0], now + 300); });
    });
  };
  const drawPats = () => {
    const t = taal();
    $("#tpats").innerHTML = SCENE_NAMES.map((nm, i) => {
      const p = patternEvents(text(i), t, map());
      return `<div class="tpat"><div class="row"><b class="grow">S${i + 1} · ${nm}</b>
          <span class="small muted">${p.bars} bar${p.bars > 1 ? "s" : ""} · ${t.ts[0]}/${t.ts[1]}</span>
          <button class="btn sm" data-play="${i}">▶</button><button class="btn sm" data-dl="${i}">⬇ .mid</button></div>
        <textarea class="tok" data-i="${i}" spellcheck="false">${esc(text(i))}</textarea>
        ${p.unknown.length ? `<div class="small" style="color:var(--danger)">Unknown bols: ${esc(p.unknown.join(", "))}</div>` : ""}</div>`;
    }).join("");
    $$(".tok").forEach(ta => ta.onchange = () => { (st.edits[st.taal] ||= {})[ta.dataset.i] = ta.value; drawPats(); });
    $$("[data-play]").forEach(b => b.onclick = () => play(+b.dataset.play, b));
    $$("[data-dl]").forEach(b => b.onclick = () => {
      const i = +b.dataset.dl, p = patternEvents(text(i), taal(), map());
      download(new Blob([buildMidi(p, taal(), bpm(), (st.part - 1) & 15)], {type: "audio/midi"}), fileName(i));
    });
  };
  const fileName = i => `${fileSafe(st.taal)}-S${i + 1}-${fileSafe(SCENE_NAMES[i]).replace(/ /g, "")}.mid`;
  async function play(i, btn) {
    stop();
    const out = await MIDI.ensure(); if (!out) return;
    const t = taal(), p = patternEvents(text(i), t, map());
    const stepMs = 60000 / bpm() * (4 / t.ts[1]) / t.steps, ch = (st.part - 1) & 15;
    const loops = 2, start = performance.now() + 80;
    for (let l = 0; l < loops; l++) for (const e of p.events) {
      const at = start + (l * p.steps + e.step) * stepMs;
      out.send([0x90 | ch, e.note, e.vel], at); out.send([0x80 | ch, e.note, 0], at + stepMs * 0.8);
    }
    btn.textContent = "■";
    btn.onclick = () => { stop(); try { out.send([0xB0 | ch, 123, 0]); } catch {} };
    playTimer = setTimeout(() => { btn.textContent = "▶"; btn.onclick = () => play(i, btn); }, loops * p.steps * stepMs + 200);
  }
  function stop() {
    clearTimeout(playTimer); playTimer = null;
    $$("[data-play]").forEach(b => { b.textContent = "▶"; b.onclick = () => play(+b.dataset.play, b); });
    if (MIDI.out) try { MIDI.out.clear?.(); MIDI.out.send([0xB0 | ((st.part - 1) & 15), 123, 0]); } catch {}
  }

  $("#tkit").value = st.kit; $("#ttaal").value = st.taal; $("#tpart").value = st.part; $("#tbpm").value = bpm();
  $("#tkit").onchange = () => { st.kit = $("#tkit").value; drawMap(); drawPats(); };
  $("#tpart").onchange = () => { st.part = +$("#tpart").value; };
  $("#ttaal").onchange = () => { stop(); st.taal = $("#ttaal").value; st.bpm = null; $("#tbpm").value = bpm(); drawPats(); };
  $("#tbpm").onchange = () => { const v = +$("#tbpm").value; st.bpm = v >= 30 && v <= 300 ? v : null; $("#tbpm").value = bpm(); };
  $("#tsave").onclick = save;
  $("#treset").onclick = () => { if (confirm("Reset this taal's 8 patterns to the starting versions?")) { delete st.edits[st.taal]; drawPats(); } };
  $("#tloadkit").onclick = async () => {
    const perf = KIT_PRESETS[st.kit].perf;
    if (!perf) return toast("Load your own tabla kit on the MODX by hand (it's in your User bank).");
    const out = await MIDI.ensure(); if (!out) return;
    presetMsgs(perf, (st.part - 1) & 15, 63).forEach(m => out.send(m));
    toast(`Loaded Hands Kit into Part ${st.part}`);
  };
  $("#tzip").onclick = () => {
    const files = SCENE_NAMES.map((_, i) => ({name: fileName(i), data: buildMidi(patternEvents(text(i), taal(), map()), taal(), bpm(), (st.part - 1) & 15)}));
    download(buildZip(files), `${fileSafe(st.taal)}-tabla-scenes.zip`);
  };
  drawMap(); drawPats();
  cleanup = () => stop();
}
