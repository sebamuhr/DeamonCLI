"""Voice synthesis in numpy — ports the web app's drum/synth/sampler voices.

Every generator returns a mono float32 numpy array at sample-rate SR. These are summed
into the render buffer by render.py.
"""
from __future__ import annotations
import numpy as np
from scipy import signal

SR = 44100

DRUMS = ["kick", "snare", "hat", "openhat", "clap", "tomL", "tomM", "tomH",
         "rim", "cowbell", "808", "shaker", "congaH", "congaL", "cymbal"]
WAVES = ["sine", "saw", "square", "triangle", "pad", "pluck", "bass", "lead", "bell", "organ"]


def _t(n):
    return np.arange(n) / SR


def _env_exp(n, decay):
    """Exponential decay from 1 to ~0 over `decay` seconds."""
    return np.exp(-_t(n) / max(1e-4, decay / 4.0)).astype(np.float32)


def _noise(n):
    return (np.random.random(n).astype(np.float32) * 2 - 1)


def _hp(x, fc):
    b, a = signal.butter(2, min(0.99, fc / (SR / 2)), btype="high")
    return signal.lfilter(b, a, x).astype(np.float32)


def _lp(x, fc):
    b, a = signal.butter(2, min(0.99, fc / (SR / 2)), btype="low")
    return signal.lfilter(b, a, x).astype(np.float32)


def _bp(x, fc, q=4.0):
    bw = fc / q
    lo = max(20.0, fc - bw / 2) / (SR / 2)
    hi = min(0.99, (fc + bw / 2) / (SR / 2))
    b, a = signal.butter(2, [lo, hi], btype="band")
    return signal.lfilter(b, a, x).astype(np.float32)


def _sine_sweep(f0, f1, n, k=0.12):
    """Sine whose frequency glides f0->f1 (exp) over ~k seconds."""
    t = _t(n)
    f = f1 + (f0 - f1) * np.exp(-t / max(1e-4, k / 4))
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph).astype(np.float32)


# ---------------- drums ----------------
def drum(inst: str, vel: float = 1.0) -> np.ndarray:
    v = float(vel)
    if inst == "kick":
        n = int(SR * 0.26); return _sine_sweep(165, 45, n, 0.12) * _env_exp(n, 0.22) * v
    if inst == "808":
        n = int(SR * 0.62); return _sine_sweep(120, 38, n, 0.18) * _env_exp(n, 0.6) * v
    if inst == "snare":
        n = int(SR * 0.16)
        body = np.sin(2 * np.pi * 185 * _t(n)) * _env_exp(n, 0.1) * 0.5
        nz = _hp(_noise(n), 1300) * _env_exp(n, 0.14) * 0.8
        return ((body + nz) * v).astype(np.float32)
    if inst in ("hat", "openhat"):
        dec = 0.32 if inst == "openhat" else 0.05
        n = int(SR * (dec + 0.02))
        return (_hp(_noise(n), 6500) * _env_exp(n, dec) * (0.4 if inst == "openhat" else 0.5) * v).astype(np.float32)
    if inst == "clap":
        n = int(SR * 0.12); out = np.zeros(n, np.float32)
        for i in range(3):
            off = int(SR * 0.012 * i)
            seg = _bp(_noise(n - off), 1500) * _env_exp(n - off, 0.07) * 0.55
            out[off:] += seg
        return out * v
    if inst in ("tomL", "tomM", "tomH"):
        f = {"tomL": 150, "tomM": 210, "tomH": 285}[inst]
        n = int(SR * 0.24); return _sine_sweep(f, f * 0.5, n, 0.18) * _env_exp(n, 0.22) * 0.9 * v
    if inst in ("congaH", "congaL"):
        f = 330 if inst == "congaH" else 220
        n = int(SR * 0.2); return _sine_sweep(f, f * 0.85, n, 0.12) * _env_exp(n, 0.18) * 0.8 * v
    if inst == "rim":
        n = int(SR * 0.05); return (signal.square(2 * np.pi * 1700 * _t(n)).astype(np.float32) * _env_exp(n, 0.04) * 0.4 * v)
    if inst == "cowbell":
        n = int(SR * 0.26); s = (signal.square(2 * np.pi * 540 * _t(n)) + signal.square(2 * np.pi * 800 * _t(n)))
        return (s.astype(np.float32) * _env_exp(n, 0.25) * 0.25 * v)
    if inst == "shaker":
        n = int(SR * 0.1); return (_hp(_noise(n), 5000) * _env_exp(n, 0.09) * 0.32 * v).astype(np.float32)
    if inst == "cymbal":
        n = int(SR * 0.62); return (_hp(_noise(n), 8000) * _env_exp(n, 0.6) * 0.3 * v).astype(np.float32)
    # default -> kick
    n = int(SR * 0.26); return _sine_sweep(165, 45, n) * _env_exp(n, 0.22) * v


# ---------------- synths ----------------
def _osc(kind, freq, n):
    t = _t(n); ph = 2 * np.pi * freq * t
    if kind == "sine": return np.sin(ph).astype(np.float32)
    if kind == "square": return signal.square(ph).astype(np.float32)
    if kind == "saw" or kind == "sawtooth": return signal.sawtooth(ph).astype(np.float32)
    if kind == "triangle": return signal.sawtooth(ph, 0.5).astype(np.float32)
    return np.sin(ph).astype(np.float32)


def _adsr(n, atk, rel):
    e = np.ones(n, np.float32)
    a = max(1, int(atk * SR)); r = max(1, int(rel * SR))
    e[:a] = np.linspace(0, 1, a, dtype=np.float32)
    if r < n:
        e[n - r:] = np.linspace(1, 0, r, dtype=np.float32)
    return e


def synth(preset: str, freq: float, dur: float, vel: float = 0.8) -> np.ndarray:
    v = max(0.2, min(1.0, vel))
    n = int(SR * (dur + 0.25))
    if preset == "pad":
        s = _osc("saw", freq, n) + _osc("saw", freq * 1.005, n) + _osc("sine", freq / 2, n)
        s = _lp(s / 3, 900 + 2000 * v)
        return (s * _adsr(n, min(0.25, dur * 0.4), min(0.5, dur * 0.6 + 0.1)) * 0.3 * v).astype(np.float32)
    if preset == "pluck":
        s = _osc("triangle", freq, n) + _osc("saw", freq, n) * 0.6
        return (_lp(s, 2500) * np.exp(-_t(n) / max(1e-3, (dur + 0.12) / 4)) * 0.5 * v).astype(np.float32)
    if preset == "bass":
        s = _osc("square", freq, n) + _osc("sine", freq / 2, n)
        return (_lp(s / 2, 600 + 900 * v) * _adsr(n, 0.01, min(0.12, dur * 0.4)) * 0.5 * v).astype(np.float32)
    if preset == "lead":
        s = _osc("saw", freq, n) + _osc("square", freq * 1.003, n)
        return (_lp(s / 2, 2200 + 2600 * v) * _adsr(n, 0.015, min(0.15, dur * 0.4)) * 0.34 * v).astype(np.float32)
    if preset == "bell":
        s = (_osc("sine", freq, n) * 0.5 + _osc("sine", freq * 2.76, n) * 0.3 + _osc("sine", freq * 5.4, n) * 0.16)
        return (s * np.exp(-_t(n) / max(1e-3, max(0.45, dur + 0.35) / 4)) * 0.5 * v).astype(np.float32)
    if preset == "organ":
        s = sum(_osc("sine", freq * h, n) * g for h, g in zip((1, 2, 3, 4), (0.5, 0.25, 0.15, 0.1)))
        return (s * _adsr(n, 0.02, min(0.12, dur * 0.3)) * 0.32 * v).astype(np.float32)
    # plain waveforms
    s = _osc(preset, freq, n)
    return (s * _adsr(n, 0.012, min(0.1, dur * 0.4)) * 0.42 * v).astype(np.float32)


def midi_to_hz(m: float) -> float:
    return 440.0 * (2 ** ((m - 69) / 12.0))


def click(accent: bool = False) -> np.ndarray:
    n = int(SR * 0.045)
    f = 1600 if accent else 1000
    return (signal.square(2 * np.pi * f * _t(n)).astype(np.float32)
            * np.exp(-_t(n) / 0.006) * (0.3 if accent else 0.18))


# ---------------- sampler ----------------
def sample_voice(buf: np.ndarray, base_pitch: int, pitch: int, dur: float,
                 vel: float = 0.85, loop: bool = True) -> np.ndarray:
    """Resample `buf` for pitch (playbackRate) and loop its body to fill `dur`."""
    rate = 2 ** ((pitch - base_pitch) / 12.0)
    if rate <= 0:
        rate = 1.0
    # resample by rate via linear interpolation
    idx = np.arange(0, len(buf), rate)
    res = np.interp(idx, np.arange(len(buf)), buf).astype(np.float32)
    natural = len(res) / SR
    want = int(SR * dur) if dur and dur > 0.02 else len(res)
    if want <= len(res) or not loop:
        out = res[:want] if want < len(res) else res
    else:
        atk = int(min(0.045, natural * 0.2) * SR)
        body = res[atk:max(atk + 1, int(len(res) * 0.92))]
        reps = int(np.ceil((want - atk) / max(1, len(body))))
        out = np.concatenate([res[:atk]] + [body] * reps)[:want]
    rel = min(len(out), int(0.02 * SR))
    if rel > 1:
        out = out.copy(); out[-rel:] *= np.linspace(1, 0, rel, dtype=np.float32)
    return (out * max(0.05, min(1.4, vel))).astype(np.float32)


# ---------------- 3-band EQ (RBJ biquads) ----------------
def _biquad(kind, f0, gain_db, q=0.9):
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / SR
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2 * q)
    if kind == "lowshelf":
        b0 = A * ((A + 1) - (A - 1) * cw + 2 * np.sqrt(A) * alpha)
        b1 = 2 * A * ((A - 1) - (A + 1) * cw)
        b2 = A * ((A + 1) - (A - 1) * cw - 2 * np.sqrt(A) * alpha)
        a0 = (A + 1) + (A - 1) * cw + 2 * np.sqrt(A) * alpha
        a1 = -2 * ((A - 1) + (A + 1) * cw)
        a2 = (A + 1) + (A - 1) * cw - 2 * np.sqrt(A) * alpha
    elif kind == "highshelf":
        b0 = A * ((A + 1) + (A - 1) * cw + 2 * np.sqrt(A) * alpha)
        b1 = -2 * A * ((A - 1) + (A + 1) * cw)
        b2 = A * ((A + 1) + (A - 1) * cw - 2 * np.sqrt(A) * alpha)
        a0 = (A + 1) - (A - 1) * cw + 2 * np.sqrt(A) * alpha
        a1 = 2 * ((A - 1) - (A + 1) * cw)
        a2 = (A + 1) - (A - 1) * cw - 2 * np.sqrt(A) * alpha
    else:  # peaking
        b0 = 1 + alpha * A; b1 = -2 * cw; b2 = 1 - alpha * A
        a0 = 1 + alpha / A; a1 = -2 * cw; a2 = 1 - alpha / A
    return np.array([b0, b1, b2]) / a0, np.array([1, a1 / a0, a2 / a0])


def apply_eq(x: np.ndarray, low_db=0, mid_db=0, high_db=0) -> np.ndarray:
    if not (low_db or mid_db or high_db):
        return x
    out = x
    if low_db:
        b, a = _biquad("lowshelf", 200, low_db); out = signal.lfilter(b, a, out)
    if mid_db:
        b, a = _biquad("peaking", 1200, mid_db); out = signal.lfilter(b, a, out)
    if high_db:
        b, a = _biquad("highshelf", 4200, high_db); out = signal.lfilter(b, a, out)
    return out.astype(np.float32)
