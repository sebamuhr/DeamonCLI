"""Render a Project to a mono float32 buffer by summing scheduled voices.

We pre-render the whole timeline (glitch-free), then stream it. Live edits during
playback just re-render. Mirrors the web app's offline scheduling.
"""
from __future__ import annotations
import numpy as np
from . import synth
from .synth import SR

# When a sample-lane has no loaded sample yet, fall back to a distinct percussion
# voice per track so the groove is audible.
_FALLBACK = ["kick", "snare", "hat", "clap", "tomM", "rim", "cowbell", "shaker", "congaH", "openhat"]


def _voice_for(lane, e, spb, li, samples):
    kind = lane.kind
    tune = e.tune or 0
    if kind == "drum":
        x = synth.drum(lane.sound, e.vel)
    elif kind == "synth":
        freq = synth.midi_to_hz((e.pitch if e.pitch is not None else 60) + tune)
        dur = max(0.15, (e.length or 0) * spb) if e.length else 0.3
        x = synth.synth(lane.sound or "square", freq, dur, e.vel)
    elif kind == "sample":
        samp = (samples or {}).get(lane.sound)
        if samp is not None:
            dur = (e.length or 0) * spb
            x = synth.sample_voice(samp["buf"], samp.get("base", 60),
                                   (e.pitch if e.pitch is not None else 60) + tune, dur, e.vel)
        else:
            x = synth.drum(_FALLBACK[li % len(_FALLBACK)], e.vel)
    else:
        return None
    eq = e.eq or {}
    return synth.apply_eq(x, eq.get("low", 0), eq.get("mid", 0), eq.get("high", 0))


def _orig_slice(orig, e):
    a = max(0, int((e.src_t or 0) * SR))
    b = min(len(orig), a + int((e.src_dur or 0.28) * SR))
    if b <= a:
        return None
    seg = (orig[a:b] * max(0.05, min(1.4, e.vel or 0.85))).astype(np.float32)
    rel = min(len(seg), int(0.02 * SR))
    if rel > 1:
        seg = seg.copy(); seg[-rel:] *= np.linspace(1, 0, rel, dtype=np.float32)
    return seg


def render_project(project, samples=None, tail=0.6, orig=None):
    """Return (buffer float32 mono, seconds_per_beat). `orig` = master take for play_original."""
    spb = 60.0 / max(1, project.bpm)
    max_beat = project.max_beat()
    total = int((max_beat * spb + tail) * SR) + SR // 4
    buf = np.zeros(total + SR, np.float32)

    solos = [l for l in project.lanes if l.solo]
    pool = solos if solos else project.lanes
    active = {l.id for l in pool if not l.muted}
    lanes_by_id = {l.id: (i, l) for i, l in enumerate(project.lanes)}

    for e in project.events:
        li_lane = lanes_by_id.get(e.lane_id)
        if not li_lane:
            continue
        li, lane = li_lane
        if lane.id not in active or lane.kind == "master":
            continue
        if lane.play_original and orig is not None and e.src_t is not None:
            v = _orig_slice(orig, e)
        else:
            v = _voice_for(lane, e, spb, li, samples)
        if v is None:
            continue
        start = int(project.snap(e.beat) * spb * SR)
        if start >= len(buf):
            continue
        end = min(len(buf), start + len(v))
        buf[start:end] += v[:end - start]

    if getattr(project, "metronome", False):
        b = 0
        while b * spb * SR < len(buf):
            c = synth.click(accent=(b % 4 == 0))
            s = int(b * spb * SR); e = min(len(buf), s + len(c))
            buf[s:e] += c[:e - s]
            b += 1

    np.tanh(buf * 0.9, out=buf)        # soft clip
    buf *= 0.9
    return buf[:total].astype(np.float32), spb
