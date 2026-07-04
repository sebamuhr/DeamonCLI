"""Project save/load (JSON), MIDI export (mido), and phone-sync groove loading.

from_dict is tolerant of the WEB app's groove format (type/laneId/len) so grooves the
phone records and syncs via server.py load straight into the desktop app.
"""
from __future__ import annotations
import json
import os
import mido

from .model import Project, Lane, Event

# General-MIDI percussion notes (channel 10) for our drum voices
DRUM_NOTE = {"kick": 36, "808": 35, "snare": 38, "rim": 37, "clap": 39,
             "tomL": 45, "tomM": 47, "tomH": 50, "hat": 42, "openhat": 46,
             "cowbell": 56, "shaker": 70, "congaH": 62, "congaL": 63, "cymbal": 49}


def to_dict(p: Project) -> dict:
    return {
        "bpm": p.bpm, "grid": p.grid, "start_at": p.start_at, "metronome": p.metronome,
        "loop_on": p.loop_on, "loop_start": p.loop_start, "loop_end": p.loop_end,
        "lanes": [{"id": l.id, "kind": l.kind, "sound": l.sound, "name": l.name,
                   "muted": l.muted, "solo": l.solo, "auto": l.auto, "eq": l.eq,
                   "has_original": l.has_original, "play_original": l.play_original} for l in p.lanes],
        "events": [{"id": e.id, "lane_id": e.lane_id, "beat": e.beat, "vel": e.vel,
                    "length": e.length, "pitch": e.pitch, "tune": e.tune, "eq": e.eq,
                    "src_t": e.src_t, "src_dur": e.src_dur} for e in p.events],
    }


def from_dict(d: dict) -> Project:
    d = d.get("state", d)          # web grooves wrap data under "state"
    p = Project(bpm=int(d.get("bpm", 90)), grid=int(d.get("grid", 4)),
                start_at=d.get("start_at", d.get("startAt", 0)) or 0,
                metronome=bool(d.get("metronome", False)),
                loop_on=bool(d.get("loop_on", d.get("loopOn", False))),
                loop_start=d.get("loop_start", d.get("loopStart")),
                loop_end=d.get("loop_end", d.get("loopEnd")))
    for l in d.get("lanes", []):
        p.lanes.append(Lane(id=l["id"], kind=l.get("kind") or l.get("type", "drum"),
                            sound=l.get("sound", "kick"), name=l.get("name") or l.get("soundName", "Sound"),
                            muted=bool(l.get("muted", False)), solo=bool(l.get("solo", False)),
                            auto=bool(l.get("auto", False)),
                            has_original=bool(l.get("has_original", False)),
                            play_original=bool(l.get("play_original", False)),
                            eq=l.get("eq") or {"low": 0, "mid": 0, "high": 0}))
    for e in d.get("events", []):
        p.events.append(Event(id=e.get("id"), lane_id=e.get("lane_id") or e.get("laneId"),
                             beat=e.get("beat", 0), vel=e.get("vel", 0.85),
                             length=e.get("length", e.get("len", 0)) or 0,
                             pitch=e.get("pitch"), tune=e.get("tune", 0),
                             eq=e.get("eq") or {"low": 0, "mid": 0, "high": 0},
                             src_t=e.get("src_t", e.get("srcT")), src_dur=e.get("src_dur", e.get("srcDur"))))
    return p


def save_project(p: Project, path: str):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(to_dict(p), fh, indent=1)


def load_project(path: str) -> Project:
    with open(path, "r", encoding="utf-8") as fh:
        return from_dict(json.load(fh))


def export_midi(p: Project, path: str, tpb: int = 480):
    mid = mido.MidiFile(ticks_per_beat=tpb)
    track = mido.MidiTrack(); mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(p.bpm)))
    idx = {l.id: i for i, l in enumerate(p.lanes)}
    msgs = []
    for e in p.events:
        li = idx.get(e.lane_id)
        if li is None:
            continue
        lane = p.lanes[li]
        if lane.kind == "drum":
            ch, note, length = 9, DRUM_NOTE.get(lane.sound, 36), tpb // 8
        else:
            ch = li % 8
            note = (e.pitch if e.pitch is not None else 60) + (e.tune or 0)
            length = max(1, int((e.length or 0.25) * tpb))
        note = max(0, min(127, int(note)))
        start = int(p.snap(e.beat) * tpb)
        vel = max(1, min(127, int((e.vel or 0.8) * 127)))
        msgs.append((start, 1, mido.Message("note_on", note=note, velocity=vel, channel=ch)))
        msgs.append((start + length, 0, mido.Message("note_off", note=note, velocity=0, channel=ch)))
    msgs.sort(key=lambda m: (m[0], m[1]))
    last = 0
    for tick, _, msg in msgs:
        msg.time = tick - last
        last = tick
        track.append(msg)
    mid.save(path)


def list_synced(sync_dir: str):
    if not os.path.isdir(sync_dir):
        return []
    out = []
    for f in sorted(os.listdir(sync_dir)):
        if f.endswith(".json"):
            path = os.path.join(sync_dir, f)
            try:
                with open(path, encoding="utf-8") as fh:
                    d = json.load(fh)
                out.append((d.get("id", f[:-5]), d.get("name", f[:-5]), path))
            except Exception:
                pass
    return out
