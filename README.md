# StageKit

Self-hosted web app for preparing and performing songs on a Yamaha MODX M6.

- **Library**: paste a YouTube link or upload audio. The server downloads it and separates stems with UVR models (an MDX vocal model, then Demucs for drums / bass / other).
- **Song page**: YouTube playback, stem mixer (mute / solo / volume, synced), WAV and zip downloads, detected key and BPM with one-tap alternatives.
- **Song card**: key, BPM, meter, MODX Performance (bank MSB/LSB + program), sections mapped to scene buttons 1–8, chords and cues, notes.
- **Sound finder**: all 3,487 MODX M factory Performances and 10,922 arpeggios from Yamaha's Data List (Jan 2026, OS 3.0). Pick a feel (Indian, ballad, devotional, pop, cinematic, dance) and get Performance suggestions plus groove arpeggios that fit the song's meter and tempo. **▶ Try** plays a preset on the MODX over USB; **Use** stores it on the song.
- **Scene builder (experimental)**: 172 matched groove styles (drums + bass + guitar/keys sets such as 70s Rock, 12/8 Pop, Unplugged, 6/8 Ballad) laid out over the 8 scenes (intro, 3 mains, 2 fills, break, ending). **Send to MODX** optionally loads a matching sound into each Part (Single Part bank select, MSB 63 on the Part's channel — MODX MIDI I/O Mode must be Multi), then writes the arps, scene arp selections and tempo with Yamaha parameter-change SysEx from the Data List. Only the edit buffer changes; press **STORE** on the MODX to keep it. Chrome must be allowed full MIDI (SysEx) access.
- **Tabla studio**: bol → key map (built-in Hands Kit #2813 preset, or your own samples), starting pattern sets for Keherwa, Dadra, Rupak, Teentaal and Jhaptaal laid out as the 8 scenes, live preview on the MODX, and .mid export (single or zip of all 8) to turn into user arpeggios with Put Track to Arpeggio.
- **Chords**: approximate chord timeline (no AI API needed), chord follow while playing, transpose, fill section chords; **Chords only** mode skips stems for a playable chart in under a minute.
- **Login**: one user from `.env`, sessions you can sign out of; 5 wrong attempts lock that IP for 5 minutes.
- **MODX control (live view, USB MIDI)**: loads each song's Live Set slot or Performance, sends the scene for each section (Scene CC, default 92), follows scene buttons you press on the MODX, and reminds you to set/reset MODX transpose.
- **Set lists** and **Live view**: full-screen cues (current section, scene number, chords, next section), page-turner pedal and swipe support, screen kept awake, works offline once opened. Over USB MIDI (Chrome/Edge, Android via OTG) it sends Bank Select + Program Change to load each song's Performance.

Install it as an app: open the site in Chrome (Android or Windows) → menu → **Install app** / **Add to Home screen**.

## Deploy on the paperclip VM (OCI Ampere A1, Ubuntu)

```bash
# 1. Docker (skip if installed)
curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $USER && newgrp docker

# 2. Code
mkdir -p ~/stagekit && cd ~/stagekit   # copy the project files here (scp/git)
cp .env.example .env && nano .env       # set APP_USER and APP_PASSWORD (your single login)
mkdir -p data && sudo chown 1000:1000 data

# 3. Build and run (first build ~10 min on ARM)
docker compose up -d --build
curl -s localhost:8080/api/health        # {"ok":true}
```

**HTTPS (needed for install-as-app, Web MIDI and screen wake lock):**

1. Cloudflare DNS: `A stage.lumivoxx.com → <paperclip public IP>` (grey cloud, so uploads aren't capped).
2. OCI: allow TCP 80 and 443 in the VM's NSG (`nsg-paperclip`), and in iptables:
   `sudo iptables -I INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT && sudo netfilter-persistent save`
3. Caddy: add `Caddyfile.example` to `/etc/caddy/Caddyfile`, then `sudo systemctl reload caddy`.

Update later: `git pull` (or copy files) then `docker compose up -d --build`. Data lives in `./data` (back it up).

## Things to know

- **Speed**: no GPU on the VM, so separation runs on CPU, one song at a time. Measured on 2 cores, the default `balanced` preset takes about 3.5 minutes per minute of audio (a 4-minute song ≈ 15 min; the 4-core VM should be roughly twice as fast). `fast` is about 2 min per minute of audio. `best` (RoFormer) is ~30 min per minute on CPU — only use it on a GPU machine. The first song downloads the models into `data/models` (~0.4 GB for balanced).
- **YouTube from a cloud server** is often blocked ("Sign in to confirm you're not a bot"). Fix: export `cookies.txt` from a logged-in browser (e.g. the "Get cookies.txt LOCALLY" extension), save as `data/cookies.txt`, set `YTDLP_COOKIES=/data/cookies.txt`, restart. Uploading the audio file always works.
- **MIDI**: Scene CC 92 is confirmed in the MODX M manual (Utility → set the same Scene CC there). From the MODX M Data List (MIDI Data Format): Live Set slot = Bank MSB 62, LSB = page−1, Program = slot−1; factory Performance n = MSB 65, LSB = (n−1) div 128, Program = (n−1) mod 128; User banks 1–5 = MSB 66, LSB 0–4; Library = MSB 66, LSB 8+. Live Set selection acts on whichever Live Set is open on the MODX, so open your gig Live Set before the show. Test once on your M6 with **MIDI → Send current song**. On the MODX, set MIDI receive channel to match (default 1).
- **Storage**: ~250 MB per song (WAV stems + previews). Delete songs you no longer need.
- **Use**: for personal practice and performance. Don't redistribute separated stems of copyrighted songs.

## Run locally (test on your laptop before deploying)

**Windows:** install Python 3.11 or 3.12 (tick "Add to PATH") and ffmpeg (`winget install Gyan.FFmpeg`), then double-click **run-windows.bat**. The first run installs packages (5–10 min). Chrome opens http://localhost:8080. The login is `deepak` / `localtest`; change it at the top of the .bat.

- Web MIDI and SysEx work on `localhost` without HTTPS, so connect the MODX with your USB-B printer cable and test everything from Chrome on the laptop.
- The tablet can't use this local copy for MIDI (it would need HTTPS). Test the tablet after deploying to the VM.
- Data stays in the `data` folder next to the script.

**Linux/Mac:**

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt
DATA_DIR=./data COOKIE_SECURE=0 APP_USER=deepak APP_PASSWORD=localtest uvicorn app.main:app --port 8080
```

On a PC with an NVIDIA GPU, install `audio-separator[gpu]` and a CUDA build of PyTorch instead; separation then takes seconds.

## API

`GET/POST /api/songs`, `POST /api/songs/upload`, `GET/PATCH/DELETE /api/songs/{id}`, `POST /api/songs/{id}/retry`, `POST /api/songs/{id}/stems`, `GET /api/songs/{id}/chords`,
`GET /api/songs/{id}/preview/{stem}.mp3`, `GET /api/songs/{id}/stem/{stem}.wav`, `GET /api/songs/{id}/stems.zip`,
`GET/POST /api/setlists`, `PUT/DELETE /api/setlists/{id}`, `GET /api/modx/{categories,performances,arps,suggest,styles,scene-plan}`. Stems: vocals, drums, bass, other, instrumental, original.
