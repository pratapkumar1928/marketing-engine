"""Original synthesized music bed (kick + bass + hats). No licences involved.

Ported from scrollsmack/store/promo-explainer/make_bgm.py; the seed varies tempo, key and groove.
ponytail: pure-stdlib synth at 22.05 kHz; swap in a provider file if a better free source shows up.
"""
import math
import random
import struct
import wave
from pathlib import Path

SR = 22050
BASSLINE = [0, 0, 3, 0, -2, -2, 0, 5]  # semitones from the root


def make_track(seconds: float, out: Path, *, seed: int) -> Path:
    rng = random.Random(seed)
    bpm = rng.choice([100, 108, 115, 120, 126])
    beat = 60.0 / bpm
    root = rng.choice([49.0, 55.0, 58.27, 61.74, 65.41])
    swing = rng.choice([0.0, 0.03])
    n = int(SR * seconds)
    buf = [0.0] * n

    def add(start, length, fn, gain):
        s0 = int(start * SR)
        for i in range(int(length * SR)):
            j = s0 + i
            if j >= n:
                break
            buf[j] += gain * fn(i / SR)

    def kick(t):
        return math.sin(2 * math.pi * (45 * t + 110 * (1 - math.exp(-30 * t)) / 30)) * math.exp(-7 * t)

    def bass(freq):
        def fn(t):
            w = 2 * math.pi * freq * t
            return (math.sin(w) + 0.4 * math.sin(2 * w) + 0.2 * math.sin(3 * w)) * math.exp(-9 * t) * min(1.0, t * 400)
        return fn

    def hat(decay):
        prev = [0.0]

        def fn(t):
            x = rng.uniform(-1, 1)
            hp, prev[0] = x - prev[0], x
            return hp * math.exp(-decay * t)
        return fn

    beats = int(seconds / beat) + 1
    for b in range(beats):
        t = b * beat
        frac = t / seconds
        if frac < 0.2:  # sparse intro under the hook
            if b % 2 == 0:
                add(t, beat, kick, 0.8)
            add(t, beat / 2, bass(root), 0.25)
            continue
        add(t, beat, kick, 0.9 if frac < 0.6 else 1.0)
        for s in range(2 if frac < 0.6 else 4):
            off = s * beat / (2 if frac < 0.6 else 4) + (swing if s % 2 else 0)
            add(t + off + (beat / 4 if frac < 0.6 else 0), 0.08, hat(70), 0.15)
        for e in range(2):
            semis = BASSLINE[(b * 2 + e) % 8]
            add(t + e * beat / 2, beat / 2, bass(root * 2 ** (semis / 12)), 0.45)

    peak = max(max(abs(x) for x in buf), 1e-9)
    fade = int(0.6 * SR)
    frames = bytearray()
    for i, x in enumerate(buf):
        v = math.tanh(1.6 * x / peak) * 0.85
        if i > n - fade:
            v *= (n - i) / fade
        frames += struct.pack("<h", int(v * 32767))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))
    return out
