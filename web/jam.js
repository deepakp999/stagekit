/* StageKit Jam: Shuffle or describe a mix, send it to the MODX, and let the tab play the chord
   progression so the band runs on its own while you play lead. Uses helpers from app.js. */

const JAM_KEY = "sk_jam";
const CHORD_INTERVALS = {"": [0, 4, 7], m: [0, 3, 7], "7": [0, 4, 7, 10], maj7: [0, 4, 7, 11], m7: [0, 3, 7, 10],
  sus2: [0, 2, 7], sus4: [0, 5, 7], dim: [0, 3, 6], add9: [0, 4, 7, 14], "6": [0, 4, 7, 9], m6: [0, 3, 7, 9],
  "9": [0, 4, 7, 10, 14], m9: [0, 3, 7, 10, 14]};
const JAM_PC = {C: 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, F: 5, "F#": 6, Gb: 6, G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11};

// Chord name → MIDI notes voiced for the left hand, below the split (arps and held pads follow these).
function chordNotes(name, split = 54) {
  const m = /^([A-G](?:#|b)?)(m9|m7|m6|maj7|sus2|sus4|dim|add9|m|7|6|9)?(?:\/([A-G](?:#|b)?))?$/.exec((name || "").trim());
  if (!m) return [];
  const root = JAM_PC[m[1]], ivs = CHORD_INTERVALS[m[2] || ""] || CHORD_INTERVALS[""];
  let base = 48 + root;                                   // around C3
  while (base + ivs[ivs.length - 1] >= split) base -= 12;
  while (base < 36) base += 12;
  // Close voicing: anything that would land above the split folds down an octave (keeps every chord tone).
  const notes = ivs.map(i => base + i).map(n => { while (n >= split) n -= 12; return n; }).sort((x, y) => x - y);
  if (m[3]) notes.unshift(Math.max(24, base + ((JAM_PC[m[3]] - root + 12) % 12) - 12));
  return [...new Set(notes)];
}

async function jamView() {
  const meta = await api("jam/genres");
  let plan = (() => { try { return JSON.parse(localStorage.getItem(JAM_KEY)); } catch { return null; } })();
  const prefs = (() => { try { return JSON.parse(localStorage.getItem("sk_auto") || "{}"); } catch { return {}; } })();
  const st = {genre: "any", split: prefs.split === undefined ? 54 : prefs.split, lead: null, scene: 0, bars: 0, busy: false};
  const save = () => { try { localStorage.setItem(JAM_KEY, JSON.stringify(plan)); } catch {} };

  // ---------- chord player ----------
  const player = {on: false, timer: null, held: [], idx: 0, nextAt: 0, pendingScene: null, fillTimer: null};
  const chIdx = () => ((midiSettings().channel || 1) - 1) & 15;
  const barMs = () => 4 * 60000 / (plan?.bpm || 120);
  const barsPerChord = () => st.bars || ((plan?.bpm || 120) >= 110 ? 2 : 1);
  const sectionChords = () => plan?.progression?.sections?.[st.scene] || [];
  async function out() { return MIDI.ensure(); }
  function release(o, notes) { notes.forEach(n => o.send([0x80 | chIdx(), n, 0])); }
  async function playChord() {
    const o = await out(); if (!o || !player.on) return;
    const list = sectionChords(); if (!list.length) return;
    const name = list[player.idx % list.length];
    const notes = chordNotes(name, st.split ?? 54);
    notes.forEach(n => o.send([0x90 | chIdx(), n, 96]));             // new chord first (legato keeps the arps running)
    release(o, player.held.filter(n => !notes.includes(n)));
    player.held = notes;
    drawNow(name, list[(player.idx + 1) % list.length]);
    player.idx++;
  }
  function tick() {
    if (!player.on) return;
    const now = performance.now();
    if (now >= player.nextAt - 5) {
      if (player.pendingScene != null) { applyScene(player.pendingScene); player.pendingScene = null; player.idx = 0; }
      playChord();
      player.nextAt += barsPerChord() * barMs();
    }
    player.timer = setTimeout(tick, Math.max(5, Math.min(40, player.nextAt - performance.now() - 5)));
  }
  async function startBand() {
    const o = await out(); if (!o) return;
    o.send(ymh([0x06, 0x00, 0x01, 0x09], [1]));                      // Arpeggio master on
    player.on = true; player.idx = 0; player.nextAt = performance.now() + 30; tick(); drawPlayer();
  }
  async function stopBand() {
    player.on = false; clearTimeout(player.timer); clearTimeout(player.fillTimer);
    const o = await out(); if (o) { release(o, player.held); o.send([0xB0 | chIdx(), 123, 0]); }
    player.held = []; drawNow("–", ""); drawPlayer();
  }

  // ---------- scenes (with arranger-style fills) ----------
  const sceneMsg = async n => { const o = await out(); o?.send([0xB0 | chIdx(), (midiSettings().sceneCC ?? 92) & 127, (n * 16 + 8) & 127]); };
  function applyScene(n) { st.scene = n; drawScenes(); }
  async function goScene(n) {
    const from = st.scene, mains = [1, 2, 3];
    clearTimeout(player.fillTimer);
    if (mains.includes(from) && [1, 2, 3, 6].includes(n) && n !== from) {
      await sceneMsg(n > from || n === 6 ? 4 : 5);                     // Fill A going up, Fill B going down
      flash(n);
      player.fillTimer = setTimeout(() => sceneMsg(n), barMs() + 40);
    } else await sceneMsg(n);
    if (player.on) player.pendingScene = n; else applyScene(n);
  }

  // ---------- rendering ----------
  view.innerHTML = `
    <div class="row" style="margin-bottom:10px"><h1 class="grow" style="margin:0">Jam</h1>
      <span class="small muted">Shuffle or describe a mix, send it, press Start and play lead.</span></div>
    <div class="panel">
      <div class="chipsel" id="jgen">${[{id: "any", label: "Any"}, ...meta.genres].map(g => `<button class="chipb ${g.id === st.genre ? "on" : ""}" data-g="${g.id}">${esc(g.label)}</button>`).join("")}</div>
      <div class="row" style="margin-top:10px">
        <button class="btn primary" id="jshuf">🎲 Shuffle</button>
        <input id="jtext" type="text" class="grow" placeholder="${meta.ai ? "Describe it: trance DJ mix, euphoric, big build-ups, A minor" : "Describe it needs an OpenRouter key on the server (OPENROUTER_API_KEY)"}" ${meta.ai ? "" : "disabled"}>
        <button class="btn" id="jdesc" ${meta.ai ? "" : "disabled"}>✨ Create</button>
      </div>
    </div>
    <div id="jplan"></div>`;

  function drawPlan() {
    const el = $("#jplan");
    if (!plan) { el.innerHTML = `<div class="empty">Pick a genre and press 🎲 Shuffle, or describe the mix you want.</div>`; return; }
    const P = plan.progression || {sections: []};
    el.innerHTML = `
      <div class="grid2" style="margin-top:14px">
        <div class="panel">
          <div class="row"><b class="grow">${esc(plan.title || plan.flavor_label || plan.family)}</b>
            <span class="chip">${esc(plan.flavor_label || "")}</span><span class="chip">${plan.bpm} BPM</span><span class="chip">${esc(P.key || "")}</span></div>
          ${plan.notes ? `<div class="small muted" style="margin-top:6px">${esc(plan.notes)}</div>` : ""}
          <table class="sec" style="margin-top:10px"><thead><tr><th>Part</th><th>Instrument</th><th>Sound</th><th>Pattern</th></tr></thead><tbody>
            ${plan.parts.map((x, i) => `<tr><td>${i + 2}</td><td><b>${esc(x.label)}</b></td>
              <td>${x.options?.length ? `<select class="jsnd" data-i="${i}">${x.options.map(o => `<option value="${o.no}" ${o.no === x.sound_no ? "selected" : ""}>${esc(o.name)}</option>`).join("")}
                ${x.options.some(o => o.no === x.sound_no) ? "" : `<option value="${x.sound_no}" selected>${esc(x.sound_name || "")}</option>`}<option value="search">Search all…</option></select>` : esc(x.sound_name || "–")}</td>
              <td class="small muted">${x.hold ? "holds the chord" : esc(x.from || plan.family || "")}</td></tr>`).join("")}
            <tr><td>1</td><td><b>Your lead</b></td><td colspan="2">${(plan.leads || [plan.lead]).filter(Boolean).map(l => `<button class="btn sm jlead ${st.lead?.no === l.no ? "primary" : ""}" data-no="${l.no}" data-name="${esc(l.name)}">${esc(l.name)}</button>`).join(" ")}
              <button class="btn sm jlead ${!st.lead ? "primary" : ""}" data-no="">Keep mine</button></td></tr>
          </tbody></table>
          <div class="row" style="margin-top:10px">
            <label class="small">Split <select id="jsplit">${SPLIT_CHOICES.filter(n => n != null).map(n => `<option value="${n}" ${n === st.split ? "selected" : ""}>${noteName(n)}</option>`).join("")}</select></label>
            <span class="grow"></span><button class="btn primary" id="jsend">Send to MODX</button></div>
        </div>
        <div class="panel">
          <b>Chord progression</b> <span class="small muted">· edit any line (space between chords)</span>
          <div class="jprog">${(plan.scenes || []).map((name, i) => `<label class="f">${i + 1} · ${esc(name)}</label>
            <input type="text" class="jline" data-i="${i}" value="${esc((P.sections[i] || []).join(" "))}">`).join("")}</div>
          <div class="row" style="margin-top:8px"><button class="btn sm" id="jreprog">🎲 New progression</button></div>
        </div>
      </div>
      <div class="panel jperf" style="margin-top:14px">
        <div class="row"><button class="btn primary jbig" id="jplay">▶ Start band</button>
          <div class="jnow"><div class="cn" id="jcn">–</div><div class="small muted" id="jnext"></div></div>
          <span class="grow"></span>
          <label class="small">Chord every <select id="jbars"><option value="0">auto</option><option value="1">1 bar</option><option value="2">2 bars</option><option value="4">4 bars</option></select></label></div>
        <div class="jscenes" id="jscenes"></div>
        <div class="small muted" style="margin-top:8px">The tab plays the chords below the split; the band and pads follow. Changing between Groove/Build-up/Drop/Breakdown plays a one-bar fill first. Sweep the Super Knob up through the build-up.</div>
      </div>`;
    bindPlan(); drawScenes(); drawPlayer();
  }
  function drawScenes() {
    const el = $("#jscenes"); if (!el || !plan) return;
    el.innerHTML = (plan.scenes || []).map((n, i) => `<button class="btn jsc ${i === st.scene ? "on" : ""}" data-i="${i}"><b>${i + 1}</b> ${esc(n)}<span class="small">${esc((plan.progression?.sections?.[i] || []).join(" "))}</span></button>`).join("");
    $$(".jsc", el).forEach(b => b.onclick = () => goScene(+b.dataset.i));
  }
  function flash(n) { const b = $(`.jsc[data-i="${n}"]`); if (b) { b.classList.add("pending"); setTimeout(() => b.classList.remove("pending"), barMs()); } }
  function drawPlayer() { const b = $("#jplay"); if (b) b.textContent = player.on ? "■ Stop band" : "▶ Start band"; }
  function drawNow(cur, next) { if ($("#jcn")) { $("#jcn").textContent = cur; $("#jnext").textContent = next ? `next ${next}` : ""; } }

  function bindPlan() {
    $$(".jsnd").forEach(sel => sel.onchange = () => {
      const row = plan.parts[+sel.dataset.i];
      const set = (no, name) => { row.sound_no = no; row.sound_name = name; save(); drawPlan(); };
      if (sel.value === "search") return openFinder({meter: "4/4", bpm: plan.bpm, onUse: p => set(p.no, p.name), onArp: () => {}});
      set(+sel.value, sel.options[sel.selectedIndex].text);
    });
    $$(".jlead").forEach(b => b.onclick = () => { st.lead = b.dataset.no ? {no: +b.dataset.no, name: b.dataset.name} : null; drawPlan(); });
    $("#jsplit").onchange = e => { st.split = +e.target.value; };
    $("#jbars").value = String(st.bars); $("#jbars").onchange = e => { st.bars = +e.target.value; };
    $$(".jline").forEach(inp => inp.onchange = () => {
      const chords = inp.value.trim().split(/\s+/).filter(c => chordNotes(c).length);
      plan.progression.sections[+inp.dataset.i] = chords.length ? chords : plan.progression.sections[+inp.dataset.i];
      inp.value = plan.progression.sections[+inp.dataset.i].join(" "); save(); drawScenes();
    });
    $("#jreprog").onclick = async () => {
      const fresh = await api("jam/shuffle", {method: "POST", json: {genre: plan.flavor}});
      plan.progression = fresh.progression; save(); drawPlan();
    };
    $("#jplay").onclick = () => player.on ? stopBand() : startBand();
    $("#jsend").onclick = async () => {
      if (player.on) await stopBand();
      const p = {...plan, parts: plan.parts.map((x, i) => ({...x, scenes: x.scenes.map(y => y && (y.no ?? y)), part: i + 2}))};
      const ok = await sendPlanToModx(p, plan.bpm, {split: st.split, othersOff: true, withSounds: true, resetLimits: false,
        lead: {part: 1, sound_no: st.lead?.no ?? null, name: st.lead?.name, full: false, wind: !!st.lead && WIND_RX.test(st.lead.name)},
        expression: true, groove: true, superKnob: true, motion: true, touch: false, swing: 0});
      if (ok) { st.scene = 0; drawScenes(); }
    };
  }

  // ---------- top controls ----------
  $$("#jgen .chipb").forEach(b => b.onclick = () => { st.genre = b.dataset.g; $$("#jgen .chipb").forEach(x => x.classList.toggle("on", x === b)); });
  $("#jshuf").onclick = async () => {
    if (st.busy) return; st.busy = true;
    try { if (player.on) await stopBand(); plan = await api("jam/shuffle", {method: "POST", json: {genre: st.genre}}); st.lead = null; st.scene = 0; save(); drawPlan(); }
    catch (e) { toast(e.message); } finally { st.busy = false; }
  };
  $("#jdesc").onclick = async () => {
    const text = $("#jtext").value.trim(); if (!text || st.busy) return;
    st.busy = true; $("#jdesc").textContent = "Thinking…";
    try { if (player.on) await stopBand(); plan = await api("jam/describe", {method: "POST", json: {text}}); st.lead = plan.lead || null; st.scene = 0; save(); drawPlan(); }
    catch (e) { toast(e.message, 6000); } finally { st.busy = false; $("#jdesc").textContent = "✨ Create"; }
  };
  $("#jtext")?.addEventListener("keydown", e => { if (e.key === "Enter") $("#jdesc").click(); });
  drawPlan();
  cleanup = () => { if (player.on) stopBand(); };
}
