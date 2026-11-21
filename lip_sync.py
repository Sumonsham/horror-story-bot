"""LIP SYNC from the real voice (no text-to-speech timing guesses, no paid service).

For every video frame of a spoken line: how far the mouth is open = the loudness of that moment; which shape =
the sound's colour (spectral centroid): dark/round sounds -> "O", middle -> "A", bright/flat sounds -> "E";
a short closure between syllables -> "M"; silence -> "rest". So the mouth opens and closes exactly with the
syllables that are heard. It is not phoneme-perfect (that would need a speech recogniser), and it is reported so.
"""
import subprocess

import numpy as np


def load(path, sr=16000):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def visemes(path, fps, sr=16000):
    """[(open 0..1, shape)] per frame for one voice clip"""
    x = load(path, sr)
    hop = int(round(sr / fps))
    n = max(1, int(np.ceil(len(x) / hop)))
    x = np.pad(x, (0, n * hop + hop - len(x)))
    win = np.hanning(hop * 2)
    freqs = np.fft.rfftfreq(hop * 2, 1.0 / sr)
    rms, cen = np.zeros(n), np.zeros(n)
    for i in range(n):
        seg = x[i * hop:i * hop + hop * 2]
        if len(seg) < hop * 2:
            seg = np.pad(seg, (0, hop * 2 - len(seg)))
        rms[i] = np.sqrt((seg ** 2).mean() + 1e-12)
        sp = np.abs(np.fft.rfft(seg * win))
        band = (freqs > 150) & (freqs < 4000)
        cen[i] = (sp[band] * freqs[band]).sum() / (sp[band].sum() + 1e-9)
    top = np.percentile(rms, 95) or 1.0
    op = np.clip((rms / top - 0.12) / 0.75, 0, 1)
    op = np.convolve(op, [0.25, 0.5, 0.25], mode="same")
    out = []
    for i in range(n):
        if op[i] < 0.08:
            shape = "M" if (i > 0 and op[i - 1] > 0.3) else "rest"
        elif cen[i] < 950:
            shape = "O"
        elif cen[i] < 1700:
            shape = "A"
        else:
            shape = "E"
        out.append((float(op[i]), shape))
    return out


def envelope(path, fps):
    return np.array([o for o, _ in visemes(path, fps)])
