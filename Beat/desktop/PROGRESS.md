# Beat Studio (native desktop) — PROGRESS

**This is the living status doc for the NATIVE desktop app. Read this first when
continuing in a new chat.** Current version: **v0.14.2** (shown in the window title bar as
`Beat Studio · v0.14.2 · AI matching ✓`).

## v0.14.2 — thinking OFF app-wide (user directive)
User: "any model used on this app should ALWAYS be think=false." Enforced centrally in
`llm.chat`: every request gets payload `think:false` AND `_no_think_messages` appends `/no_think`
to the system message (Qwen3 template reads it), and replies are stripped of any `<think>…</think>`
via `_THINK_RE`. Applies to arrange AND the Test ping. Result on the a3b model: arrange 178s→139s
(richer 9-track output). Still server-throughput-bound (35B MoE) — if snappier is ever wanted,
`qwen2.5-coder:14b` would likely be faster, but a3b-no-think is the user's chosen default.

## v0.14.1 — AI arrange VERIFIED LIVE + model-dropdown + freeze fix
**The whole arrange pipeline works end-to-end against the user's REAL home server** (Ollama at
`192.168.2.200:11434`). Test: a 3-track sketch (kick+snare + hummed melody D4/F4) → the model
returned a full 6-track arrangement (Kick/Snare/Hat cleaned + a NEW Bass D2/F2 + Pad D3/F3 + Lead
keeping the melody) with coherent D/F harmony across three octaves. This is the "beatbox a seed →
full track" vision proven. Config saved: `desktop/config.json` = `http://192.168.2.200:11434/v1`,
model **`qwen3.5:35b-a3b`** (fast MoE, ~3B active). NOTE: even warmed, generation took ~178s for
88 notes — usable (off-thread, title shows progress) but SLOW; next optimization = disable qwen3
"thinking" (/no_think) or try `qwen2.5-coder:14b` (9GB, fast, good at JSON). The plain
`qwen2.5:32b-instruct-q4_K_M` TIMED OUT cold at 180s.

Three bugs/UX fixes this patch:
- **Test-connection FREEZE (user hit it):** a bare IP like `192.168.2.200` made `urllib` raise a
  `ValueError` DURING request construction (before the try), and `ping()` only caught `LLMError`,
  so the worker thread died silently → "Testing…" forever. Fixed: `llm.normalize_base_url` (bare
  IP → `http://…:11434/v1`, keeps explicit scheme/port/path), request built INSIDE the try, `ping`
  catches everything, dialog worker double-guards + a live "⏳ Testing … Ns" counter so you always
  know it's alive. Ping timeout 90s (big models load slowly), arrange 300s.
- **Model DROPDOWN (user's idea):** `llm.list_models` hits `/v1/models`; the dialog auto-loads the
  server's models on URL entry / open and shows them in an editable combo + ↻ reload — so you pick
  the exact tag instead of mistyping it (which is what broke it: `qwen2.5:32b-instruct` vs the real
  `…-q4_K_M`). Verified live: lists all 7 of the user's models.

## v0.14.0 — AI ARRANGE LAYER + HPSS ("stop working double") — the strategic pivot
User's insight (correct, restated over several sessions): don't make a model *hear* audio —
turn the beatbox into NUMBERS (our DSP+CLAP already do), then hand that symbolic sketch to a big
reasoning LLM on their **home server**. It reasons over the WHOLE track at once and expands the
sketch into a **full musical arrangement** (long melody behind the ts/pf, bassline, harmony,
cleaned drums), which we render with our own synth engine → user just tweaks. This ends the
"beatbox AND then build the whole track by hand" double-work. Philosophy locked: **musical, not
exact** — `ps ps ps` heard as `psssst ps` is fine if it sounds good; go with the flow like a DAW.

New files: **`config.py`** (desktop/config.json: `ai_base_url`/`ai_model`/`ai_api_key`/`ai_enabled`;
default local Ollama), **`llm.py`** (stdlib-only OpenAI-compatible `/chat/completions` client —
works with Ollama/vLLM/LM Studio/llama.cpp; `chat()`, `ping()`, `LLMError`), **`arrange.py`**
(`project_to_sketch` → compact symbolic JSON; `_SYSTEM` producer prompt constrained to our
`synth.DRUMS`/`WAVES` vocab; `_extract_json` tolerant of fences/prose; `arrangement_to_project`
coerces bad kind/sound → playable; `arrange()` = full round-trip → new `Project`), **`aidialog.py`**
(AI Settings dialog: editable **URL + model name** + optional key + **Test** (threaded ping) —
user can swap servers/models anytime).

Wiring (`mainwindow.py`): **AI menu** → "✨ Arrange into a full track" (**Ctrl+R**) + "AI Server
Settings…". `_arrange_with_ai` runs the LLM call OFF the UI thread (daemon thread → `arrange_done`
Signal → `_on_arrange_done` swaps the project via `_set_project` + `_commit` so **Ctrl+Z restores
the pre-arrange groove**). If unconfigured it opens Settings first. Errors (dead server, bad JSON)
surface in the title bar, never crash/hang (short timeouts).

**HPSS (`groove.hpss`)** = the "don't cut the background tone" fix (librosa `effects.hpss`, falls
back to (buf,buf)). **`groove.melody_line`** tracks the harmonic layer's continuous pitch and
MERGES contiguous same-pitch frames into HELD notes (allows a few unvoiced frames so a pop over
the tone doesn't split it) → a held tone becomes ONE long note, not one-note-per-hit. Wired into
`extract.analyze_clusters`: computes hpss, and appends a synthetic **melody cluster** (`suggest=
"melody"`, `is_melody=True`, pre-built held-note hits) that flows through the existing review
dialog + `build_from_review` melody path unchanged. VERIFIED headlessly: held A4→C5 tones → 2 clean
held notes (MIDI 69/72, full length); arrange serialize/parse + bad-vocab coercion + dead-server
LLMError all pass; window builds, title shows v0.14.0.

STILL TODO / next: (1) test arrange against the user's REAL home server (need URL + model tag —
they likely run Ollama; `Ollama-Test` folder exists). (2) percussion onsets still run on the full
hp buffer, not the percussive layer — could move them to `perc` to stop the tone spawning drum
onsets (needs real-audio tuning). (3) melody cluster can double-count if a tonal attack also makes
onset clusters — review dialog lets the user "ignore" those for now. (4) still want a real MELODIC
beatbox sample to tune `melody_line` thresholds.


> ⚠️ VERSION GOTCHA: bump `beatstudio/__init__.py __version__` by EDITING the string directly
> (not `sed` find-replace — a lost bump once left every later `sed` searching for a number that
> wasn't there, so the title silently stayed stale while the code advanced). Verify after: the
> title bar must show the new number.

---

## HOW THE APP WORKS NOW (the core loop, as of v0.13.0)

The philosophy pivoted (user's insight): **"My Sounds" pre-registration is BACKWARDS.** The right
flow is beatbox anything → software finds the distinct sounds → **asks you what each is** → builds
with REAL instruments → and **learns your kit** so it recognises them next time ("train along, not
beforehand"). When you press **Record master**:
1. `extract.analyze_clusters()` — high-pass (kills DC rumble) → onsets (spectral flux) → tempo
   (librosa) → quantize to 1/16 grid → cluster by CLAP embedding. Per cluster: a 0.5s preview +
   a SUGGESTED category (from `usermodel` if learnt, else acoustic guess, else pitch→melody) +
   per-hit melody note (`groove.note_of`) + a matched clean synth `preset` (`groove.pick_preset`).
2. `reviewdialog.ReviewDialog` — the QUESTIONNAIRE ("What did you just beatbox?"): one row per
   sound with ▶ (hear YOUR sound), 🔊 (hear the CHOSEN instrument), and a category dropdown
   (kick/snare/hat/…/bass/melody/keep-my-sound/ignore). Shows "(learned)" vs "(guess)".
3. `extract.build_from_review()` — builds tracks with real instruments AND
   `usermodel.add(embedding, category)` for each → learns. Melody category uses the matched synth
   preset + real per-note pitches.
4. `usermodel.UserModel` (`desktop/usermodel/labels.npz`) — CLAP-embedding k-NN. Verified:
   label once → re-analysis auto-recognises the same sounds (conf>0.5).

New files since the earlier changelog: **`usermodel.py`, `reviewdialog.py`**; new funcs in
`groove.py` (`highpass`, `classify_acoustic`, `detect_pitch`, `note_of`, `pick_preset`) and
`extract.py` (`analyze_clusters`, `build_from_review`; old `smart_extract` still there).

## HONEST OPEN ISSUES (priority order for next session)
1. **Tempo unstable** — same file read 92 vs 167 BPM depending on high-pass. Add a confirm/
   tap-tempo step in the questionnaire, or a better beat tracker. This is the shakiest part.
2. **Onset over-detection** — ~56–76 hits on a 30s take; some are breaths, and SUSTAINED melodic
   notes get chopped into many notes. For melody: merge consecutive same-pitch contiguous hits
   into one held note (but keep redobles = re-articulated repeats separate).
3. **Cold-start suggestions rough** — first-time acoustic guesses are often wrong (that's OK by
   design; user corrects once, model learns). Could improve the initial guess.
4. **pick_preset** timbre match is approximate (e.g. low sine → 'bass'). Fine for now.
5. Need a **real MELODIC beatbox sample** from the user to tune note-tracking + timbre. Also want
   Recording 1/2 style drum samples to keep tuning onsets/clustering.

## READING/DEBUGGING REAL AUDIO
- `desktop/analyze.py <file>` runs a recording through the full pipeline + prints tempo/onsets/
  clusters/suggestions + saves a spectrogram PNG. Use it to tune on the user's real audio.
- User's FLACs have BROKEN/STREAMED headers (frames=int64max → libsndfile `psf_fseek` fails,
  soundfile can't read). Decode first with GStreamer (ffmpeg NOT installed):
  `gst-launch-1.0 -q filesrc location=IN.flac ! decodebin ! audioconvert ! audioresample !
   audio/x-raw,format=S16LE,channels=1,rate=44100 ! wavenc ! filesink location=OUT.wav`
- Put user beatbox recordings in `desktop/samples/`.

---

## What this is / the pivot

`Documents/APPS/Beat` began as a **web app** ("Beatbox to MIDI", `Beatbox to MIDI.dc.html`,
last at web-v0.7.6) that kept **stuttering** (full-canvas repaints in the browser). On
2026-07-01 the user decided to go **native**: a real Linux desktop app, NOT Electron/Tauri
(those are still browser engines). The native app lives in **`desktop/`** and is the primary
product now. The **web app stays as the phone capture companion** (record on the phone
offline → sync to the desktop via `server.py` → open under File ▸ Grooves). Nothing from the
web app was thrown away — its features were ported.

Goal the user keeps restating: **feature parity with the web version**, good recording, and
**AI sound matching** (now shipped).

---

## How to run

```bash
bash ~/Documents/APPS/Beat/desktop/run.sh          # or double-click the "Beat Studio" desktop icon
```
- Desktop icon installed via `desktop/install-launcher.sh` (icon `desktop/icon.png`,
  `desktop/BeatStudio.desktop`).
- System deps the user already installed: `libxcb-cursor0` (to launch), **`libportaudio2`**
  (REQUIRED for sound + mic).
- Python venv at `desktop/.venv` (created `--system-site-packages`). Key deps:
  PySide6 6.11, numpy, scipy, sounddevice, mido, **torch 2.12 (CPU), transformers 5.12,
  soundfile** (for CLAP AI).
- Controls: **Ctrl+scroll** zoom, **Space** play/stop, **Ctrl+Z / Ctrl+Shift+Z** undo/redo,
  **Ctrl+N** new, **Ctrl+Backspace** clear beats.
- Headless verify pattern (used for all testing):
  `QT_QPA_PLATFORM=offscreen BEAT_NO_GL=1 ./.venv/bin/python <script>` and `w.grab().save('ref/x.png')`.
  Reference screenshots (web + native) are in `desktop/ref/`.

**Versioning:** bump `beatstudio/__init__.py` `__version__` on EVERY change — it's shown in
the title bar so the user can confirm a relaunch picked up the new build.

---

## Architecture / files (`desktop/beatstudio/`)

- **`mainwindow.py`** — assembles everything; transport; recording flow; undo/redo; menu;
  wires all signals. Starts with `empty_project()` (4 empty tracks Kick/Snare/Hat/Square).
- **`timeline.py`** — `QGraphicsView` + OpenGL viewport. Custom-paints ONLY the exposed rect
  in `drawBackground`/`drawForeground` (this is the anti-stutter fix). `setAlignment(Left|Top)`
  so rows line up with headers. Handles beat editing (click-add / drag-move / dbl-click delete /
  snap), marquee select, right-click → per-beat EQ, live record waveform + markers, minimap
  mirror circle.
- **`headers.py`** — left track column (colour chip, name, subtitle, REC/S/M/⚙ buttons,
  Extract/Original toggle for `has_original` lanes, + New track). Custom-painted with hit-testing.
- **`ruler.py`** — top bar-number ruler; drag to set loop region.
- **`toolbar.py`** — ▶ ■ ↺(undo) ↻(redo) 🗑(clear+confirm) 🎤 ♩(metro) BPM · level meter ·
  notes/tracks · Save/Grooves/My Sounds. `_LevelMeter` shows input volume while recording.
- **`settings.py`** — bottom track-settings panel (⚙): instrument picker (unified drum/synth/
  My-Sounds list; KEEPS beats on change), Bass/Mid/Treble EQ, Test, per-track Record,
  Play-Original checkbox, Delete, Close.
- **`synth.py`** — numpy voices: drums, synth presets, sampler (`sample_voice` = resample +
  sustain-loop), 3-band RBJ EQ, metronome click. `SR=44100`.
- **`render.py`** — `render_project(project, samples, orig)` → mono buffer (mute/solo, EQ,
  velocity, note length, metronome, play-original slices). `_voice_for` builds one voice.
- **`audio.py`** — `AudioEngine`: sounddevice OutputStream, loop, live cursor, `one_shot`
  preview; virtual-clock fallback if no PortAudio.
- **`recorder.py`** — `Recorder`: sounddevice InputStream; `live_env` (per-block RMS for the
  live waveform), `live_onsets`, `peak` (clip warn).
- **`analysis.py`** — `onsets_from` (spectral-flux attack detection — see below),
  `seg_features` (24-D: 5 spectral + 6 bands + 13 MFCC), `match_dist`, `onset_start`.
- **`extract.py`** — `multi_extract` = try CLAP → DSP gallery-match → brightness band-split.
  `clap_extract` embeds each hit, matches gallery by cosine or zero-shot classifies.
- **`ai_match.py`** — **CLAP** (`laion/clap-htsat-unfused`): `load()`, `embed()` (512-D, uses
  `out.pooler_output`, resample to 48000, processor kwarg `audio=`), `cosine_dist`, `classify()`
  zero-shot vs text LABELS. Fully local/offline after one-time ~600MB weight download to
  `~/.cache/huggingface`.
- **`sounds.py`** — `SoundLibrary` (`desktop/mysounds/` = index.json + <id>.npy); DSP features +
  CLAP embeddings cached per sound.
- **`soundsdialog.py`** — My Sounds window: list w/ per-sound ▶ buttons, record (live waveform),
  waveform editor (trim/base-pitch/gain/loop), looping Preview.
- **`minimap.py`** — bottom-right hover corner: exact scaled miniature, draggable dot (reaches
  every corner), mirror circle on real grid. `zoombar.py` = −/100%/+ pill stacked ABOVE it.
- **`beateq.py`** — per-beat EQ popover (Tune/Bass/Mid/Treble/Volume on the selection).
- **`persistence.py`** — JSON save/load, `mido` MIDI export, `from_dict` tolerant of the WEB
  groove format (phone sync via `server.py` → `Beat/synced/`).
- **`model.py`** — `Project` / `Lane` / `Event` dataclasses. `empty_project()`, `demo_project()`.

---

## DONE (feature parity with web, verified headlessly)

Audio playback · transport (play/pause/stop/space, metronome, BPM, loop) · grid editing
(add/move/delete/snap, marquee) · track settings panel (instrument switch keeps beats, EQ,
Test, Delete) · header buttons (REC/solo/mute/gear/+track) · mic recording + onset detection +
live markers + live waveform (per-track AND master full-height) + metronome-while-recording ·
**Record master → auto-split** into instrument tracks · **My Sounds** sampler gallery + waveform
editor + per-sound play + looping preview · **AI matching (CLAP)** with zero-shot fallback (works
WITH or WITHOUT a gallery) · **Extract/Original toggle** per track (header + gear) · per-beat EQ
popover + marquee · minimap (exact miniature + dot + mirror) · zoom controls · MIDI export ·
save/load · phone-sync groove loading · undo/redo (buttons + shortcuts) · clear-all (confirm) ·
starts with a clean empty grid.

### Two hard bugs fixed recently
- **v0.9.1 — onset detection rewrite** (the "giant green note / no rhythm" bug). Old detector was
  level-based and let one hit's note run until energy fell <25% of peak → a single hit became a
  whole-bar note (plus an over-aggressive timbre merge). Now **spectral-flux attack detection**
  (hop 256 / win 1024, positive spectral-change novelty, adaptive-mean threshold ×1.4 + floor,
  45 ms refractory) → ONE onset per hit; note length SHORT by default (decays under 40% of its
  own peak, hard-capped 0.7 s and by the gap to the next onset), NO merge. Verified:
  "pf ts pf ts pf pf" → 6 distinct ~0.05 s hits; a sustained "tsssss" → ~0.47 s.
- **v0.8.2 — vertical misalignment**: `QGraphicsView` centres content smaller than the viewport,
  so rows drifted below the headers. Fixed with `setAlignment(Qt.AlignLeft|Qt.AlignTop)`.
- **v0.9.3 — row misalignment (second cause)**: the track-header column had an internal
  `_HEADER_BAND` (=RULER_H) caption strip that pushed its rows down 26px while the timeline rows
  started at y=0. Fixed: `_HEADER_BAND = 0` (rows start at 0, aligned to the grid) and the
  "TRACK · REC · SOLO · MUTE" caption moved into the `CornerBox` (grid row 0, col 0). Verified
  header row 0 and timeline row 0 share the same global top (0px diff).
- **v0.9.2/0.9.3 — undo/redo buttons**: always present in the toolbar (↺ ↻), GREYED (disabled
  `:disabled` style) when the stack is empty — never hidden, never shift the layout (per user
  request). Enable on first edit / after undo.

---

## v0.12.0 — REVIEW QUESTIONNAIRE + "TRAIN ALONG" (the right architecture)

Reframed per the user: "My Sounds" (pre-registering sounds) is BACKWARDS. Correct flow =
beatbox anything → software finds the distinct sounds → **ask the user what each one is** →
build with REAL instruments → and LEARN so it recognises them next time. No pre-registration;
labelling happens AFTER, and doubles as training data.

Flow now (`_stop_master_record`):
1. `extract.analyze_clusters(buf, sr, start, usermodel)` → high-pass, onsets, tempo, quantize,
   cluster (CLAP), and per cluster: a representative 0.5s preview + a SUGGESTED category
   (from `usermodel` if learnt, else acoustic guess `groove.classify_acoustic`, else pitch→melody).
2. `reviewdialog.ReviewDialog` — a per-sound questionnaire: ▶ play example, pick instrument from
   `usermodel.CATEGORIES` (kick/snare/hat/…/bass/melody/keep-my-sound/ignore), shows "(learned)"
   vs "(guess)".
3. `extract.build_from_review(clusters, decisions, usermodel)` → tracks with real instruments,
   AND `usermodel.add(embedding, category)` for each → **learns your kit** (persisted).
4. `usermodel.UserModel` (`desktop/usermodel/labels.npz`): CLAP-embedding k-NN classifier;
   `predict()` = nearest-fingerprint vote. Verified: after labelling once, re-analysis
   auto-recognises 9/9 sounds (conf>0.5). This IS "train along, not beforehand."

NOTE: "My Sounds" gallery still exists but is now secondary; the review flow is the main path.
Acoustic suggestions are rough (cold start) but the user corrects them once and the model learns.
Tempo detection still unstable (Recording 2: 92 pre-HP, 167 post-HP) — needs work/confirm-in-UI.

## v0.10.0 — MUSICAL PIPELINE (the "random rhythm" fix)

The big fix for "the result is random as fuck." Master record now runs a real MIR pipeline
(`groove.py` + `extract.smart_extract`), replacing the raw-onset placement:
1. **Onsets** (spectral flux, `analysis.onsets_from`).
2. **Tempo** — `groove.detect_tempo` (librosa `feature.rhythm.tempo`, IOI-median fallback);
   sets `project.bpm`. Verified: recovers 120 BPM from a humanized take.
3. **Quantize** — `groove.quantize` snaps every hit to the nearest 1/16 with a circular-mean
   phase, anchored so the earliest hit = beat 0 → clean 0.25 multiples (verified maxGridErr 0.0).
4. **Cluster** — `groove.cluster` (sklearn AgglomerativeClustering cosine / numpy fallback)
   groups hits by CLAP embedding so the SAME sound → ONE track; each cluster centroid matched to
   nearest instrument / My Sound (`extract._label_centroid`).

Deps added: **librosa, scikit-learn** (in `.venv`). Also: **beat LED** in the toolbar
(`toolbar.pulse_beat`) blinks every beat while recording (green, red on the downbeat); the
metronome click now plays during record only if enabled, but the LED ALWAYS blinks
(`_start_beat_clock` / `_metro_click`) — fixes "metronome does nothing on record."

Cluster threshold (`groove.cluster thresh=0.35`) may merge similar synth sounds (test gave 2
tracks for kick/snare/hat) — tune on real beatbox.

## KNOWN GAPS / TODO (still not at web parity)

1. **Per-lane volume-automation curves** (draggable gain points along a lane) — not ported.
2. **Quantize + sensitivity controls** — web had global quantize + onset-sensitivity; not ported.
3. **Record countdown** (3-2-1 before capture) — not ported.
4. **AI matching** — v0.9.4 switched to AUDIO-TO-AUDIO: `ai_match.instrument_refs()` renders each
   built-in voice, embeds it with CLAP, and `nearest_instrument(emb)` returns the closest; a My
   Sound only wins if it's closer (`clap_extract`). Verified built-in voices self-match 7/7 (~0
   dist). Real-beatbox→synth-reference has a domain gap; the BEST results come from the user
   recording their own kick/snare/hat into My Sounds (real→real). Could bundle real one-shot
   samples as references later. Text zero-shot `classify()` still exists but is no longer the
   primary path. `instrument_refs()` is prebuilt in the AI preload thread.
5. **Undo/redo buttons looked "missing"** — they ARE present (↺ ↻ in the toolbar) but start
   DISABLED (nothing to undo yet); v0.9.2 added a visible `:disabled` style so they're dim-but-
   clearly-there. If the user still says they're missing, double-check the relaunch picked up the
   new version (title bar).
6. Live-monitor (🎤) and phone-sync (📡) toolbar buttons are placeholders/partial.

---

## NOTES for whoever continues

- The user is a beatboxer, non-developer, and gets frustrated when asked to confirm instead of
  acting — **just build, don't over-ask**. Bump the version each change so they can see it landed.
- CLAP is **local/offline** after the first weight download — this was a point of confusion;
  reassure if asked. **Ollama can NOT do this** (text/vision LLM only, no audio embeddings).
- The user's real test phrase is "pf ts pf ts pf pf" (kick/hat pattern). Recording quality +
  rhythm is what they judge on. After the v0.9.1 onset fix, ask them to re-test.
- Memory file: `~/.claude/projects/-home-sebastian-Documents-APPS/memory/beat_project.md`.
- Web app changelog/status: `Beat/PROGRESS.md` (the OTHER progress file, for the web build).
