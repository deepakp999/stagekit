/* StageKit front end — library, stem mixer, song cards, set lists, live mode. No build step. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const view = $("#view");
let cleanup = null;   // called when leaving a view
let pollTimer = null;

const METERS = ["4/4", "3/4", "6/8", "12/8", "2/4", "5/4", "7/8"];
const STEM_LABEL = {vocals: "Vocals", drums: "Drums", bass: "Bass", other: "Other", instrumental: "Instrumental", original: "Original"};
const TYPICAL = [["Intro", 1], ["Verse", 2], ["Chorus", 4], ["Interlude", 5], ["Verse", 2], ["Chorus", 4], ["Ending", 8]];

function toast(msg, ms = 2600) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), ms);
}

async function api(path, opts = {}) {
  const o = {credentials: "same-origin", ...opts};
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers = {"Content-Type": "application/json"}; delete o.json; }
  const r = await fetch("api/" + path, o);
  if (r.status === 401) { showLogin(); throw new Error("Login required"); }
  if (r.status === 503 && path !== "health") { const d = await r.json().catch(() => ({})); if (d.detail && !d.offline) { showLogin(d.detail); throw new Error("Login required"); } }
  let data = null;
  try { data = await r.json(); } catch { /* empty body */ }
  if (!r.ok) throw new Error((data && (data.detail?.[0]?.msg || data.detail)) || `Error ${r.status}`);
  return data;
}

const fmtTime = s => { s = Math.max(0, s || 0); return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`; };
const busy = s => ["queued", "downloading", "separating", "analysing"].includes(s);
const statusChip = s => {
  const map = {ready: ["ready", "Ready"], error: ["error", "Failed"], queued: ["busy", "Queued"],
    downloading: ["busy", "Downloading"], separating: ["busy", "Separating"], analysing: ["busy", "Analysing"]};
  const [cls, txt] = map[s.status] || ["", s.status];
  return `<span class="chip ${cls}">${txt}</span>`;
};
const thumb = s => s.youtube_id
  ? `<div class="thumb" style="background-image:url(https://i.ytimg.com/vi/${esc(s.youtube_id)}/mqdefault.jpg)"></div>`
  : `<div class="thumb">♪</div>`;

// ---------------- routing ----------------

function setNav(name) { $$(".top nav a").forEach(a => a.classList.toggle("on", a.dataset.nav === name)); }

async function route() {
  if (cleanup) { try { cleanup(); } catch {} cleanup = null; }
  clearInterval(pollTimer);
  document.body.classList.remove("live");
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  try {
    if (parts[0] === "song" && parts[1]) { setNav("library"); await songView(parts[1]); }
    else if (parts[0] === "sets" && parts[1]) { setNav("sets"); await setEditView(parts[1]); }
    else if (parts[0] === "sets") { setNav("sets"); await setsView(); }
    else if (parts[0] === "live") { await liveView(parts[1], parts[2]); }
    else if (parts[0] === "tabla") { setNav("tabla"); await tablaView(); }
    else { setNav("library"); await libraryView(); }
  } catch (e) {
    if (e.message !== "Login required") view.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);

function showLogin(msg) {
  clearInterval(pollTimer);
  document.body.classList.remove("live");
  $("#logout").hidden = true; $(".top nav").hidden = true;
  view.innerHTML = `
    <div class="panel login">
      <img src="icon.svg" alt="" width="44" height="44">
      <h1>StageKit</h1>
      <form id="lf">
        <label class="f" for="un">Username</label>
        <input id="un" type="text" autocomplete="username" autocapitalize="none" spellcheck="false" required>
        <label class="f" for="pw" style="margin-top:10px">Password</label>
        <input id="pw" type="password" autocomplete="current-password" required>
        <div class="err small" id="lerr">${esc(msg || "")}</div>
        <button class="btn primary" style="width:100%;margin-top:12px">Sign in</button>
      </form>
    </div>`;
  $("#un").focus();
  $("#lf").onsubmit = async e => {
    e.preventDefault();
    const btn = $("#lf button"); btn.disabled = true;
    try {
      const r = await fetch("api/login", {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({username: $("#un").value, password: $("#pw").value})});
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || "Sign-in failed");
      $("#logout").hidden = false; $(".top nav").hidden = false; route();
    } catch (err) { $("#lerr").textContent = err.message; $("#pw").value = ""; $("#pw").focus(); }
    btn.disabled = false;
  };
}

$("#logout").onclick = async e => {
  e.preventDefault();
  await fetch("api/logout", {method: "POST", credentials: "same-origin"}).catch(() => {});
  try { Object.keys(localStorage).filter(k => k.startsWith("sk_live_cache")).forEach(k => localStorage.removeItem(k)); } catch {}
  if (window.caches) caches.delete("stagekit-data-v1").catch(() => {});
  showLogin("Signed out.");
};

// ---------------- library ----------------

async function libraryView() {
  view.innerHTML = `
    <h1>Library</h1>
    <div class="panel">
      <form class="add" id="addf">
        <input id="url" type="url" placeholder="Paste a YouTube link" autocomplete="off" required>
        <button class="btn primary">Add song</button>
      </form>
      <label class="quick"><input type="checkbox" id="quick"> <span><b>Chords only</b> — playable chords in about a minute; make stems later if you need them</span></label>
      <label class="drop" id="drop">Or drop an audio file here, or <u>choose a file</u>
        <input id="file" type="file" accept="audio/*,video/*,.flac,.m4a,.aif,.aiff" hidden></label>
      <div class="small muted" style="margin-top:8px">Stems are made with UVR models on the server. On CPU this takes a few minutes per song — you can leave the page.</div>
    </div>
    <div class="list" id="songs"><div class="empty">Loading…</div></div>`;

  $("#addf").onsubmit = async e => {
    e.preventDefault();
    try { await api("songs", {method: "POST", json: {url: $("#url").value.trim(), quick: $("#quick").checked}}); $("#url").value = ""; toast("Added — processing in the background"); load(); }
    catch (err) { toast(err.message, 4000); }
  };
  const upload = async f => {
    if (!f) return;
    const fd = new FormData(); fd.append("file", f); fd.append("quick", $("#quick").checked);
    toast(`Uploading ${f.name}…`, 60000);
    try { await api("songs/upload", {method: "POST", body: fd}); toast("Uploaded — processing in the background"); load(); }
    catch (err) { toast(err.message, 4000); }
  };
  $("#file").onchange = e => upload(e.target.files[0]);
  const drop = $("#drop");
  drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); upload(e.dataTransfer.files[0]); };

  async function load() {
    const songs = await api("songs");
    const box = $("#songs");
    if (!box) return;
    box.innerHTML = songs.length ? songs.map(s => `
      <a class="item" href="#/song/${s.id}">
        ${thumb(s)}
        <div class="grow">
          <div class="title">${esc(s.title)}</div>
          <div class="chips">${statusChip(s)}${s.quick ? `<span class="chip">Chords only</span>` : ""}
            ${s.card.key ? `<span class="chip">${esc(s.card.key)}</span>` : ""}
            ${s.card.bpm ? `<span class="chip">${esc(s.card.bpm)} BPM</span>` : ""}
            ${s.card.meter ? `<span class="chip">${esc(s.card.meter)}</span>` : ""}
            ${s.card.sections?.length ? `<span class="chip">${s.card.sections.length} sections</span>` : ""}
          </div>
          ${busy(s.status) ? `<div class="small muted" style="margin-top:4px">${esc(s.stage)}</div><div class="bar"><i style="width:${Math.round(s.progress * 100)}%"></i></div>` : ""}
          ${s.status === "error" ? `<div class="small" style="color:var(--danger);margin-top:4px">${esc(s.error)}</div>` : ""}
        </div>
      </a>`).join("") : `<div class="empty">No songs yet. Paste a YouTube link above to start.</div>`;
    clearInterval(pollTimer);
    if (songs.some(s => busy(s.status))) pollTimer = setInterval(load, 4000);
  }
  await load();
}

// ---------------- chords ----------------

const FLAT_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
const PC = {C: 0, "B#": 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, Fb: 4, F: 5, "E#": 5, "F#": 6, Gb: 6, G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11, Cb: 11};
function transposeChord(ch, n) {
  if (!ch || ch === "N.C.") return ch;
  return ch.replace(/\b([A-G](?:#|b)?)/g, r => r in PC ? FLAT_NAMES[(PC[r] + n % 12 + 12) % 12] : r);
}
// Chords between two times, repeated neighbours collapsed: "Am F C G".
function chordsBetween(list, t0, t1, n) {
  const seq = [];
  for (const c of list) {
    if (c.t + c.d <= t0 + 0.2 || c.t >= t1 - 0.2 || c.c === "N.C.") continue;
    const name = transposeChord(c.c, n);
    if (seq[seq.length - 1] !== name) seq.push(name);
  }
  return seq.slice(0, 16).join("  ");
}

// ---------------- stem mixer ----------------

class Mixer {
  // Streams each stem with an <audio> element (no full decode, so tablets don't run out of memory)
  // and keeps them in sync against the first track.
  constructor(sid, stems, el) {
    this.sid = sid; this.el = el;
    // Instrumental duplicates drums+bass+other, and original is the full mix: both start muted.
    this.tracks = [...stems, "original"].map(name => ({name, a: null, vol: 1,
      mute: name === "instrumental" || (name === "original" && stems.length > 0), solo: false}));
    this.onTick = null; this.playing = false; this.duration = 0;
    this.render(); this.load();
  }
  render() {
    this.el.innerHTML = `
      <div class="transport">
        <button class="play" id="mxplay" aria-label="Play" disabled>▶</button>
        <input class="seek" id="mxseek" type="range" min="0" max="1000" value="0" disabled aria-label="Position">
        <span class="time" id="mxtime">Loading…</span>
      </div>
      ${this.tracks.map((t, i) => `
        <div class="stem" style="--c:var(--${t.name})">
          <span class="n">${STEM_LABEL[t.name]}</span>
          <button class="tog m ${t.mute ? "on" : ""}" data-i="${i}" data-k="mute" aria-label="Mute ${t.name}">M</button>
          <button class="tog s" data-i="${i}" data-k="solo" aria-label="Solo ${t.name}">S</button>
          <input type="range" min="0" max="1" step="0.01" value="1" data-i="${i}" aria-label="${t.name} volume">
          ${t.name === "original" && this.tracks.length === 1 ? "<span></span>" : `<span class="dl"><a href="api/songs/${this.sid}/stem/${t.name}.mp3" download title="MP3, ~1.4 MB per minute">MP3</a><a href="api/songs/${this.sid}/stem/${t.name}.wav" download title="WAV, full quality, ~10 MB per minute">WAV</a></span>`}
        </div>`).join("")}`;
    $$(".tog", this.el).forEach(b => b.onclick = () => {
      const t = this.tracks[b.dataset.i]; t[b.dataset.k] = !t[b.dataset.k];
      b.classList.toggle("on", t[b.dataset.k]); this.applyGains();
    });
    $$(".stem input", this.el).forEach(r => r.oninput = () => { this.tracks[r.dataset.i].vol = +r.value; this.applyGains(); });
    $("#mxplay", this.el).onclick = () => this.playing ? this.pause() : this.play();
    const seek = $("#mxseek", this.el);
    seek.oninput = () => { this.seeking = true; $("#mxtime", this.el).textContent = `${fmtTime(seek.value / 1000 * this.duration)} / ${fmtTime(this.duration)}`; };
    seek.onchange = () => { this.seeking = false; this.seek(seek.value / 1000 * this.duration); };
  }
  msg(text) { if (!this.dead) $("#mxtime", this.el).textContent = text; }
  load() {
    let ready = 0;
    for (const t of this.tracks) {
      const a = new Audio(); t.a = a;
      a.preload = "auto";
      a.addEventListener("loadedmetadata", () => {
        ready++; this.msg(`Loading ${ready}/${this.tracks.length}`);
        if (ready === this.tracks.length) this.ready();
      }, {once: true});
      a.addEventListener("error", () => this.msg(`Could not load ${STEM_LABEL[t.name] || t.name} (${a.error?.code || "?"}) — reload the page`));
      a.addEventListener("ended", () => { if (t === this.tracks[0]) { this.pause(); this.seek(0); } });
      a.src = `api/songs/${this.sid}/preview/${t.name}.mp3`;
    }
  }
  ready() {
    if (this.dead) return;
    this.duration = Math.max(...this.tracks.map(t => t.a.duration || 0));
    this.applyGains();
    $("#mxplay", this.el).disabled = false; $("#mxseek", this.el).disabled = false;
    this.tick();
  }
  applyGains() {
    const anySolo = this.tracks.some(t => t.solo);
    for (const t of this.tracks) {
      if (!t.a) continue;
      const on = anySolo ? t.solo && !t.mute : !t.mute;
      t.a.muted = !on; t.a.volume = Math.max(0, Math.min(1, t.vol));
    }
  }
  pos() { return this.tracks[0]?.a?.currentTime || 0; }
  async play() {
    const p = this.pos();
    for (const t of this.tracks) if (Math.abs(t.a.currentTime - p) > 0.03) t.a.currentTime = p;
    this.playing = true; $("#mxplay", this.el).textContent = "❚❚";
    try { await Promise.all(this.tracks.map(t => t.a.play())); }
    catch (e) { this.pause(); this.msg(`Playback blocked: ${e.message}`); }
  }
  pause() {
    for (const t of this.tracks) t.a?.pause();
    this.playing = false; $("#mxplay", this.el).textContent = "▶";
  }
  seek(s) { for (const t of this.tracks) if (t.a) t.a.currentTime = s; this.tick(true); }
  tick(once) {
    if (this.dead) return;
    const p = this.pos();
    // Keep stems locked to the first track; nudge any that drift by more than ~60 ms.
    if (this.playing && !once) for (const t of this.tracks.slice(1)) {
      if (!t.a.paused && Math.abs(t.a.currentTime - p) > 0.06) t.a.currentTime = p;
    }
    this.onTick?.(p);
    if (!this.seeking) {
      $("#mxseek", this.el).value = this.duration ? Math.round(p / this.duration * 1000) : 0;
      $("#mxtime", this.el).textContent = `${fmtTime(p)} / ${fmtTime(this.duration)}`;
    }
    if (!once) requestAnimationFrame(() => this.tick());
  }
  destroy() { this.dead = true; for (const t of this.tracks) if (t.a) { t.a.pause(); t.a.removeAttribute("src"); t.a.load(); } }
}

// ---------------- MODX sound finder ----------------

// Factory Performance n → Bank MSB 65 (whole multi-part Performance), LSB = bank of 128, Program = position.
// From the MODX M Data List (MIDI Data Format, Bank Select table).
// MSB 63 instead loads only Part 1 of that preset into the Part listening on this channel.
function presetMsgs(n, ch, msb = 65) {
  const i = (n - 1) | 0;
  return [[0xB0 | ch, 0, msb], [0xB0 | ch, 32, (i >> 7) & 127], [0xC0 | ch, i & 127]];
}
// MIDI outside live view (auditioning presets). Uses the same saved port/channel.
const MIDI = {
  access: null, out: null,
  async ensure() {
    if (this.out && this.out.state !== "disconnected") return this.out;
    if (!navigator.requestMIDIAccess) { toast("This browser has no Web MIDI. Use Chrome or Edge."); return null; }
    try { this.access = this.access || await navigator.requestMIDIAccess({sysex: true}); } catch { toast("MIDI permission was refused (allow 'full MIDI control' for scene sending)."); return null; }
    const ms = midiSettings(), outs = [...this.access.outputs.values()];
    this.out = outs.find(o => o.id === ms.port) || outs.find(o => /modx|yamaha/i.test(o.name)) || outs[0] || null;
    if (!this.out) toast("No MIDI device found. Connect the MODX by USB.");
    return this.out;
  },
  async preset(n) {
    const out = await this.ensure(); if (!out) return;
    const ch = ((midiSettings().channel || 1) - 1) & 15;
    presetMsgs(n, ch).forEach(m => out.send(m));
  },
};

// Yamaha parameter change: F0 43 1n 7F 1C 0D a1 a2 a3 a4 data F7 (MODX M Data List, MIDI Data Format 3-5-3).
const ymh = (addr, data) => [0xF0, 0x43, 0x10, 0x7F, 0x1C, 0x0D, ...addr, ...data, 0xF7];
const d14 = v => [(v >> 7) & 127, v & 127];
// Writes a scene plan into the Performance currently open on the MODX (edit buffer). Nothing is saved until STORE.
// opts.split: MIDI note where the right hand starts (arp Parts only receive notes below it); null = no split.
// opts.lead: {part, sound_no} right-hand Part above the split. opts.othersOff: switch every other Part off.
function scenePlanMessages(plan, tempo, opts = {}) {
  const msgs = [], used = new Set();
  const part1 = (p, off, v) => msgs.push(ymh([0x10 + p, 0x00, 0x01, off], [v]));
  const limits = (p, lo, hi) => { msgs.push(ymh([0x10 + p, 0x00, 0x02, 0x08], [0, lo & 127])); msgs.push(ymh([0x10 + p, 0x00, 0x02, 0x0A], [0, hi & 127])); };
  for (const row of plan.parts) {
    if (!row.part) continue;
    const p = row.part - 1; used.add(p);
    part1(p, 0x00, 1);                                     // Part Switch on
    part1(p, 0x02, 1);                                     // Keyboard Control on (the keys trigger this Part's arps)
    part1(p, 0x47, 1);                                     // Part Arp Switch on
    if (opts.arpOnly !== false) part1(p, 0x48, 1);         // Arp Play Only: only the pattern sounds, not the held keys
    row.scenes.forEach((no, i) => { if (no) msgs.push(ymh([0x10 + p, 0x00, 0x06, 0x44 + 2 * i], d14(no))); }); // Arp 1–8 Number
    if (opts.split != null) limits(p, 0, opts.split - 1);
    else if (opts.resetLimits) limits(p, 0, 127);
  }
  if (opts.lead && opts.lead.part) {
    const p = opts.lead.part - 1; used.add(p);
    part1(p, 0x00, 1); part1(p, 0x02, 1); part1(p, 0x47, 0); part1(p, 0x48, 0);
    limits(p, opts.split != null ? opts.split : 0, 127);
  }
  if (opts.othersOff) for (let p = 0; p < 16; p++) if (!used.has(p)) part1(p, 0x00, 0);
  for (let c = 0; c < 8; c++) {
    msgs.push(ymh([0x06, 0x02, c, 0x00], [1]));      // Scene Arpeggio Master Switch on
    msgs.push(ymh([0x06, 0x02, c, 0x02], [1]));      // Scene Arpeggio Memorize Switch on
    msgs.push(ymh([0x06, 0x03, c, 0x00], [0, c]));   // Scene c+1 → Arp Select c+1
  }
  msgs.push(ymh([0x06, 0x00, 0x01, 0x09], [1]));     // Arpeggio Master Switch on
  if (tempo) msgs.push(ymh([0x06, 0x00, 0x02, 0x1E], d14(Math.round(Math.min(300, Math.max(5, tempo)))))); // Tempo
  msgs.push(ymh([0x06, 0x00, 0x02, 0x2A], [0, 0])); // Select Scene 1 so you start at the intro
  return msgs;
}

// Loads sounds (optional) then writes the plan into the Performance open on the MODX. Returns true on success.
async function sendPlanToModx(plan, bpm, opts = {}) {
  const out = await MIDI.ensure(); if (!out) return false;
  if (!/modx|yamaha|montage/i.test(out.name) && !confirm(`The MIDI output is "${out.name}", not a MODX. Send anyway?`)) return false;
  if (!confirm("This changes the Performance currently open on your MODX (sounds, arps, scenes" + (opts.othersOff ? ", other Parts off" : "") +
    "). Nothing is saved until you press STORE; reloading the Performance undoes it. Continue?")) return false;
  const wait = ms => new Promise(r => setTimeout(r, ms));
  try {
    if (opts.withSounds !== false) {
      // Single Part bank select (MSB 63) on each Part's channel replaces just that Part's sound (MIDI I/O Mode: Multi).
      for (const r of plan.parts) if (r.part && r.sound_no) presetMsgs(r.sound_no, r.part - 1, 63).forEach(m => out.send(m));
      if (opts.lead && opts.lead.part && opts.lead.sound_no) presetMsgs(opts.lead.sound_no, opts.lead.part - 1, 63).forEach(m => out.send(m));
      await wait(1200); // let the MODX finish loading sounds before setting Part parameters
    }
    for (const m of scenePlanMessages(plan, bpm, opts)) { out.send(m); await wait(12); }
    toast("Sent. Hold a chord" + (opts.split != null ? " with your left hand" : "") + " and try scenes 1–8; press STORE on the MODX to keep it.", 7000);
    return true;
  } catch (e) { toast("Sending failed: " + e.message + " — allow full MIDI (SysEx) access in Chrome.", 7000); return false; }
}

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const noteName = n => `${NOTE_NAMES[n % 12]}${Math.floor(n / 12) - 2}`;   // Yamaha: C3 = 60
const SPLIT_CHOICES = [null, 48, 53, 54, 55, 60];

// ---------------- Auto-build ----------------

const AUTO_FEELS = [["", "Auto"], ["pop", "Pop / rock"], ["ballad", "Ballad"], ["devotional", "Devotional"], ["cinematic", "Cinematic"], ["dance", "Dance"], ["indian", "Indian"]];

async function openAutoBuild({sid, meter, bpm, onApply}) {
  const prefs = (() => { try { return JSON.parse(localStorage.getItem("sk_auto") || "{}"); } catch { return {}; } })();
  const st = {feel: prefs.feel || "", split: prefs.split === undefined ? 54 : prefs.split, lead: prefs.lead || {no: 3, name: "CFX Concert"},
    tabla: prefs.tabla || {use: false, first: 1, kit: 2813}, othersOff: prefs.othersOff !== false, useSections: true};
  const savePrefs = () => { try { localStorage.setItem("sk_auto", JSON.stringify({feel: st.feel, split: st.split, lead: st.lead, tabla: st.tabla, othersOff: st.othersOff})); } catch {} };
  const dlg = document.createElement("dialog"); dlg.className = "mdlg finder";
  dlg.innerHTML = `<div class="row"><h2 class="grow" style="margin:0">✨ Auto-build</h2><button class="btn sm" id="ax" aria-label="Close">✕</button></div>
    <div id="abody"><div class="empty">Listening to the song… the first time takes up to a minute.</div></div>`;
  document.body.appendChild(dlg);
  $("#ax", dlg).onclick = () => dlg.close();
  dlg.addEventListener("close", () => dlg.remove());
  dlg.showModal();
  let r = null, chosen = null, plan = null;

  const load = async refresh => {
    try { r = await api(`songs/${sid}/autobuild`, {method: "POST", json: {feel: st.feel, refresh: !!refresh}}); }
    catch (e) { $("#abody", dlg).innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    chosen = r.styles[0]?.family || null;
    plan = r.plan ? toPlan(r.plan) : null;
    draw();
  };
  const toPlan = p => ({family: p.family, ts: p.ts, tempo: p.tempo, parts: p.parts.map((x, i) => ({
    cat: x.cat, label: x.label, sound: x.sound, sound_no: x.sound_no, sound_name: x.sound_name,
    names: x.scenes.map(y => y && y.name), scenes: x.scenes.map(y => y && y.no), part: i < 4 ? i + 1 : 0}))});
  const applyTabla = p => {
    if (!st.tabla.use || !p) return p;
    const drums = p.parts.find(x => x.cat === "Dr/Pc");
    if (!drums) return p;
    const first = 12032 + Math.max(0, Math.min(255, (st.tabla.first || 1) - 1));   // User arpeggio numbers start at 12032
    return {...p, parts: p.parts.map(x => x !== drums ? x : {...x, label: "Tabla (your arps)", sound: null,
      sound_no: st.tabla.kit || 2813, sound_name: st.tabla.kit === 2813 ? "Hands Kit" : `Preset #${st.tabla.kit}`,
      scenes: x.scenes.map((_, i) => first + i), names: x.scenes.map((_, i) => `User ${st.tabla.first + i}`)})};
  };

  function draw() {
    const g = r.groove;
    const finalPlan = applyTabla(plan);
    const leadPart = finalPlan ? Math.min(8, finalPlan.parts.filter(x => x.part).length + 1) : 5;
    dlg._final = {plan: finalPlan, leadPart};
    $("#abody", dlg).innerHTML = `
      <div class="small muted" style="margin:6px 0 10px">${esc(r.meter)} · ${r.bpm ? esc(r.bpm) + " BPM · " : ""}${g ? `${esc(g.feel)} ${esc(g.subdivision)}s · ${esc(g.busy)} drums` : "groove not detected"}
        ${r.used_drum_stem ? "" : " · <span title='Make stems for a better groove reading'>no drum stem (chords-only song)</span>"}
        · <a href="#" id="arefresh">re-analyse</a></div>
      <div class="chipsel" id="afeel">${AUTO_FEELS.map(([k, v]) => `<button class="chipb ${k === st.feel ? "on" : ""}" data-f="${k}">${v}</button>`).join("")}</div>
      <div class="fcols acols" style="margin-top:12px">
        <div>
          <h3>Groove style</h3>
          <div class="flist" id="astyles" style="max-height:38vh">${r.styles.map((x, i) => `<label class="frow sbtn ${x.family === chosen ? "on" : ""}"><input type="radio" name="ast" value="${esc(x.family)}" ${x.family === chosen ? "checked" : ""}>
            <span class="grow"><b>${esc(x.family)}</b>${i === 0 ? ' <span class="chip ready">best match</span>' : ""}<br>
            <span class="small muted">${esc(x.ts)} · ${x.tempo} BPM · ${esc(x.instruments.join(", "))}</span><br>
            <span class="small">${esc(x.why.join(" · ") || "—")}</span></span></label>`).join("") || '<div class="muted small">No styles in this meter.</div>'}</div>
          <h3 style="margin-top:12px">Playing setup</h3>
          <label class="f">Split point (left hand plays the band)</label>
          <select id="asplit">${SPLIT_CHOICES.map(n => `<option value="${n ?? ""}" ${n === st.split ? "selected" : ""}>${n == null ? "No split — whole keyboard" : `${noteName(n)} — left hand below`}</option>`).join("")}</select>
          <label class="f" style="margin-top:8px">Right-hand sound (Part ${leadPart})</label>
          <div class="row"><span class="grow" id="alead">${st.split == null ? '<span class="muted">— no split</span>' : `${esc(st.lead.name)} <span class="muted">#${st.lead.no}</span>`}</span>
            <button class="btn sm" id="aleadpick" ${st.split == null ? "disabled" : ""}>Change</button></div>
          ${st.feel === "indian" ? `<label class="chk"><input type="checkbox" id="atabla" ${st.tabla.use ? "checked" : ""}> Use my tabla arps for drums: User arp
            <input id="atfirst" type="number" min="1" max="249" value="${st.tabla.first}" style="width:60px"> onwards</label>
            <div class="small muted">Make them in the Tabla tab (S1–S8 → 8 consecutive user arps).</div>` : ""}
          <label class="chk"><input type="checkbox" id="aoff" ${st.othersOff ? "checked" : ""}> Switch off all other Parts</label>
        </div>
        <div>
          <h3>Plan</h3>
          ${finalPlan ? `<div class="ptable"><table class="sec plan"><thead><tr><th>Part</th><th>Instrument</th><th>Sound</th>${["Intro", "Main A", "Main B", "Main C", "Fill A", "Fill B", "Break", "Ending"].map((n, i) => `<th>S${i + 1}<br><span class="muted">${n}</span></th>`).join("")}</tr></thead><tbody>
            ${finalPlan.parts.filter(x => x.part).map(x => `<tr><td>${x.part}</td><td><b>${esc(x.label)}</b></td><td class="small">${esc(x.sound_name || "–")}</td>${x.scenes.map(n => `<td class="an">${n || "–"}</td>`).join("")}</tr>`).join("")}
            ${st.split != null ? `<tr><td>${leadPart}</td><td><b>Right hand</b></td><td class="small">${esc(st.lead.name)}</td><td colspan="8" class="small muted">plays from ${noteName(st.split)} up, no arp</td></tr>` : ""}
          </tbody></table></div>` : '<div class="muted small">No plan.</div>'}
          <h3 style="margin-top:14px">Sections → scenes</h3>
          ${r.sections.length ? `<table class="sec"><thead><tr><th>Section</th><th>Starts</th><th>Scene</th><th>Chords</th></tr></thead><tbody>
            ${r.sections.map(x => `<tr><td><b>${esc(x.name)}</b>${x.cue ? `<br><span class="small muted">${esc(x.cue)}</span>` : ""}</td><td>${fmtTime(x.start)}</td><td>S${x.scene}</td><td class="small">${esc(x.chords || "")}</td></tr>`).join("")}
          </tbody></table>
          <label class="chk"><input type="checkbox" id="asecs" ${st.useSections ? "checked" : ""}> Replace the song's sections with these</label>` : '<div class="muted small">Song too short to find sections.</div>'}
          <div class="row" style="margin-top:14px"><span class="grow"></span>
            <button class="btn" id="aapply">Apply to song</button>
            <button class="btn primary" id="asend">Apply &amp; send to MODX</button></div>
        </div>
      </div>`;
    $("#arefresh", dlg).onclick = e => { e.preventDefault(); $("#abody", dlg).innerHTML = '<div class="empty">Re-analysing…</div>'; load(true); };
    $$("#afeel .chipb", dlg).forEach(b => b.onclick = () => { st.feel = b.dataset.f; savePrefs(); $("#abody", dlg).innerHTML = '<div class="empty">Matching styles…</div>'; load(false); });
    $$("input[name=ast]", dlg).forEach(i => i.onchange = async () => {
      chosen = i.value; plan = toPlan(await api(`modx/scene-plan?family=${encodeURIComponent(chosen)}`)); draw();
    });
    $("#asplit", dlg).onchange = e => { st.split = e.target.value === "" ? null : +e.target.value; savePrefs(); draw(); };
    $("#aleadpick", dlg).onclick = () => openFinder({meter, bpm, onUse: p => { st.lead = {no: p.no, name: p.name}; savePrefs(); draw(); }, onArp: () => {}});
    $("#aoff", dlg).onchange = e => { st.othersOff = e.target.checked; savePrefs(); };
    $("#atabla", dlg)?.addEventListener("change", e => { st.tabla.use = e.target.checked; savePrefs(); draw(); });
    $("#atfirst", dlg)?.addEventListener("change", e => { st.tabla.first = Math.max(1, Math.min(249, +e.target.value || 1)); savePrefs(); draw(); });
    $("#asecs", dlg)?.addEventListener("change", e => { st.useSections = e.target.checked; });
    const result = () => ({plan: dlg._final.plan, sections: st.useSections ? r.sections : null,
      opts: {split: st.split, lead: st.split != null ? {part: dlg._final.leadPart, sound_no: st.lead.no, name: st.lead.name} : null,
        othersOff: st.othersOff, withSounds: true, resetLimits: st.split == null}});
    $("#aapply", dlg).onclick = async () => { await onApply(result(), false); dlg.close(); };
    $("#asend", dlg).onclick = async () => {
      const res = result();
      if (!res.plan) return toast("No plan to send");
      if (await sendPlanToModx(res.plan, bpm || r.bpm, res.opts)) { await onApply(res, true); dlg.close(); }
    };
  }
  await load(false);
}

async function openScenePlan({meter = "4/4", bpm = null, current = null, onSave}) {
  const dlg = document.createElement("dialog"); dlg.className = "mdlg finder";
  dlg.innerHTML = `
    <div class="row"><h2 class="grow" style="margin:0">Build scenes</h2><button class="btn sm" id="sx" aria-label="Close">✕</button></div>
    <div class="small muted" style="margin:4px 0 10px">Pick a groove style. Its drums, bass, guitar and keys arpeggios are laid out across your 8 scenes: intro, three main grooves, two fills, break and ending.</div>
    <div class="row"><input id="sq" type="text" class="grow" placeholder="Search styles: ballad, rock, 12/8, unplugged…">
      <label class="chk" style="margin:0"><input type="checkbox" id="sall"> All meters</label></div>
    <div class="fcols" style="margin-top:10px;grid-template-columns:260px 1fr">
      <div><h3>Styles <span class="muted small" id="scount"></span></h3><div id="slist" class="flist"></div></div>
      <div id="splan"><div class="muted small" style="padding:20px 0">Choose a style on the left.</div></div>
    </div>`;
  document.body.appendChild(dlg);
  let plan = null;
  const loadStyles = async () => {
    const q = $("#sq", dlg).value.trim(), all = $("#sall", dlg).checked;
    const list = await api(`modx/styles?q=${encodeURIComponent(q)}${all ? "" : `&meter=${encodeURIComponent(meter)}`}${bpm ? `&bpm=${bpm}` : ""}`);
    $("#scount", dlg).textContent = `${list.length} · ${all ? "all meters" : meter}`;
    $("#slist", dlg).innerHTML = list.map(st => `<button class="frow sbtn" data-fam="${esc(st.family)}"><span class="grow" style="text-align:left"><b>${esc(st.family)}</b><br>
      <span class="small muted">${esc(st.ts)} · ${st.tempo} BPM · ${esc(st.instruments.join(", "))}</span></span></button>`).join("")
      || `<div class="muted small">No styles in ${esc(meter)}. Tick "All meters".</div>`;
    $$(".sbtn", dlg).forEach(b => b.onclick = () => { $$(".sbtn", dlg).forEach(x => x.classList.toggle("on", x === b)); showPlan(b.dataset.fam); });
  };
  const showPlan = async fam => {
    const p = await api(`modx/scene-plan?family=${encodeURIComponent(fam)}`);
    const saved = current && current.family === fam ? current : null;
    plan = {family: p.family, ts: p.ts, tempo: p.tempo, parts: p.parts.map((r, i) => ({
      cat: r.cat, label: r.label, sound: r.sound, sound_no: r.sound_no, sound_name: r.sound_name, names: r.scenes.map(x => x && x.name),
      scenes: r.scenes.map(x => x && x.no), part: saved?.parts.find(s => s.cat === r.cat)?.part ?? (i < 4 ? i + 1 : 0)}))};
    const big = plan.parts.some(r => r.scenes.some(n => n > 10239));
    $("#splan", dlg).innerHTML = `
      <h3>${esc(p.family)} <span class="muted small">${esc(p.ts)} · original ${p.tempo} BPM${bpm ? ` · song ${bpm} BPM` : ""}</span></h3>
      <div class="ptable"><table class="sec plan"><thead><tr><th>Instrument</th><th>Part</th><th>Sound</th>${p.scenes.map((n, i) => `<th>S${i + 1}<br><span class="muted">${esc(n)}</span></th>`).join("")}</tr></thead><tbody>
      ${plan.parts.map((r, k) => `<tr><td><b>${esc(r.label)}</b>${r.sound ? `<br><span class="small muted">${esc(r.sound)}</span>` : ""}</td>
        <td><select data-k="${k}" aria-label="Part for ${esc(r.label)}"><option value="0">skip</option>${[1, 2, 3, 4, 5, 6, 7, 8].map(n => `<option ${r.part === n ? "selected" : ""}>${n}</option>`).join("")}</select></td>
        <td class="small">${r.sound_no ? `${esc(r.sound_name)}<br><span class="muted">#${r.sound_no}</span>` : "–"}</td>
        ${r.scenes.map((no, i) => `<td class="an" title="${esc(r.names[i] || "")}">${no || "–"}<br><span class="muted">${esc((r.names[i] || "").split("_")[0])}</span></td>`).join("")}</tr>`).join("")}
      </tbody></table></div>
      <div class="small muted" style="margin-top:8px">Numbers are arpeggio types. Make sure the Performance's Parts hold matching sounds (Part 1 a drum kit, Part 2 a bass, …).</div>
      ${big ? `<div class="fnote" style="margin-top:6px">Some arps are numbered above 10239; the Data List only documents 1–10239 for presets, so check those on the keyboard.</div>` : ""}
      <label class="chk"><input type="checkbox" id="psnd" checked> Also load these sounds into the Parts <span class="muted small">(MODX: Utility → MIDI I/O Mode = Multi)</span></label>
      <div class="row" style="margin-top:12px">
        <button class="btn" id="psave">Save plan to song</button>
        <button class="btn primary" id="psend">Send to MODX (experimental)</button>
      </div>`;
    $$("#splan select", dlg).forEach(sel => sel.onchange = () => { plan.parts[+sel.dataset.k].part = +sel.value; });
    $("#psave", dlg).onclick = () => { onSave(plan); dlg.close(); };
    $("#psend", dlg).onclick = async () => {
      if (await sendPlanToModx(plan, bpm, {withSounds: $("#psnd", dlg).checked})) { onSave(plan); dlg.close(); }
    };
  };
  let t = null;
  $("#sq", dlg).oninput = () => { clearTimeout(t); t = setTimeout(loadStyles, 250); };
  $("#sall", dlg).onchange = loadStyles;
  $("#sx", dlg).onclick = () => dlg.close();
  dlg.addEventListener("close", () => dlg.remove());
  dlg.showModal(); await loadStyles();
  if (current?.family) { const b = $(`.sbtn[data-fam="${CSS.escape(current.family)}"]`, dlg); if (b) b.click(); }
}

let finderFeel = (() => { try { return localStorage.getItem("sk_feel") || "indian"; } catch { return "indian"; } })();

async function openFinder({meter = "4/4", bpm = null, onUse, onArp}) {
  const cats = await api("modx/categories");
  const dlg = document.createElement("dialog"); dlg.className = "mdlg finder";
  dlg.innerHTML = `
    <div class="row"><h2 class="grow" style="margin:0">Find a sound</h2><button class="btn sm" id="fx" aria-label="Close">✕</button></div>
    <div class="small muted" style="margin:4px 0 10px">${cats.counts.performances.toLocaleString()} factory Performances · ${cats.counts.arpeggios.toLocaleString()} arpeggios · song: ${esc(meter)}${bpm ? ` · ${esc(bpm)} BPM` : ""}</div>
    <div class="chipsel" id="feels">${Object.entries(cats.feels).map(([k, v]) => `<button class="chipb ${k === finderFeel ? "on" : ""}" data-f="${k}">${esc(v)}</button>`).join("")}</div>
    <input id="fq" type="text" placeholder="Or search by name or category: tabla, sitar, strings, pad…" style="margin:10px 0">
    <div id="fnote" class="fnote"></div>
    <div class="fcols">
      <div><h3>Performances</h3><div id="fperf" class="flist"></div></div>
      <div><h3>Groove ideas <span class="muted small">— set these arps in your scenes</span></h3><div id="farp" class="flist"></div></div>
    </div>`;
  document.body.appendChild(dlg);
  const perfRow = p => `<div class="frow"><span class="no">${p.no}</span><span class="grow"><b>${esc(p.name)}</b><br><span class="small muted">${esc(p.main)} · ${esc(p.sub)}</span></span>
      <button class="btn sm" data-try="${p.no}">▶ Try</button><button class="btn primary sm" data-use="${p.no}">Use</button></div>`;
  const arpRow = (a, i) => `<div class="frow"><span class="no">${a.no}</span><span class="grow"><b>${esc(a.family || a.name)}</b><br><span class="small muted">${esc(a.cat)} · ${esc(a.sub)} · ${esc(a.ts)} · ${a.tempo} BPM${a.sound ? " · " + esc(a.sound) : ""}</span></span>
      <button class="btn sm" data-arp="${i}">+ Notes</button></div>`;
  let perfs = [], arps = [];
  const draw = () => {
    $("#fperf", dlg).innerHTML = perfs.map(perfRow).join("") || `<div class="muted small">No matches.</div>`;
    $("#farp", dlg).innerHTML = arps.map(arpRow).join("") || `<div class="muted small">—</div>`;
    $$("[data-try]", dlg).forEach(b => b.onclick = async () => { await MIDI.preset(+b.dataset.try); if (MIDI.out) toast(`Playing preset ${b.dataset.try} on MODX`); });
    $$("[data-use]", dlg).forEach(b => b.onclick = () => { onUse(perfs.find(p => p.no === +b.dataset.use)); dlg.close(); });
    $$("[data-arp]", dlg).forEach(b => b.onclick = () => onArp(arps[+b.dataset.arp]));
  };
  const loadFeel = async () => {
    const r = await api(`modx/suggest?feel=${encodeURIComponent(finderFeel)}&meter=${encodeURIComponent(meter)}${bpm ? `&bpm=${bpm}` : ""}`);
    perfs = r.performances; arps = r.arpeggios; $("#fnote", dlg).textContent = r.note || ""; draw();
  };
  let t = null;
  $("#fq", dlg).oninput = () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      const q = $("#fq", dlg).value.trim();
      if (!q) return loadFeel();
      [perfs, arps] = await Promise.all([api(`modx/performances?q=${encodeURIComponent(q)}&limit=80`),
        api(`modx/arps?q=${encodeURIComponent(q)}&ts=${encodeURIComponent(meter)}${bpm ? `&bpm=${bpm}` : ""}&limit=40`)]);
      $("#fnote", dlg).textContent = ""; draw();
    }, 250);
  };
  $$("#feels .chipb", dlg).forEach(b => b.onclick = () => {
    finderFeel = b.dataset.f; try { localStorage.setItem("sk_feel", finderFeel); } catch {}
    $$("#feels .chipb", dlg).forEach(x => x.classList.toggle("on", x === b)); $("#fq", dlg).value = ""; loadFeel();
  });
  $("#fx", dlg).onclick = () => dlg.close();
  dlg.addEventListener("close", () => dlg.remove());
  dlg.showModal(); await loadFeel();
}

// ---------------- lyrics with chords over the words ----------------

// Which chord falls on which word: by Whisper word timings when we have them, otherwise spread
// across the line by time. Chords after the line has been sung go on an instrumental row.
function layoutLyrics(lines, chords, tp, roman) {
  const rows = [];
  const timed = lines.filter(l => l.t != null);
  const chordName = c => transposeChord(c.c, tp);
  const first = timed[0]?.t ?? Infinity;
  const intro = chords.filter(c => c.t + (c.d || 0) > 0 && c.t < first - 0.3);
  if (intro.length && timed.length) rows.push({kind: "inst", t: intro[0].t, chords: intro.map(chordName)});
  timed.forEach((l, i) => {
    const next = timed[i + 1]?.t ?? (l.t + 10);
    const text = (roman && l.roman) || l.text || "";
    const words = text.split(/\s+/).filter(Boolean);
    const sung = Math.min(next - l.t, Math.max(2.5, words.length * 0.75 + 1));
    const slots = words.map(() => []);
    const after = [];
    // The chord already sounding when the line starts goes on its first word.
    const active = chords.filter(c => c.t <= l.t + 0.15 && c.t + (c.d || 0) > l.t + 0.15).pop();
    const inLine = chords.filter(c => c.t > l.t + 0.15 && c.t < next - 0.15);
    if (active && words.length) slots[0].push(chordName(active));
    for (const c of inLine) {
      if (c.t > l.t + sung || !words.length) { after.push(chordName(c)); continue; }
      let k;
      if (l.words?.length === words.length && !roman) {
        k = 0; l.words.forEach((w, j) => { if (w.t <= c.t + 0.1) k = j; });
      } else {
        k = Math.min(words.length - 1, Math.floor((c.t - l.t) / sung * words.length));
      }
      if (slots[k].at(-1) !== chordName(c)) slots[k].push(chordName(c));
    }
    rows.push({kind: "line", t: l.t, idx: lines.indexOf(l), words: words.map((w, j) => ({w, c: slots[j].join(" ")}))});
    if (after.length) rows.push({kind: "inst", t: l.t + sung, chords: after});
  });
  return rows;
}

function lyricsPanel(sid, el, getMixer, getTp, canTranscribe) {
  let data = {lines: []}, chords = [], roman = false, tapping = -1, poll = null, dead = false, cur = -1;
  try { roman = localStorage.getItem("sk_roman") === "1"; } catch {}
  api(`songs/${sid}/chords`).then(c => { chords = c; draw(); }).catch(() => {});

  const load = async () => {
    try { data = await api(`songs/${sid}/lyrics`); } catch (e) { data = {lines: [], job: {status: "error", message: e.message}}; }
    draw();
    clearTimeout(poll);
    if (data.job?.status === "running" && !dead) poll = setTimeout(load, 3000);
  };

  const untimed = () => data.lines.length && data.lines.some(l => l.t == null);

  function draw() {
    if (dead) return;
    const tp = getTp(), job = data.job, has = data.lines.length > 0;
    const src = {lrclib: `LRCLIB${data.match ? ` · ${data.match}` : ""}`, whisper: `transcribed${data.language ? ` (${data.language})` : ""}`, pasted: "pasted"}[data.source] || "";
    el.innerHTML = `
      <div class="row"><b class="grow">Lyrics + chords ${src ? `<span class="muted small">· ${esc(src)}</span>` : ""}</b>
        ${data.malayalam ? `<button class="btn sm" id="lyscript" title="Malayalam script / Manglish">${roman ? "മ" : "Aa"}</button>` : ""}
        ${has ? `<button class="btn sm" id="lymenu" aria-label="Lyrics options">⋯</button>` : ""}</div>
      ${job?.status === "running" ? `<div class="small" style="margin:8px 0"><span class="spin"></span> ${esc(job.message)}</div>` : ""}
      ${job?.status === "error" ? `<div class="small" style="margin:8px 0;color:var(--danger)">${esc(job.message)}</div>` : ""}
      ${!has || el.dataset.menu ? `
        <div class="lyfind">
          <div class="row"><input id="lyq" type="text" value="${esc(data.query || data.suggested_query || "")}" placeholder="Song name + film" aria-label="Search lyrics">
            <button class="btn primary sm" id="lylrc">Find lyrics</button></div>
          <div class="row" style="margin-top:6px">
            ${canTranscribe ? `<select id="lylang" aria-label="Language"><option value="">Auto language</option><option value="ml">Malayalam</option><option value="hi">Hindi</option><option value="ta">Tamil</option><option value="te">Telugu</option><option value="kn">Kannada</option><option value="en">English</option></select>
            <button class="btn sm" id="lywh">Transcribe vocals</button>` : ""}
            <button class="btn sm" id="lypaste">Paste lyrics</button>
            ${has ? `<button class="btn sm" id="lyretime">Re-time by tapping</button><button class="btn sm danger" id="lydel">Remove</button>` : ""}</div>
          <div class="small muted" style="margin-top:6px">Find = synced lyrics from LRCLIB (free). Transcribe = speech-to-text on the vocal stem, a few minutes, rough for Malayalam. Paste = your own; then tap along once to time the lines.</div>
        </div>` : ""}
      ${has && data.lines.some(l => l.t != null) ? `<div class="row small muted" style="margin-top:8px">Timing <button class="btn sm" data-shift="-0.5">−0.5s</button><button class="btn sm" data-shift="0.5">+0.5s</button><span class="grow"></span>Tap a line to jump there</div>` : ""}
      ${tapping >= 0 || untimed() ? `<div class="tapbar"><button class="btn primary" id="lytap">${tapping >= 0 ? `Tap: line ${tapping + 1} of ${data.lines.length}` : "▶ Start tap timing"}</button>
        <span class="small muted">${tapping >= 0 ? "Tap (or press T) as each line starts. Esc to stop." : "Play the song and tap when each line starts."}</span></div>` : ""}
      <div class="lyr" id="lyr">${has ? sheet(tp) : ""}</div>`;
    bind();
    cur = -1; follow(getMixer()?.pos() || 0);
  }

  function sheet(tp) {
    if (untimed() || !chords.length) {
      return data.lines.map((l, i) => `<div class="ll" data-i="${i}"><span class="lt">${esc((roman && l.roman) || l.text)}</span></div>`).join("");
    }
    return layoutLyrics(data.lines, chords, tp, roman).map(r => r.kind === "inst"
      ? `<div class="li" data-t="${r.t}">${r.chords.map(esc).join("  ")}</div>`
      : `<div class="ll" data-i="${r.idx}" data-t="${r.t}">${r.words.map(w => `<span class="lw"><b>${esc(w.c) || "&nbsp;"}</b>${esc(w.w)}</span>`).join(" ")}</div>`).join("");
  }

  function bind() {
    const on = (id, f) => { const b = $(id, el); if (b) b.onclick = f; };
    on("#lyscript", () => { roman = !roman; try { localStorage.setItem("sk_roman", roman ? "1" : "0"); } catch {} draw(); });
    on("#lymenu", () => { el.dataset.menu ? delete el.dataset.menu : el.dataset.menu = "1"; draw(); });
    on("#lylrc", () => start("lrclib", {query: $("#lyq", el).value}));
    on("#lywh", () => start("whisper", {language: $("#lylang", el).value}));
    on("#lypaste", pasteDialog);
    on("#lydel", async () => { if (!confirm("Remove these lyrics?")) return; await api(`songs/${sid}/lyrics`, {method: "DELETE"}); delete el.dataset.menu; load(); });
    on("#lyretime", () => { data.lines.forEach(l => l.t = null); tapping = -1; delete el.dataset.menu; draw(); toast("Play the song and tap as each line starts"); });
    on("#lytap", tap);
    $$("[data-shift]", el).forEach(b => b.onclick = () => shift(+b.dataset.shift));
    $$(".ll[data-t], .li[data-t]", el).forEach(r => r.onclick = () => { const m = getMixer(); if (m?.duration) m.seek(+r.dataset.t); });
  }

  async function start(source, body) {
    try { data.job = (await api(`songs/${sid}/lyrics/fetch`, {method: "POST", json: {source, ...body}})).job; delete el.dataset.menu; draw(); poll = setTimeout(load, 1500); }
    catch (e) { toast(e.message); }
  }

  async function save(lines) {
    try { data = await api(`songs/${sid}/lyrics`, {method: "PUT", json: {lines}}); draw(); } catch (e) { toast(e.message); }
  }

  function shift(d) {
    data.lines.forEach(l => { if (l.t != null) l.t = Math.max(0, Math.round((l.t + d) * 100) / 100); });
    l_words(d); draw(); clearTimeout(shift.t); shift.t = setTimeout(() => save(data.lines), 800);
  }
  function l_words(d) { data.lines.forEach(l => l.words?.forEach(w => w.t = Math.max(0, Math.round((w.t + d) * 100) / 100))); }

  function tap() {
    const m = getMixer();
    if (!m?.duration) return toast("Wait for the player to load");
    if (tapping < 0) {
      tapping = 0; data.lines.forEach(l => { l.t = null; delete l.words; });
      if (!m.playing) m.play();
      return draw();
    }
    data.lines[tapping].t = Math.round(m.pos() * 100) / 100;
    tapping++;
    if (tapping >= data.lines.length) { tapping = -1; save(data.lines); toast("Lines timed — use ±0.5s if they're early or late"); return; }
    draw();
  }

  function pasteDialog() {
    const dlg = document.createElement("dialog"); dlg.className = "mdlg";
    dlg.innerHTML = `<b>Paste lyrics</b>
      <div class="small muted" style="margin:6px 0">One line per sung line. Malayalam script or Manglish both work. Lines with [mm:ss.xx] times (.lrc) are used as they are; otherwise you time them by tapping.</div>
      <textarea id="lyt" style="min-height:240px" placeholder="Malare ninne kaanathirunnal…"></textarea>
      <div class="row" style="margin-top:10px"><span class="grow"></span><button class="btn" id="lyc">Cancel</button><button class="btn primary" id="lys">Save</button></div>`;
    document.body.append(dlg);
    $("#lyc", dlg).onclick = () => dlg.close();
    $("#lys", dlg).onclick = async () => {
      try { data = await api(`songs/${sid}/lyrics`, {method: "PUT", json: {text: $("#lyt", dlg).value}}); dlg.close(); delete el.dataset.menu; draw();
        if (untimed()) toast("Now play the song and tap as each line starts"); }
      catch (e) { toast(e.message); }
    };
    dlg.addEventListener("close", () => dlg.remove()); dlg.showModal();
  }

  function follow(p) {
    if (dead || untimed() || tapping >= 0) return;
    const rows = $$(".ll[data-t]", el);
    let k = -1; rows.forEach((r, j) => { if (+r.dataset.t <= p + 0.05) k = j; });
    if (k === cur) return; cur = k;
    rows.forEach((r, j) => r.classList.toggle("on", j === k));
    const box = $("#lyr", el), row = rows[k];
    if (row && getMixer()?.playing) box.scrollTo({top: row.offsetTop - box.offsetTop - box.clientHeight / 3, behavior: "smooth"});
  }

  const onKey = e => {
    if (e.target.closest?.("input,textarea,select")) return;
    if (tapping >= 0 && (e.key === "t" || e.key === "T")) { e.preventDefault(); tap(); }
    if (tapping >= 0 && e.key === "Escape") { tapping = -1; draw(); }
  };
  document.addEventListener("keydown", onKey);
  load();
  return {follow, draw, destroy() { dead = true; clearTimeout(poll); document.removeEventListener("keydown", onKey); }};
}

// ---------------- song view ----------------

async function songView(sid) {
  let s = await api(`songs/${sid}`);

  const render = () => {
    const c = s.card, det = c.detected || {};
    view.innerHTML = `
      <div class="row" style="margin-bottom:6px"><a href="#/" class="small muted">← Library</a></div>
      <div class="row">
        <h1 class="grow" style="margin:0">${esc(s.title)}</h1>
        ${s.status === "ready" ? `<a class="btn" href="#/live/song/${s.id}">Live view</a>` : ""}
      </div>
      <div class="chips" style="margin:6px 0 16px">${statusChip(s)}${s.duration ? `<span class="chip">${fmtTime(s.duration)}</span>` : ""}</div>
      ${busy(s.status) ? `<div class="panel"><div>${esc(s.stage)}…</div><div class="bar"><i style="width:${Math.round(s.progress * 100)}%"></i></div>
        <div class="small muted" style="margin-top:8px">You can fill in the song card below while this runs.</div></div>` : ""}
      ${s.status === "error" ? `<div class="panel"><div style="color:var(--danger)">${esc(s.error)}</div>
        <div class="row" style="margin-top:10px"><button class="btn" id="retry">Try again</button></div></div>` : ""}
      <div class="grid2" style="margin-top:14px">
        <div>
          ${s.status === "ready" ? `<div class="panel"><div class="row" style="margin-bottom:6px"><b class="grow">${s.quick ? "Player" : "Stems"}</b>
            ${s.quick ? `<button class="btn sm" id="mkstems">Make stems</button>` : `<a class="btn sm" href="api/songs/${s.id}/stems.zip?format=mp3">All MP3 (zip)</a><a class="btn sm" href="api/songs/${s.id}/stems.zip">All WAV</a>`}</div><div id="mixer"></div></div>` : ""}
          ${s.has_chords ? `<div class="panel" style="margin-top:14px" id="chordp">
            <div class="row"><b class="grow">Chords <span class="muted small">· approximate</span></b>
              <span class="tp"><button class="btn sm" id="tpd" aria-label="Transpose down">−</button><span id="tpv"></span><button class="btn sm" id="tpu" aria-label="Transpose up">+</button></span></div>
            <div class="now"><div class="cn" id="cnow">–</div><div class="cnext" id="cnext"></div></div>
            <div class="row" style="margin:6px 0 10px"><button class="btn sm" id="mark">⏱ Mark section here</button>
              <button class="btn sm" id="fill">Fill section chords</button><span class="small muted grow">Mark while playing, then fill.</span></div>
            <div class="chart" id="chart"></div></div>` : ""}
          <div class="panel" style="margin-top:14px" id="lyrp"></div>
          ${s.youtube_id ? `<h2>YouTube</h2><div class="yt"><iframe src="https://www.youtube-nocookie.com/embed/${esc(s.youtube_id)}" title="YouTube" allow="encrypted-media; picture-in-picture; fullscreen" loading="lazy"></iframe></div>` : ""}
        </div>
        <div class="panel">
          <div class="row"><b class="grow">Song card</b><button class="btn primary sm" id="save">Save</button></div>
          <div style="margin-top:12px"><label class="f" for="ti">Title</label><input id="ti" type="text" value="${esc(s.title)}"></div>
          <div class="fields" style="margin-top:10px">
            <div style="grid-column:span 2"><label class="f" for="key">Key</label><input id="key" type="text" value="${esc(c.key)}" placeholder="e.g. D minor">
              ${det.key ? `<div class="sugg">Detected ${esc(det.key)} (${Math.round(det.key_confidence * 100)}%) · also
                ${(det.key_alternatives || []).map(k => `<button data-key="${esc(k)}">${esc(k)}</button>`).join("")}</div>` : ""}</div>
            <div><label class="f" for="bpm">BPM</label><input id="bpm" type="number" min="20" max="300" step="0.1" value="${esc(c.bpm ?? "")}">
              ${det.bpm ? `<div class="sugg">${[det.bpm, ...(det.bpm_alternatives || [])].map(b => `<button data-bpm="${b}">${b}</button>`).join("")}</div>` : ""}</div>
            <div><label class="f" for="meter">Meter</label><select id="meter">${METERS.map(m => `<option ${m === c.meter ? "selected" : ""}>${m}</option>`).join("")}</select></div>
          </div>
          <h2>MODX performance</h2>
          <div class="fields">
            <div style="grid-column:span 2"><label class="f" for="perf">Performance name</label><input id="perf" type="text" value="${esc(c.modx?.performance)}" placeholder="e.g. Tabla Ballad 6-8"></div>
            <div><label class="f" for="mode">Load by</label><select id="mode">
              ${[["", "Don't send"], ["preset", "Preset Performance"], ["liveset", "Live Set slot"], ["perf", "Bank + program"]].map(([v, t]) => `<option value="${v}" ${(c.modx?.mode ?? (c.modx?.program ? "perf" : "")) === v ? "selected" : ""}>${t}</option>`).join("")}</select></div>
            <div><label class="f" for="mtr">MODX transpose</label><input id="mtr" type="number" min="-24" max="24" value="${esc(c.modx?.transpose ?? 0)}"></div>
            <div class="lsf"><label class="f" for="lsp">Live Set page (1–16)</label><input id="lsp" type="number" min="1" max="16" value="${esc(c.modx?.ls_page ?? "")}"></div>
            <div class="lsf"><label class="f" for="lss">Slot (1–16)</label><input id="lss" type="number" min="1" max="16" value="${esc(c.modx?.ls_slot ?? "")}"></div>
            <div class="pcf"><label class="f" for="msb">Bank MSB</label><input id="msb" type="number" min="0" max="127" value="${esc(c.modx?.bank_msb ?? "")}"></div>
            <div class="pcf"><label class="f" for="lsb">Bank LSB</label><input id="lsb" type="number" min="0" max="127" value="${esc(c.modx?.bank_lsb ?? "")}"></div>
            <div class="pcf"><label class="f" for="pc">Program (1–128)</label><input id="pc" type="number" min="1" max="128" value="${esc(c.modx?.program ?? "")}"></div>
            <div class="prf"><label class="f" for="pno">Preset no. (1–3487)</label><input id="pno" type="number" min="1" max="3487" value="${esc(c.modx?.preset_no ?? "")}"></div>
            <div class="prf" style="grid-column:span 3;align-self:end"><button class="btn" id="finder" type="button">🔎 Find a sound for this song</button></div>
          </div>
          <div class="small muted" style="margin-top:4px" id="modehelp"></div>
          <div class="row" style="margin-top:8px">${s.status === "ready" ? `<button class="btn primary" id="autobtn" type="button">✨ Auto-build</button>` : ""}<button class="btn" id="scenebtn" type="button">🎛 Build scenes by hand</button>
            <span class="small muted" id="planinfo">${c.scene_plan ? `Plan: ${esc(c.scene_plan.family)}` : ""}</span></div>
          <h2>Sections and scenes</h2>
          <table class="sec"><thead><tr><th>Section</th><th>Scene</th><th>Chords / cue</th><th></th></tr></thead><tbody id="secs"></tbody></table>
          <div class="row" style="margin-top:8px"><button class="btn sm" id="addsec">+ Section</button>
            ${c.sections?.length ? "" : `<button class="btn sm" id="typical">Add typical layout</button>`}</div>
          <h2>Notes</h2>
          <textarea id="notes" placeholder="Transpose, footswitch, anything to remember">${esc(c.notes)}</textarea>
          <div class="row" style="margin-top:14px"><span class="grow"></span><button class="btn danger sm" id="del">Delete song</button></div>
        </div>
      </div>`;

    let sections = (c.sections || []).map(x => ({...x}));
    let transpose = +c.transpose || 0;
    let scenePlan = c.scene_plan || null;
    const drawSecs = () => {
      $("#secs").innerHTML = sections.map((x, i) => `
        <tr data-i="${i}">
          <td class="nm"><input type="text" data-f="name" value="${esc(x.name)}" aria-label="Section name">${x.start != null ? `<div class="small muted at">at ${fmtTime(x.start)}</div>` : ""}</td>
          <td class="sc"><select data-f="scene" aria-label="Scene">${[1, 2, 3, 4, 5, 6, 7, 8].map(n => `<option ${+x.scene === n ? "selected" : ""}>${n}</option>`).join("")}</select></td>
          <td><input type="text" data-f="chords" value="${esc(x.chords)}" placeholder="Dm  Bb  C  Dm"><input type="text" data-f="cue" value="${esc(x.cue)}" placeholder="Cue" style="margin-top:4px"></td>
          <td class="ac"><button class="btn sm" data-a="up" aria-label="Move up">↑</button><button class="btn sm" data-a="rm" aria-label="Remove">✕</button></td>
        </tr>`).join("") || `<tr><td colspan="4" class="muted small">No sections yet. Each section maps to one MODX scene button.</td></tr>`;
      $$("#secs input, #secs select").forEach(inp => inp.oninput = () => {
        const i = inp.closest("tr").dataset.i; sections[i][inp.dataset.f] = inp.dataset.f === "scene" ? +inp.value : inp.value;
      });
      $$("#secs button").forEach(b => b.onclick = () => {
        const i = +b.closest("tr").dataset.i;
        if (b.dataset.a === "rm") sections.splice(i, 1);
        else if (i > 0) [sections[i - 1], sections[i]] = [sections[i], sections[i - 1]];
        drawSecs();
      });
    };
    drawSecs();
    $("#addsec").onclick = () => { sections.push({name: "", scene: Math.min(8, sections.length + 1), chords: "", cue: ""}); drawSecs(); };
    $("#typical")?.addEventListener("click", e => { sections = TYPICAL.map(([name, scene]) => ({name, scene, chords: "", cue: ""})); e.target.remove(); drawSecs(); });
    $$("[data-key]").forEach(b => b.onclick = () => { $("#key").value = b.dataset.key; });
    $$("[data-bpm]").forEach(b => b.onclick = () => { $("#bpm").value = b.dataset.bpm; });
    $("#retry")?.addEventListener("click", async () => { s = await api(`songs/${sid}/retry`, {method: "POST"}); render(); startPoll(); });

    const num = id => { const v = $(id).value.trim(); return v === "" ? null : +v; };
    const save = async () => {
      try {
        s = await api(`songs/${sid}`, {method: "PATCH", json: {title: $("#ti").value, card: {
          key: $("#key").value.trim(), bpm: num("#bpm"), transpose, scene_plan: scenePlan, meter: $("#meter").value, notes: $("#notes").value,
          modx: {performance: $("#perf").value.trim(), mode: $("#mode").value, transpose: num("#mtr") || 0, preset_no: num("#pno"),
            ls_page: num("#lsp"), ls_slot: num("#lss"), bank_msb: num("#msb"), bank_lsb: num("#lsb"), program: num("#pc")},
          sections: sections.filter(x => (x.name || "").trim()),
        }}});
        $("h1").textContent = s.title; toast("Saved");
      } catch (e) { toast(e.message); }
    };
    $("#save").onclick = save;
    const modeUi = () => {
      const m = $("#mode").value;
      $$(".lsf").forEach(e => e.hidden = m !== "liveset"); $$(".pcf").forEach(e => e.hidden = m !== "perf"); $$(".prf").forEach(e => e.hidden = m !== "preset");
      $("#modehelp").textContent = m === "liveset" ? "Live view selects this slot in the Live Set currently open on the MODX (Bank 62, LSB = page, Program = slot). Open your gig Live Set on the MODX before the show."
        : m === "preset" ? "Live view loads this factory Performance by number when the song opens. Use 🔎 to search all 3,487 presets and get groove ideas."
        : m === "perf" ? "Live view sends Bank Select + Program Change when the song opens. User banks 1–5: MSB 66, LSB 0–4. Library 1: MSB 66, LSB 8."
        : "Nothing is sent when the song opens. MODX transpose is shown on stage as a reminder.";
    };
    $("#mode").onchange = modeUi; modeUi();
    $("#autobtn")?.addEventListener("click", async () => {
      await save();
      openAutoBuild({sid, meter: $("#meter").value, bpm: num("#bpm"), onApply: async (res, sent) => {
        const card = {scene_plan: res.plan, auto_options: res.opts};
        if (res.sections) card.sections = res.sections.map(x => ({name: x.name, scene: x.scene, chords: x.chords || "", cue: x.cue || "", start: x.start}));
        s = await api(`songs/${sid}`, {method: "PATCH", json: {card}});
        mixer?.destroy(); render(); toast(sent ? "Applied and sent — press STORE on the MODX to keep it" : "Applied to the song");
      }});
    });
    $("#scenebtn").onclick = () => openScenePlan({meter: $("#meter").value, bpm: num("#bpm"), current: scenePlan, onSave: plan => {
      scenePlan = plan; $("#planinfo").textContent = `Plan: ${plan.family}`; toast("Scene plan added — Save to keep it");
    }});
    $("#finder").onclick = () => openFinder({meter: $("#meter").value, bpm: num("#bpm"), onUse: p => {
      $("#pno").value = p.no; $("#perf").value = p.name; toast(`${p.name} selected — Save to keep it`);
    }, onArp: a => {
      const line = `Arp #${a.no} ${a.family || a.name}${a.sound ? ` (${a.sound})` : ""} · ${a.ts} · ${a.tempo} BPM`;
      $("#notes").value = ($("#notes").value ? $("#notes").value + "\n" : "") + line; toast("Added to notes");
    }});
    const onKey = e => { if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); } };
    document.addEventListener("keydown", onKey);
    $("#del").onclick = async () => {
      if (!confirm(`Delete "${s.title}" and its stems?`)) return;
      try { await api(`songs/${sid}`, {method: "DELETE"}); location.hash = "#/"; } catch (e) { toast(e.message); }
    };

    let mixer = null;
    if (s.status === "ready") mixer = new Mixer(sid, s.stems, $("#mixer"));
    $("#mkstems")?.addEventListener("click", async () => {
      s = await api(`songs/${sid}/stems`, {method: "POST"}); toast("Making stems — chords stay available meanwhile"); mixer?.destroy(); render(); startPoll();
    });

    // Chords: follow playback, tap to seek, transpose, fill sections.
    let chordList = [], lastIdx = -1;
    const drawChart = () => {
      $("#tpv").textContent = transpose ? (transpose > 0 ? `+${transpose}` : transpose) : "0";
      $("#chart").innerHTML = chordList.map((c, i) => `<button class="ch" data-i="${i}" title="${fmtTime(c.t)}"><b>${esc(transposeChord(c.c, transpose))}</b><i>${fmtTime(c.t)}</i></button>`).join("");
      $$("#chart .ch").forEach(b => b.onclick = () => mixer?.duration && mixer.seek(chordList[b.dataset.i].t + 0.01));
      lastIdx = -1; follow(mixer ? mixer.pos() : 0);
    };
    const follow = p => {
      if (!chordList.length) return;
      let i = chordList.findIndex(c => p < c.t + c.d); if (i < 0) i = chordList.length - 1;
      if (i === lastIdx) return; lastIdx = i;
      $("#cnow").textContent = transposeChord(chordList[i].c, transpose);
      $("#cnext").textContent = chordList.slice(i + 1, i + 4).map(c => transposeChord(c.c, transpose)).join("   ");
      $$("#chart .ch").forEach((b, j) => b.classList.toggle("on", j === i));
      const cur = $(`#chart .ch[data-i="${i}"]`); if (cur && mixer?.playing) cur.scrollIntoView({block: "nearest", inline: "nearest"});
    };
    if (s.has_chords) {
      api(`songs/${sid}/chords`).then(list => { chordList = list; drawChart(); }).catch(() => {});
      if (mixer) mixer.onTick = follow;
      $("#tpd").onclick = () => { transpose = Math.max(-11, transpose - 1); drawChart(); };
      $("#tpu").onclick = () => { transpose = Math.min(11, transpose + 1); drawChart(); };
      $("#mark").onclick = () => {
        const t = mixer ? Math.round(mixer.pos() * 10) / 10 : 0;
        sections.push({name: `Section ${sections.length + 1}`, scene: Math.min(8, sections.length + 1), chords: "", cue: "", start: t});
        sections.sort((a, b) => (a.start ?? 1e9) - (b.start ?? 1e9)); drawSecs(); toast(`Section marked at ${fmtTime(t)} — rename it in the card`);
      };
      $("#fill").onclick = () => {
        const timed = sections.filter(x => x.start != null);
        if (!timed.length) return toast("Mark sections while playing first (⏱ Mark section here).");
        timed.forEach((x, k) => { x.chords = chordsBetween(chordList, x.start, timed[k + 1]?.start ?? 1e9, transpose); });
        drawSecs(); toast("Section chords filled — check them, then Save");
      };
    }
    const lyr = lyricsPanel(sid, $("#lyrp"), () => mixer, () => transpose, s.status === "ready");
    if (mixer) mixer.onTick = p => { if (s.has_chords) follow(p); lyr.follow(p); };
    const drawChart0 = drawChart;
    if (s.has_chords) { $("#tpd").onclick = () => { transpose = Math.max(-11, transpose - 1); drawChart0(); lyr.draw(); };
      $("#tpu").onclick = () => { transpose = Math.min(11, transpose + 1); drawChart0(); lyr.draw(); }; }
    cleanup = () => { document.removeEventListener("keydown", onKey); mixer?.destroy(); lyr.destroy(); };
  };

  // While processing, refresh only the status (the card form keeps its edits).
  const startPoll = () => {
    clearInterval(pollTimer);
    if (!busy(s.status)) return;
    pollTimer = setInterval(async () => {
      const n = await api(`songs/${sid}`);
      if (n.status !== s.status && !busy(n.status)) { s = n; clearInterval(pollTimer); render(); toast(n.status === "ready" ? "Stems ready" : "Processing failed"); return; }
      s.status = n.status; s.stage = n.stage; s.progress = n.progress;
      const bar = $(".panel .bar i"); if (bar) bar.style.width = Math.round(n.progress * 100) + "%";
      const st = bar?.closest(".panel")?.firstElementChild; if (st) st.textContent = n.stage + "…";
    }, 4000);
  };
  render(); startPoll();
}

// ---------------- set lists ----------------

async function setsView() {
  const [sets, songs] = await Promise.all([api("setlists"), api("songs")]);
  const name = id => songs.find(s => s.id === id)?.title || "(deleted)";
  view.innerHTML = `
    <div class="row"><h1 class="grow">Set lists</h1><a class="btn primary" href="#/sets/new">New set list</a></div>
    <div class="list sets">${sets.length ? sets.map(sl => `
      <div class="item">
        <div class="grow"><div class="title">${esc(sl.name)}</div>
          <div class="small muted">${sl.song_ids.length} songs · ${esc(sl.song_ids.slice(0, 4).map(name).join(", "))}${sl.song_ids.length > 4 ? "…" : ""}</div></div>
        <a class="btn sm" href="#/sets/${sl.id}">Edit</a>
        <a class="btn primary sm" href="#/live/set/${sl.id}">Go live</a>
      </div>`).join("") : `<div class="empty">No set lists yet.</div>`}</div>`;
}

async function setEditView(slid) {
  const [sets, songs] = await Promise.all([api("setlists"), api("songs")]);
  const existing = sets.find(x => x.id === slid);
  let order = existing ? existing.song_ids.filter(id => songs.some(s => s.id === id)) : [];
  view.innerHTML = `
    <div class="row" style="margin-bottom:6px"><a href="#/sets" class="small muted">← Set lists</a></div>
    <h1>${existing ? "Edit set list" : "New set list"}</h1>
    <div class="grid2">
      <div class="panel">
        <label class="f" for="nm">Name</label><input id="nm" type="text" value="${esc(existing?.name || "")}" placeholder="e.g. Onam show">
        <h2>Order</h2><ol class="order" id="ord"></ol>
        <div class="row" style="margin-top:12px">
          <button class="btn primary" id="sv">Save</button>
          ${existing ? `<button class="btn danger" id="dl">Delete</button>` : ""}
        </div>
      </div>
      <div class="panel"><b>Songs</b><div class="pick" id="pick" style="margin-top:10px"></div></div>
    </div>`;
  const draw = () => {
    $("#ord").innerHTML = order.map((id, i) => `<li><span class="grow">${esc(songs.find(s => s.id === id).title)}</span>
      <button class="btn sm" data-u="${i}" aria-label="Move up">↑</button><button class="btn sm" data-r="${i}" aria-label="Remove">✕</button></li>`).join("")
      || `<li class="muted">Tick songs on the right to add them.</li>`;
    $("#pick").innerHTML = songs.map(s => `<label><input type="checkbox" value="${s.id}" ${order.includes(s.id) ? "checked" : ""}>
      <span class="grow">${esc(s.title)}</span>${statusChip(s)}</label>`).join("") || `<div class="muted">Add songs in the Library first.</div>`;
    $$("#ord [data-u]").forEach(b => b.onclick = () => { const i = +b.dataset.u; if (i) [order[i - 1], order[i]] = [order[i], order[i - 1]]; draw(); });
    $$("#ord [data-r]").forEach(b => b.onclick = () => { order.splice(+b.dataset.r, 1); draw(); });
    $$("#pick input").forEach(c => c.onchange = () => { c.checked ? order.push(c.value) : order = order.filter(x => x !== c.value); draw(); });
  };
  draw();
  $("#sv").onclick = async () => {
    const body = {name: $("#nm").value.trim() || "Untitled set", song_ids: order};
    try {
      existing ? await api(`setlists/${slid}`, {method: "PUT", json: body}) : await api("setlists", {method: "POST", json: body});
      toast("Saved"); location.hash = "#/sets";
    } catch (e) { toast(e.message); }
  };
  $("#dl")?.addEventListener("click", async () => {
    if (!confirm("Delete this set list? Songs stay in the library.")) return;
    await api(`setlists/${slid}`, {method: "DELETE"}); location.hash = "#/sets";
  });
}

// ---------------- live mode ----------------

const LIVE_CACHE = "sk_live_cache";
const midiSettings = () => { try { return JSON.parse(localStorage.getItem("sk_midi") || "{}"); } catch { return {}; } };
const saveMidiSettings = s => { try { localStorage.setItem("sk_midi", JSON.stringify(s)); } catch {} };

async function liveView(kind, id) {
  let title, songs;
  try {
    const all = await api("songs");
    if (all.offline) throw new Error("offline");
    if (kind === "set") {
      const sl = (await api("setlists")).find(x => x.id === id);
      if (!sl) throw new Error("Set list not found");
      title = sl.name; songs = sl.song_ids.map(i => all.find(s => s.id === i)).filter(Boolean);
    } else {
      const one = all.find(s => s.id === id); if (!one) throw new Error("Song not found");
      title = one.title; songs = [one];
    }
    try { localStorage.setItem(LIVE_CACHE + kind + id, JSON.stringify({title, songs})); } catch {}
  } catch (e) {
    if (e.message === "Login required") throw e;
    const cached = (() => { try { return JSON.parse(localStorage.getItem(LIVE_CACHE + kind + id)); } catch { return null; } })();
    if (!cached) throw new Error(e.message === "offline" ? "Offline and this set hasn't been opened before." : e.message);
    ({title, songs} = cached); toast("Offline — using the saved copy of this set");
  }
  if (!songs.length) throw new Error("This set list is empty.");

  document.body.classList.add("live");
  let si = 0, xi = 0;
  const ms = midiSettings();
  let midiOut = null, midiAccess = null;

  view.innerHTML = `
    <div class="stage">
      <div class="hd"><div class="song" id="lsong"></div><div class="meta" id="lmeta"></div></div>
      <div class="body"><div class="zone cur" id="zcur"></div><div class="zone nxt" id="znxt"></div></div>
      <div class="ft">
        <button class="btn" id="psong" aria-label="Previous song">⏮ Song</button>
        <button class="btn" id="psec" aria-label="Previous section">◀</button>
        <div class="dots" id="dots"></div>
        <button class="btn" id="nsec" aria-label="Next section">▶</button>
        <button class="btn" id="nsong" aria-label="Next song">Song ⏭</button>
        <button class="btn" id="midi">MIDI</button><span class="midi" id="mst"></span>
        <button class="btn" id="fs" aria-label="Full screen">⛶</button>
        <button class="btn" id="exit">Exit</button>
      </div>
    </div>`;

  const secs = () => songs[si].card.sections || [];
  const zone = (x, lbl) => x ? `<div class="lbl">${lbl}</div><div class="sec">${esc(x.name)}</div>
      <div><span class="scene">SCENE ${esc(x.scene)}</span></div>
      ${x.chords ? `<div class="chords">${esc(x.chords)}</div>` : ""}${x.cue ? `<div class="cue">${esc(x.cue)}</div>` : ""}` : `<div class="lbl">${lbl}</div>`;

  function draw() {
    const s = songs[si], c = s.card, list = secs();
    $("#lsong").textContent = `${si + 1}/${songs.length} · ${s.title}`;
    const tr = +(c.modx?.transpose || 0);
    $("#lmeta").innerHTML = [c.key, c.bpm && `${c.bpm} BPM`, c.meter, c.modx?.performance].filter(Boolean).map(esc).map(t => `<span>${t}</span>`).join("")
      + (tr ? `<span class="trb">TRANSPOSE ${tr > 0 ? "+" : ""}${tr}</span>` : "");
    if (!list.length) {
      $("#zcur").innerHTML = `<div class="lbl">No sections</div><div class="sec">${esc(s.title)}</div><div class="cue">Add sections in the song card to get scene cues here.</div>${c.notes ? `<div class="cue">${esc(c.notes)}</div>` : ""}`;
      const nx = songs[si + 1];
      $("#znxt").innerHTML = nx ? `<div class="lbl">Next song</div><div class="sec">${esc(nx.title)}</div>` : `<div class="lbl">End of set</div>`;
    } else {
      $("#zcur").innerHTML = zone(list[xi], `Now · ${xi + 1}/${list.length}`);
      const nx = list[xi + 1];
      $("#znxt").innerHTML = nx ? zone(nx, "Next") : (songs[si + 1] ? `<div class="lbl">Next song</div><div class="sec">${esc(songs[si + 1].title)}</div>` : `<div class="lbl">End of set</div>`);
    }
    $("#dots").innerHTML = list.map((_, i) => `<i class="${i === xi ? "on" : ""}"></i>`).join("");
  }
  let lastSent = 0;
  const ch = () => ((ms.channel || 1) - 1) & 15;
  const send = msg => { if (!midiOut) return false; try { midiOut.send(msg); lastSent = performance.now(); return true; } catch { return false; } };
  function sendProgram() {
    const m = songs[si].card.modx || {};
    const mode = m.mode ?? (m.program ? "perf" : "");
    if (!midiOut || !mode) return false;
    if (mode === "liveset" && m.ls_page && m.ls_slot) {
      // Live Set slot: Bank MSB 62, LSB = page, Program = slot (values from MODX/MONTAGE docs — test on your M6).
      send([0xB0 | ch(), 0, 62]); send([0xB0 | ch(), 32, (m.ls_page - 1) & 127]); send([0xC0 | ch(), (m.ls_slot - 1) & 15]);
    } else if (mode === "preset" && m.preset_no) {
      presetMsgs(m.preset_no, ch()).forEach(send);
    } else if (mode === "perf" && m.program) {
      if (m.bank_msb != null) send([0xB0 | ch(), 0, m.bank_msb & 127]);
      if (m.bank_lsb != null) send([0xB0 | ch(), 32, m.bank_lsb & 127]);
      send([0xC0 | ch(), (m.program - 1) & 127]);
    } else return false;
    toast(`Loaded ${m.performance || "song sound"} on MODX`);
    return true;
  }
  // Scene buttons 1–8 over MIDI: one CC (MODX default 92); value bands of 16 select the scene.
  function sendScene() {
    if (ms.sendScenes === false || !midiOut) return;
    const x = secs()[xi]; if (!x?.scene) return;
    send([0xB0 | ch(), (ms.sceneCC ?? 92) & 127, ((x.scene - 1) * 16 + 8) & 127]);
  }
  function transposeNote(prevSong) {
    const t = +(songs[si].card.modx?.transpose || 0), prev = prevSong ? +(prevSong.card.modx?.transpose || 0) : 0;
    if (t) toast(`Set MODX transpose to ${t > 0 ? "+" : ""}${t}`, 4000);
    else if (prev) toast("Reset MODX transpose to 0", 4000);
  }
  const goSong = d => {
    const n = si + d; if (n < 0 || n >= songs.length) return;
    const prev = songs[si]; si = n; xi = 0; draw(); transposeNote(prev);
    // Give the MODX a moment to load the sound before selecting its first scene.
    if (sendProgram()) setTimeout(sendScene, 400); else sendScene();
  };
  const goSec = d => {
    const n = xi + d, len = secs().length;
    if (n >= len) return goSong(1);
    if (n < 0) return;
    xi = n; draw(); sendScene();
  };
  // Scene pressed on the keyboard → move the cue to the next section using that scene.
  function onMidiIn(e) {
    if (ms.followScenes === false || performance.now() - lastSent < 250) return;
    const [st, cc, val] = e.data;
    if ((st & 0xF0) !== 0xB0 || (st & 15) !== ch() || cc !== (ms.sceneCC ?? 92)) return;
    const scene = Math.floor(val / 16) + 1, list = secs();
    if (list[xi]?.scene === scene) return;
    for (let k = 1; k <= list.length; k++) {
      const j = (xi + k) % list.length;
      if (+list[j].scene === scene) { xi = j; draw(); return; }
    }
  }

  $("#psong").onclick = () => goSong(-1); $("#nsong").onclick = () => goSong(1);
  $("#psec").onclick = () => goSec(-1); $("#nsec").onclick = () => goSec(1);
  $("#zcur").onclick = () => goSec(1); $("#znxt").onclick = () => goSec(1);
  $("#exit").onclick = () => { if (document.fullscreenElement) document.exitFullscreen(); history.length > 1 ? history.back() : (location.hash = "#/"); };
  $("#fs").onclick = () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen?.();

  // Page-turner pedals and keyboards: → / Space / PageDown = next section; ← / PageUp = back; ↑ ↓ = songs.
  const onKey = e => {
    const k = e.key;
    if (["ArrowRight", " ", "PageDown", "Enter"].includes(k)) { e.preventDefault(); goSec(1); }
    else if (["ArrowLeft", "PageUp", "Backspace"].includes(k)) { e.preventDefault(); goSec(-1); }
    else if (k === "ArrowDown") { e.preventDefault(); goSong(1); }
    else if (k === "ArrowUp") { e.preventDefault(); goSong(-1); }
  };
  document.addEventListener("keydown", onKey);
  let tx = null;
  const onTs = e => { tx = e.touches[0].clientX; };
  const onTe = e => { if (tx == null) return; const dx = e.changedTouches[0].clientX - tx; if (Math.abs(dx) > 60) goSec(dx < 0 ? 1 : -1); tx = null; };
  const stage = $(".stage"); stage.addEventListener("touchstart", onTs, {passive: true}); stage.addEventListener("touchend", onTe);

  // Keep the screen awake on stage.
  let wake = null;
  const lockWake = async () => { try { wake = await navigator.wakeLock?.request("screen"); } catch {} };
  const onVis = () => { if (document.visibilityState === "visible") lockWake(); };
  lockWake(); document.addEventListener("visibilitychange", onVis);

  // MIDI: choose port, channel and scene CC in a small panel; settings are remembered on this device.
  function showMidi() {
    $("#mst").textContent = midiOut ? `${midiOut.name} · ch ${ms.channel || 1}` : "";
    $("#mst").className = "midi" + (midiOut ? " ok" : "");
  }
  function connectPorts() {
    const outs = [...midiAccess.outputs.values()];
    midiOut = outs.find(o => o.id === ms.port) || outs.find(o => /modx|yamaha/i.test(o.name)) || outs[0] || null;
    if (midiOut) { ms.port = midiOut.id; saveMidiSettings(ms); }
    for (const inp of midiAccess.inputs.values()) inp.onmidimessage = /modx|yamaha/i.test(inp.name) || midiAccess.inputs.size === 1 ? onMidiIn : null;
    showMidi();
  }
  async function ensureMidi() {
    if (midiAccess) return true;
    if (!navigator.requestMIDIAccess) { toast("This browser has no Web MIDI. Use Chrome or Edge."); return false; }
    try { midiAccess = await navigator.requestMIDIAccess(); } catch { toast("MIDI permission was refused."); return false; }
    midiAccess.onstatechange = () => connectPorts();
    connectPorts();
    if (!midiOut) toast("No MIDI device found. Connect the MODX by USB (OTG cable on a phone).");
    return true;
  }
  $("#midi").onclick = async () => {
    if (!(await ensureMidi())) return;
    const outs = [...midiAccess.outputs.values()];
    const dlg = document.createElement("dialog"); dlg.className = "mdlg";
    dlg.innerHTML = `<form method="dialog">
      <h2 style="margin-top:0">MIDI to MODX</h2>
      <label class="f">Output</label><select id="mport">${outs.map(o => `<option value="${esc(o.id)}" ${midiOut?.id === o.id ? "selected" : ""}>${esc(o.name)}</option>`).join("") || "<option>No devices</option>"}</select>
      <div class="fields" style="grid-template-columns:1fr 1fr;margin-top:10px">
        <div><label class="f">Channel</label><input id="mch" type="number" min="1" max="16" value="${ms.channel || 1}"></div>
        <div><label class="f">Scene CC</label><input id="mcc" type="number" min="1" max="95" value="${ms.sceneCC ?? 92}"></div>
      </div>
      <label class="chk"><input type="checkbox" id="msc" ${ms.sendScenes === false ? "" : "checked"}> Change MODX scene when I move sections</label>
      <label class="chk"><input type="checkbox" id="mfl" ${ms.followScenes === false ? "" : "checked"}> Follow scene buttons pressed on the MODX</label>
      <div class="row" style="margin-top:14px"><button class="btn" value="test" id="mtest" type="button">Send current song</button><span class="grow"></span><button class="btn primary" value="ok">Done</button></div>
    </form>`;
    document.body.appendChild(dlg);
    const apply = () => {
      ms.port = $("#mport", dlg).value; ms.channel = Math.min(16, Math.max(1, +$("#mch", dlg).value || 1));
      ms.sceneCC = Math.min(95, Math.max(1, +$("#mcc", dlg).value || 92));
      ms.sendScenes = $("#msc", dlg).checked; ms.followScenes = $("#mfl", dlg).checked;
      saveMidiSettings(ms); connectPorts();
    };
    $("#mtest", dlg).onclick = () => { apply(); if (sendProgram()) setTimeout(sendScene, 400); else { sendScene(); toast(midiOut ? "Sent scene (this song has no sound to load)" : "No MIDI output"); } };
    dlg.addEventListener("close", () => { apply(); dlg.remove(); });
    dlg.showModal();
  };
  // Reconnect automatically if MIDI was set up on this device before.
  if (ms.port && navigator.requestMIDIAccess) navigator.permissions?.query({name: "midi"}).then(p => { if (p.state === "granted") ensureMidi().then(() => { if (sendProgram()) setTimeout(sendScene, 400); }); }).catch(() => {});

  draw();
  cleanup = () => {
    document.removeEventListener("keydown", onKey); document.removeEventListener("visibilitychange", onVis);
    try { wake?.release(); } catch {}
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  };
}

// ---------------- boot ----------------
fetch("api/me", {credentials: "same-origin"}).then(r => r.json()).then(d => { if (!d.auth_required) $("#logout").hidden = true; }).catch(() => {});
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
route();
