"""THE 60-90 SECOND CINEMATIC TEST (Master Prompt V1.0, part 13) - must look right BEFORE any 20-minute video.

    python animation_test.py                 -> work/anim_test/: animation_test.mp4 (16:9, 1280x720, 24 fps),
                                                animation_test_9x16.mp4 (a 12-second vertical check),
                                                animation_plan.json, animation_report.json
    python animation_test.py 1920 1080 30    -> 1080p 30 fps

Story: two men sit facing each other by a village pond at night, a lantern between them, and talk. Leaves move in
the wind, the moon shimmers on the rippling water, mist drifts. A sound - one of them turns and looks behind. A dark
figure walks slowly along the far bank and disappears behind a tree. They talk once more; the old man stands up,
turns and walks away along the bank - the camera follows him.
Voices: real Gemini recordings already in assets/voice_samples (an old man, a forty-year-old man). Ambience
(wind, crickets, water, a plop, heartbeat, footsteps) is synthesised here. Nothing paid, nothing downloaded.
"""
import json
import os
import resource
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import animation_quality_check as qc  # noqa: E402
import animation_renderer  # noqa: E402
import environment_animation  # noqa: E402
import scene_planner  # noqa: E402

OUT = os.path.join(HERE, "work", "anim_test")
VS = os.path.join(HERE, "assets", "voice_samples")
SR = 44100
CLIPS = {   # (file, from, to) - cut at real pauses, so no word is cut in half
    "c1": ("s_1111_093554_4.ogg", 1.61, 10.06),     # old man (Haren)
    "c2": ("s_1112_032409_14.ogg", 0.0, 9.04),      # forty-year-old man (Bishu)
    "c3": ("s_1111_093617_5.ogg", 4.16, 8.67),      # Haren
    "c4": ("s_1112_032431_15.ogg", 3.16, 8.06),     # Bishu, frightened
    "c5": ("s_1111_093631_6.ogg", 0.0, 4.12),       # Haren
}


def cut(name):
    f, a, b = CLIPS[name]
    out = os.path.join(OUT, f"{name}.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(a), "-t", str(b - a), "-i", os.path.join(VS, f),
                    "-ac", "1", "-ar", str(SR), "-af", f"afade=t=in:d=0.05,afade=t=out:st={b - a - 0.12:.2f}:d=0.12", out], check=True)
    return out, b - a


def ambience(plan, n):
    """wind that follows the animated wind, crickets, water lapping, the plop, a heartbeat, footsteps on grass"""
    rng = np.random.default_rng(3)
    t = np.arange(n) / SR
    white = rng.standard_normal(n).astype("float32")
    brown = np.cumsum(white) / 400.0
    brown -= np.convolve(brown, np.ones(4001) / 4001, mode="same")
    wind = np.array([environment_animation.wind_at(x) for x in t[::441]])
    wind = np.interp(t, t[::441], wind)
    out = brown * 0.10 * (0.4 + wind)
    for k in range(3):                                     # crickets: short bright chirps in patterns
        f0 = 4300 + 350 * k
        chirp = (np.sin(2 * np.pi * f0 * t) * (np.sin(2 * np.pi * (18 + 3 * k) * t) > 0.6)
                 * (np.sin(2 * np.pi * (0.45 + 0.1 * k) * t + k) > 0.2))
        out += chirp.astype("float32") * 0.012
    lap = np.convolve(white, np.ones(220) / 220, mode="same") * (0.5 + 0.5 * np.sin(2 * np.pi * 0.31 * t)) ** 3
    out += lap * 0.25
    for s in plan["sfx"]:
        i0 = int(s["t"] * SR)
        if s["type"] == "plop":
            d = np.arange(int(0.35 * SR)) / SR
            snd = np.sin(2 * np.pi * (900 * np.exp(-d * 12) + 160) * d) * np.exp(-d * 14) * 0.5
            out[i0:i0 + len(snd)] += snd[: max(0, min(len(snd), n - i0))]
        elif s["type"] == "heartbeat":
            tt = s["t"]
            while tt < s["t1"]:
                for off, amp in ((0.0, 0.55), (0.22, 0.38)):
                    j = int((tt + off) * SR)
                    d = np.arange(int(0.18 * SR)) / SR
                    snd = np.sin(2 * np.pi * 52 * d) * np.exp(-d * 22) * amp
                    out[j:j + len(snd)] += snd[: max(0, min(len(snd), n - j))]
                tt += 0.95
        elif s["type"] == "footsteps":
            tt = s["t"]
            while tt < s["t1"]:
                j = int(tt * SR)
                d = np.arange(int(0.12 * SR)) / SR
                snd = np.convolve(rng.standard_normal(len(d)), np.ones(30) / 30, mode="same") * np.exp(-d * 30) * 0.5
                out[j:j + len(snd)] += snd[: max(0, min(len(snd), n - j))]
                tt += s.get("step", 0.47)                  # one footstep per real step
    return out


def build_audio(plan, clips):
    n = int(plan["duration"] * SR) + SR
    mix = ambience(plan, n)
    for d in plan["dialogue"]:
        p, _ = clips[d["clip"]]
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                             capture_output=True, check=True).stdout
        v = np.frombuffer(raw, np.int16).astype("float32") / 32768.0
        i0 = int(d["t0"] * SR)
        mix[i0:i0 + len(v)] += v[: max(0, min(len(v), n - i0))] * 1.15
    mix = mix[: int(plan["duration"] * SR)]
    fi, fo = int(0.8 * SR), int(1.2 * SR)
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[-fo:] *= np.linspace(1, 0, fo)
    mix = mix / (np.abs(mix).max() + 1e-6) * 0.9
    path = os.path.join(OUT, "mix.wav")
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return path


def usage():
    s, c = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"cpu_seconds": round(s.ru_utime + s.ru_stime + c.ru_utime + c.ru_stime, 1),
            "peak_ram_mb": round(max(s.ru_maxrss, c.ru_maxrss) / 1024)}


def run(W=1280, H=720, fps=24, vertical=True, log=print):
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    clips = {k: cut(k) for k in CLIPS}
    plan = scene_planner.pond_test_plan(clips)
    scene_planner.save(plan, os.path.join(OUT, "animation_plan.json"))
    audio = build_audio(plan, clips)
    log(f"plan: {plan['duration']}s, {len(plan['camera'])} shots, {len(plan['dialogue'])} lines, {len(plan['actions'])} actions")
    video = os.path.join(OUT, "animation_test.mp4")
    rep, scene = animation_renderer.render(plan, clips, video, os.path.join(OUT, "chunks"), W, H, fps, audio, log=log)
    report = {"video": os.path.basename(video), **rep, "duration": plan["duration"],
              "speed_x_realtime": round(rep["render_seconds"] / plan["duration"], 2), "cpu_cores": os.cpu_count()}
    if vertical:                                           # 9:16 check: the same scene through a vertical window
        vplan = dict(plan, duration=12.0)
        vplan["camera"] = [dict(s) for s in plan["camera"] if s["t0"] < 12.0]
        vplan["camera"][-1]["t1"] = 12.0
        vrep, _ = animation_renderer.render(vplan, clips, os.path.join(OUT, "animation_test_9x16.mp4"),
                                            os.path.join(OUT, "chunks_v"), 720, 1280, fps,
                                            None, log=log)
        report["vertical_9x16"] = {"seconds": 12.0, "render_seconds": vrep["render_seconds"], "resolution": "720x1280"}
    report["quality"] = qc.check(video, plan, rep, scene)
    report.update(usage())
    report["total_seconds"] = round(time.time() - t0, 1)
    report["zero_cost"] = "কোনো paid API, paid GPU বা অনলাইন পরিষেবা ব্যবহার হয়নি (Python, NumPy, OpenCV, FFmpeg)"
    with open(os.path.join(OUT, "animation_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    log(json.dumps(report, ensure_ascii=False, indent=1))
    return report


if __name__ == "__main__":
    a = sys.argv[1:]
    run(int(a[0]) if a else 1280, int(a[1]) if len(a) > 1 else 720, int(a[2]) if len(a) > 2 else 24)
