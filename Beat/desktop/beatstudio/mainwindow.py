"""Main window — assembles toolbar, ruler, track headers and the timeline with
classic DAW scroll-syncing (ruler follows horizontal scroll, headers follow vertical)."""
import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QGridLayout, QFrame, QFileDialog)
from PySide6.QtGui import QPainter, QPen, QColor, QKeySequence, QShortcut, QAction
from PySide6.QtCore import Qt, QTimer

from . import theme
from .model import Project, demo_project, empty_project, Lane, Event
from .timeline import TimelineView
from .ruler import Ruler
from .headers import TrackHeaders
from .toolbar import Toolbar
from .audio import AudioEngine
from .render import render_project, _voice_for
from .synth import SR, click as synth_click
from .settings import SettingsPanel
from .recorder import Recorder
from .analysis import onsets_from, gate_lin
from .extract import multi_extract, smart_extract, analyze_clusters, build_from_review
from .usermodel import UserModel
from .reviewdialog import ReviewDialog
from .minimap import Minimap
from .beateq import BeatEQ
from .sounds import SoundLibrary
from .soundsdialog import SoundsDialog
from . import persistence
from . import ai_match
from . import config as appconfig
from . import arrange as arranger
from .aidialog import AISettingsDialog
from . import __version__
import threading

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../desktop
_PROJECTS_DIR = os.path.join(_HERE, "projects")
_SYNC_DIR = os.path.join(os.path.dirname(_HERE), "synced")           # Beat/synced (phone sync)
_MYSOUNDS_DIR = os.path.join(_HERE, "mysounds")


class CornerBox(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedSize(theme.HEADER_W, theme.RULER_H)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), theme.PANEL)
        p.setPen(QColor("#4a4a56"))
        p.setFont(theme.mono(8, 500))
        p.drawText(11, 16, "TRACK · ● REC · SOLO · MUTE · ⚙")
        p.setPen(QPen(theme.BORDER_2, 1))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class MainWindow(QMainWindow):
    from PySide6.QtCore import Signal as _Signal
    ai_loaded = _Signal(bool)
    arrange_done = _Signal(object, str)   # (Project|None, error message)

    def __init__(self, project: Project | None = None):
        super().__init__()
        self.project = project or empty_project()
        self._set_title()
        self.resize(1440, 900)
        self.setStyleSheet(f"QMainWindow{{background:{theme.BG.name()};}}")

        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        self.toolbar = Toolbar(self.project)
        root.addWidget(self.toolbar)

        grid_host = QWidget()
        g = QGridLayout(grid_host); g.setContentsMargins(16, 8, 16, 16); g.setSpacing(0)
        self.timeline = TimelineView(self.project)
        self.ruler = Ruler(self.timeline)
        self.headers = TrackHeaders(self.project, self.timeline)
        g.addWidget(CornerBox(), 0, 0)
        g.addWidget(self.ruler, 0, 1)
        g.addWidget(self.headers, 1, 0)
        g.addWidget(self.timeline, 1, 1)
        g.setColumnStretch(1, 1); g.setRowStretch(1, 1)
        # panel frame around the grid
        grid_host.setStyleSheet("")
        root.addWidget(grid_host, 1)

        # bottom settings panel (hidden until you open a track's gear)
        self.settings = SettingsPanel(self.project)
        self.settings.hide()
        self.settings.changed.connect(self._on_settings_changed)
        self.settings.delete_requested.connect(self._delete_track)
        self.settings.closed.connect(self.settings.hide)
        self.settings.closed.connect(self._commit)
        self.settings.test_requested.connect(self._test_instrument)
        self.settings.record_requested.connect(self._toggle_record)
        root.addWidget(self.settings)

        # minimap + zoom overlays (bottom-right of the timeline)
        self.minimap = Minimap(self.timeline)
        self.minimap.raise_()
        from .zoombar import ZoomBar
        self.zoombar = ZoomBar(self.timeline, self.minimap)
        self.minimap.zoombar = self.zoombar
        self.zoombar.raise_()

        # scroll syncing
        self.timeline.scrolled.connect(self.ruler.update)
        self.timeline.scrolled.connect(self.headers.update)

        # interactions
        self.headers.action.connect(self._on_header_action)
        self.headers.add_track.connect(self._add_track)
        self.timeline.edited.connect(self._on_edit)
        self.timeline.committed.connect(self._commit)
        self.timeline.context_requested.connect(self._open_beat_eq)
        self.beat_eq = BeatEQ(self)
        self.beat_eq.changed.connect(self._on_beat_eq_changed)
        self.beat_eq.preview.connect(self._preview_beat)
        self.beat_eq.closed.connect(self._commit)
        self.toolbar.play.connect(self._toggle_play)
        self.toolbar.stop.connect(self._stop)
        self.toolbar.metronome.connect(self._toggle_metro)
        self.toolbar.bpm_changed.connect(self._set_bpm)
        self.toolbar.record_master.connect(self._toggle_master_record)
        self.toolbar.save.connect(self._save_project)
        self.toolbar.grooves.connect(self._open_grooves)
        self.toolbar.my_sounds.connect(self._open_my_sounds)
        self.toolbar.undo.connect(self._undo)
        self.toolbar.redo.connect(self._redo)
        self.toolbar.clear_all.connect(self._clear_beats_confirm)
        self.ruler.loop_changed.connect(self._on_loop_changed)

        # undo/redo state
        self._committed = persistence.to_dict(self.project)
        self._undo_stack = []
        self._redo_stack = []
        self._refresh_undo_buttons()

        self._build_menu()
        # Preload the CLAP AI model in the background so extraction never blocks the UI.
        self._ai_ready = False
        self.ai_loaded.connect(self._on_ai_loaded)
        if ai_match.available():
            threading.Thread(target=self._preload_ai, daemon=True).start()
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._toggle_play)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._redo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self._redo)

        # transport + audio
        self.engine = AudioEngine()
        self.recorder = Recorder()
        self._rec_lane = None
        self._orig_rec = None       # whole-groove master take
        self._lane_audio = {}       # lane_id -> recorded float32 (original take)
        self._spb = 60.0 / max(1, self.project.bpm)
        self.library = SoundLibrary(_MYSOUNDS_DIR)
        self.usermodel = UserModel(os.path.join(_HERE, "usermodel"))   # learns your kit from labels
        self.cfg = appconfig.load()                                    # AI server settings
        self._arranging = False
        self.arrange_done.connect(self._on_arrange_done)
        self._samples = self.library.samples_dict()
        self.settings.set_my_sounds(self.library.sounds)
        self._timer = QTimer(self); self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._metro_timer = QTimer(self); self._metro_timer.timeout.connect(self._metro_click)
        self._metro_beat = 0
        if not self.engine.available:
            self._set_title("(no audio device: sudo apt install libportaudio2)")

    def _preload_ai(self):
        ok = ai_match.load()
        if ok:
            try:
                ai_match.instrument_refs()      # prebuild so the first extraction is instant
            except Exception:
                pass
        self.ai_loaded.emit(bool(ok))      # thread-safe: queued to the main thread

    def _on_ai_loaded(self, ok):
        self._ai_ready = ok
        self._set_title()

    def _ai_tag(self):
        if not ai_match.available():
            return "AI off (DSP matching)"
        return "AI matching ✓" if getattr(self, "_ai_ready", False) else "AI loading…"

    def _set_title(self, note: str = ""):
        """Always show the version + AI status so you know which build/mode is live."""
        base = f"Beat Studio · v{__version__}  ·  {self._ai_tag()}"
        self.setWindowTitle(f"{base}  —  {note}" if note else base)

    def showEvent(self, ev):
        super().showEvent(ev)
        self.minimap.reposition(); self.minimap.raise_()
        self.zoombar.reposition(); self.zoombar.raise_()

    # ---- menu + persistence ----
    def _build_menu(self):
        m = self.menuBar().addMenu("File")
        for label, key, fn in (("New (clear grid)", "Ctrl+N", self._new_project),
                               ("Clear all beats", "Ctrl+Backspace", self._clear_beats),
                               (None, None, None),
                               ("Open Project…", "Ctrl+O", self._open_project),
                               ("Save Project…", "Ctrl+S", self._save_project),
                               ("Export MIDI…", "Ctrl+E", self._export_midi),
                               ("Grooves (phone sync)…", "Ctrl+G", self._open_grooves)):
            if label is None:
                m.addSeparator(); continue
            a = QAction(label, self); a.setShortcut(QKeySequence(key)); a.triggered.connect(fn)
            m.addAction(a)
        ai = self.menuBar().addMenu("AI")
        a = QAction("✨ Arrange into a full track", self)
        a.setShortcut(QKeySequence("Ctrl+R")); a.triggered.connect(self._arrange_with_ai)
        ai.addAction(a)
        ai.addSeparator()
        s = QAction("AI Server Settings…", self); s.triggered.connect(self._open_ai_settings)
        ai.addAction(s)
        self.menuBar().setStyleSheet("QMenuBar{background:#0d0d12;color:#c0c0cc;}"
                                     "QMenuBar::item:selected{background:#1e1e28;}"
                                     "QMenu{background:#13131b;color:#d8d8e0;border:1px solid #2a2a36;}"
                                     "QMenu::item:selected{background:#2a2a36;}")

    def _open_ai_settings(self):
        dlg = AISettingsDialog(self.cfg, self)
        if dlg.exec() == AISettingsDialog.Accepted:
            self.cfg = appconfig.load()
            self._set_title("AI server saved")

    def _arrange_with_ai(self):
        """Send the current groove to the home-server model → get back a full arrangement.
        Runs off the UI thread; the result replaces the project (undoable)."""
        if self._arranging:
            return
        if not appconfig.ai_configured(self.cfg):
            self._open_ai_settings()
            if not appconfig.ai_configured(self.cfg):
                return
        if not self.project.events:
            self._set_title("nothing to arrange — record or add beats first")
            return
        self._arranging = True
        self._set_title("✨ arranging with AI… (asking your server)")
        snapshot = persistence.to_dict(self.project)

        def work():
            try:
                proj = arranger.arrange(self._project_from_dict(snapshot), self.cfg)
                self.arrange_done.emit(proj, "")
            except Exception as e:
                self.arrange_done.emit(None, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _project_from_dict(self, d):
        return persistence.from_dict(d)

    def _on_arrange_done(self, proj, err):
        self._arranging = False
        if proj is None:
            self._set_title(f"AI arrange failed: {err[:80]}")
            return
        self._set_project(proj)              # swaps project on every sub-widget (like undo/open)
        self._commit()                       # Ctrl+Z restores the pre-arrange groove
        self._rerender_if_playing()
        self._set_title("✨ arranged — tweak away")

    def _new_project(self):
        self._orig_rec = None; self._lane_audio = {}
        self._load_fresh(empty_project())

    def _clear_beats(self):
        self.project.events = []
        self.timeline.selected = set()
        self.timeline.set_project(self.project)
        self.headers.update(); self.toolbar.refresh_info(); self._commit(); self._rerender_if_playing()

    def _set_project(self, p):
        self._stop()
        self.project = p
        self._spb = 60.0 / max(1, p.bpm)
        self.timeline.set_project(p)
        self.headers.project = p; self.settings.project = p; self.toolbar.project = p
        self.toolbar.bpm.blockSignals(True); self.toolbar.bpm.setValue(p.bpm); self.toolbar.bpm.blockSignals(False)
        self.settings.hide()
        self.headers.update(); self.ruler.update(); self.toolbar.refresh_info()

    def _save_project(self):
        os.makedirs(_PROJECTS_DIR, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", os.path.join(_PROJECTS_DIR, "groove.json"),
                                              "Beat project (*.json)")
        if path:
            persistence.save_project(self.project, path)

    def _load_fresh(self, p):
        self._set_project(p)
        self._committed = persistence.to_dict(self.project)
        self._undo_stack.clear(); self._redo_stack.clear()

    def _open_project(self):
        os.makedirs(_PROJECTS_DIR, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", _PROJECTS_DIR, "Beat project (*.json)")
        if path:
            self._load_fresh(persistence.load_project(path))

    def _export_midi(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export MIDI", os.path.join(_HERE, "groove.mid"),
                                              "MIDI file (*.mid)")
        if path:
            persistence.export_midi(self.project, path)

    def _open_grooves(self):
        start = _SYNC_DIR if os.path.isdir(_SYNC_DIR) else _HERE
        path, _ = QFileDialog.getOpenFileName(self, "Open a synced groove", start, "Groove (*.json)")
        if path:
            self._load_fresh(persistence.load_project(path))

    # ---- header buttons ----
    def _on_header_action(self, lane_id: str, act: str):
        lane = next((l for l in self.project.lanes if l.id == lane_id), None)
        if not lane:
            return
        if act == "mute":
            lane.muted = not lane.muted
            self._rerender_if_playing()
        elif act == "solo":
            lane.solo = not lane.solo
            self._rerender_if_playing()
        elif act == "gear":
            self.settings.open_for(lane)
        elif act == "rec":
            self._toggle_record(lane_id)
        elif act == "extract":
            lane.play_original = False; self._rerender_if_playing()
        elif act == "original":
            lane.play_original = True; self._rerender_if_playing()
        self.headers.update(); self.timeline.viewport().update()

    # ---- recording ----
    def _stop_any_record(self):
        if self._rec_lane == "__master__":
            self._stop_master_record()
        else:
            self._stop_record()

    def _toggle_record(self, lane_id: str):
        if self.recorder.recording:
            self._stop_any_record()
        else:
            self._start_record(lane_id)

    def _start_record(self, lane_id: str):
        if not self.recorder.available:
            self._set_title("no mic/audio (sudo apt install libportaudio2)")
            return
        self._stop()
        self._rec_lane = lane_id
        if not self.recorder.start():
            self._rec_lane = None
            return
        self.settings.set_recording(True)
        lane = next((l for l in self.project.lanes if l.id == lane_id), None)
        self.headers.recording_lane = lane_id
        self._set_title(f"● RECORDING “{lane.name if lane else ''}”  (click the red ● again to stop)")
        self.headers.update()
        self.timeline.live_markers = []
        self.timeline.horizontalScrollBar().setValue(int(self.timeline.x_of_beat(self.project.start_at) - 40))
        self._timer.start()
        self._start_beat_clock()

    def _stop_record(self):
        self._metro_timer.stop(); self._timer.stop()
        self.timeline.live_markers = []; self.timeline.rec_wave = None; self.timeline.set_playhead(None)
        self.toolbar.set_rec_level(None, None)
        self.headers.recording_lane = None
        self._set_title()
        buf = self.recorder.stop()
        lane_id, self._rec_lane = self._rec_lane, None
        self.settings.set_recording(False)
        if lane_id is None:
            return
        self._lane_audio[lane_id] = buf
        ons = onsets_from(buf, SR, gate_lin(10))
        spb, sa = self._spb, self.project.start_at
        new = [Event(lane_id=lane_id, beat=self.project.snap(sa + o["t"] / spb),
                     vel=max(0.4, min(1.0, o["amp"])), length=o["dur"] / spb) for o in ons]
        self.project.events = [e for e in self.project.events if e.lane_id != lane_id] + new
        self.timeline._refresh_scene_rect(); self.timeline.viewport().update()
        self.headers.update(); self.toolbar.refresh_info(); self._commit()
        if not new:
            self._set_title("no beats detected (record a bit louder, or check the mic)")

    def _start_beat_clock(self):
        """Beat clock during recording: always blinks the LED; clicks only if the metronome
        is on. (Fixes 'metronome does nothing on record' — now there's always a visual beat.)"""
        self._metro_beat = 0
        self._metro_click()
        self._metro_timer.start(int(self._spb * 1000))

    def _preview_category(self, cat_id):
        """Play the built-in instrument for a questionnaire category so it can be compared."""
        from .usermodel import CAT_BY_ID
        from . import synth
        c = CAT_BY_ID.get(cat_id)
        if not c:
            return
        _id, _lbl, kind, sound, _po = c
        if kind == "drum":
            v = synth.drum(sound, 0.9)
        elif kind == "synth":
            v = synth.synth(sound, synth.midi_to_hz(60), 0.4, 0.9)
        else:
            return
        self.engine.one_shot(v)

    def _metro_click(self):
        accent = (self._metro_beat % 4 == 0)
        self.toolbar.pulse_beat(accent)               # visual LED every beat
        if self.project.metronome:
            self.engine.one_shot(synth_click(accent=accent))
        self._metro_beat += 1

    # ---- master record -> auto-split ----
    def _toggle_master_record(self):
        if self.recorder.recording:
            self._stop_any_record()
        else:
            if not self.recorder.available:
                self._set_title("no mic/audio (sudo apt install libportaudio2)")
                return
            self._stop()
            self._rec_lane = "__master__"
            if not self.recorder.start():
                self._rec_lane = None
                return
            self.toolbar.set_master_recording(True)
            self.timeline.live_markers = []
            self._timer.start()
            self._start_beat_clock()

    def _stop_master_record(self):
        self._metro_timer.stop(); self._timer.stop()
        self.timeline.live_markers = []; self.timeline.rec_wave = None; self.timeline.set_playhead(None)
        self.toolbar.set_rec_level(None, None)
        buf = self.recorder.stop()
        self._rec_lane = None
        self.toolbar.set_master_recording(False)
        self._set_title("finding your sounds + tempo…"); self.repaint()
        bpm, clusters, hp = analyze_clusters(buf, SR, self.project.start_at, self.usermodel)
        self._orig_rec = hp                # high-passed take (used for 'keep my sound')
        self._set_title()
        if not clusters:
            self._set_title("no sounds detected (louder / raise sensitivity)")
            return
        # Questionnaire: you tell me what each detected sound is → I build it + learn your kit.
        dlg = ReviewDialog(bpm, clusters, self.engine.one_shot, self._preview_category, self)
        if dlg.exec() != ReviewDialog.Accepted:
            return
        lanes, events = build_from_review(clusters, dlg.decisions(), self.usermodel)
        if not lanes:
            return
        if bpm:
            self.project.bpm = bpm; self._spb = 60.0 / bpm
            self.toolbar.bpm.blockSignals(True); self.toolbar.bpm.setValue(bpm); self.toolbar.bpm.blockSignals(False)
        auto_ids = {l.id for l in self.project.lanes if l.auto}
        self.project.lanes = [l for l in self.project.lanes if not l.auto] + lanes
        self.project.events = [e for e in self.project.events if e.lane_id not in auto_ids] + events
        self.timeline.set_project(self.project)
        self.headers.update(); self.toolbar.refresh_info(); self._rerender_if_playing(); self._commit()

    def _rerender_if_playing(self):
        if self.engine.playing:
            buf, self._spb = render_project(self.project, self._samples, orig=self._orig_rec)
            self.engine.set_buffer(buf)

    def _open_my_sounds(self):
        dlg = SoundsDialog(self.library, self.engine.one_shot, self)
        dlg.exec()
        self._samples = self.library.samples_dict()
        self.settings.set_my_sounds(self.library.sounds)
        self.timeline.viewport().update()
        self._rerender_if_playing()

    def _on_settings_changed(self):
        self.headers.update(); self.timeline.viewport().update(); self.toolbar.refresh_info()
        self._rerender_if_playing()

    def _delete_track(self, lane_id: str):
        self.project.lanes = [l for l in self.project.lanes if l.id != lane_id]
        self.project.events = [e for e in self.project.events if e.lane_id != lane_id]
        self.settings.hide()
        self.timeline.set_project(self.project)
        self.headers.update(); self.toolbar.refresh_info(); self._rerender_if_playing(); self._commit()

    def _test_instrument(self, lane_id: str):
        lane = next((l for l in self.project.lanes if l.id == lane_id), None)
        if not lane:
            return
        li = self.project.lane_index(lane_id)
        e = Event(lane_id=lane_id, beat=0, vel=0.9, pitch=(60 if lane.kind == "synth" else None))
        v = _voice_for(lane, e, self._spb, li, self._samples)
        if v is not None:
            self.engine.one_shot(v)

    def _add_track(self):
        self.project.lanes.append(Lane(kind="drum", sound="kick", name="Kick"))
        self.timeline.set_project(self.project)
        self.headers.update(); self.toolbar.refresh_info(); self._commit()

    def _on_edit(self):
        """A beat was added/moved/deleted on the grid."""
        self.toolbar.refresh_info()
        self._rerender_if_playing()

    # ---- undo / redo ----
    def _refresh_undo_buttons(self):
        self.toolbar.set_undo_state(bool(self._undo_stack), bool(self._redo_stack))

    def _commit(self):
        snap = persistence.to_dict(self.project)
        if snap == self._committed:
            return
        self._undo_stack.append(self._committed)
        self._undo_stack = self._undo_stack[-80:]
        self._redo_stack.clear()
        self._committed = snap
        self._refresh_undo_buttons()

    def _undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(self._committed)
        self._committed = self._undo_stack.pop()
        self._set_project(persistence.from_dict(self._committed))
        self._refresh_undo_buttons()

    def _redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(self._committed)
        self._committed = self._redo_stack.pop()
        self._set_project(persistence.from_dict(self._committed))
        self._refresh_undo_buttons()

    def _clear_beats_confirm(self):
        from PySide6.QtWidgets import QMessageBox
        if not self.project.events:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Clear all beats")
        box.setText(f"Remove all {len(self.project.events)} beats from every track?")
        box.setInformativeText("Your tracks stay; only the beats are cleared. You can undo this.")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        box.setStyleSheet("QMessageBox{background:#13131b;} QLabel{color:#d8d8e0;}")
        if box.exec() == QMessageBox.Yes:
            self._clear_beats()

    # ---- per-beat EQ popover ----
    def _selected_events(self):
        return [e for e in self.project.events if e.id in self.timeline.selected]

    def _open_beat_eq(self, global_pos):
        events = self._selected_events()
        if not events:
            return
        self.beat_eq.set_targets(events)
        self.beat_eq.move(global_pos)
        self.beat_eq.show()

    def _on_beat_eq_changed(self):
        self.timeline.viewport().update()
        self._rerender_if_playing()

    def _preview_beat(self):
        events = self.beat_eq.targets
        if not events:
            return
        e = events[0]
        li = self.project.lane_index(e.lane_id)
        lane = self.project.lanes[li]
        v = _voice_for(lane, e, self._spb, li, self._samples)
        if v is not None:
            self.engine.one_shot(v)

    def _toggle_metro(self):
        self.project.metronome = not self.project.metronome
        self.toolbar.set_metro_active(self.project.metronome)
        self._rerender_if_playing()

    def _set_bpm(self, bpm: int):
        self.project.bpm = int(bpm)
        self._spb = 60.0 / max(1, self.project.bpm)
        self.toolbar.refresh_info()
        self._rerender_if_playing()

    def _on_loop_changed(self):
        # restart playback with the new loop so it takes effect immediately
        if self.engine.playing:
            self._play_from(self.project.loop_start if self.project.loop_on else self.project.start_at)

    # ---- transport ----
    def _toggle_play(self):
        if self.engine.playing:
            self.engine.stop(); self._timer.stop()
            return
        self._play_from(self.project.start_at)

    def _play_from(self, start_beat: float):
        buf, self._spb = render_project(self.project, self._samples, orig=self._orig_rec)
        self.engine.set_buffer(buf)
        start_frame = int(start_beat * self._spb * SR)
        loop = self.project.loop_on and self.project.loop_end and self.project.loop_start is not None
        la = int((self.project.loop_start or 0) * self._spb * SR) if loop else 0
        lb = int((self.project.loop_end or 0) * self._spb * SR) if loop else 0
        self.engine.play(start_frame, loop, la, lb)
        self._timer.start()

    def _stop(self):
        self.engine.stop(); self._timer.stop()
        self.timeline.set_playhead(None)

    def _tick(self):
        if self.recorder.recording:
            beat = self.project.start_at + (self.recorder.frames / SR) / self._spb
            self.timeline.set_playhead(beat)
            # live waveform: on the recording lane, or full-height (li=-1) for master
            li = -1 if self._rec_lane == "__master__" else self.project.lane_index(self._rec_lane)
            self.timeline.rec_wave = (li, self.project.start_at, beat, list(self.recorder.live_env))
            self.timeline.rec_clip = self.recorder.peak > 0.92
            if li >= 0:
                self.timeline.live_markers = [(li, self.project.start_at + t / self._spb)
                                              for t in list(self.recorder.live_onsets)]
            self.toolbar.set_rec_level(self.recorder.level, self.recorder.peak)
            self.timeline.viewport().update()
            x = self.timeline.x_of_beat(beat)
            sb = self.timeline.horizontalScrollBar(); vw = self.timeline.viewport().width()
            if x - sb.value() > vw * 0.75:
                sb.setValue(int(x - vw * 0.5))
            return
        pos = self.engine.position_frames()
        beat = pos / SR / self._spb
        self.timeline.set_playhead(beat)
        if not self.engine.playing:
            self._timer.stop()
            return
        # keep the playhead in view
        x = self.timeline.x_of_beat(beat)
        sb = self.timeline.horizontalScrollBar()
        vw = self.timeline.viewport().width()
        if x - sb.value() > vw * 0.75 or x - sb.value() < 0:
            sb.setValue(int(x - vw * 0.5))
