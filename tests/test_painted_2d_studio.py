"""Tests for V4 Realistic Cinematic Shot-by-Shot Painted 2.5D + Zero-Cut Single-Line Voice Pipeline."""
import os
import shutil
import sys

import cv2
import numpy as np
from scipy.io import wavfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import cartoon25d as C25
import extras as EX


def _make_painted_shot(path, w=640, h=360, bg_col=(22, 30, 48)):
    img = np.full((h, w, 3), bg_col, dtype=np.uint8)
    cv2.circle(img, (int(w * 0.2), int(h * 0.22)), 28, (205, 220, 235), -1)
    cv2.rectangle(img, (0, int(h * 0.72)), (w, h), (18, 22, 28), -1)
    cv2.circle(img, (w // 2, int(h * 0.34)), 36, (188, 152, 126), -1)
    cv2.rectangle(img, (w // 2 - 48, int(h * 0.44)), (w // 2 + 48, int(h * 0.94)), (45, 58, 90), -1)
    cv2.imwrite(path, img)


def _make_wav(path, secs=2.2, sr=44100):
    t = np.linspace(0, secs, int(sr * secs), endpoint=False)
    sig = (0.35 * np.sin(2 * np.pi * 210 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3.0 * t))).astype(np.float32)
    wavfile.write(path, sr, np.clip(sig * 32767, -32768, 32767).astype(np.int16))


def _fake_fg_mask(pic, w_, h_):
    m = np.zeros((h_, w_), dtype=np.uint8)
    cv2.circle(m, (w_ // 2, int(h_ * 0.34)), int(w_ * 0.06), 255, -1)
    cv2.rectangle(m, (w_ // 2 - int(w_ * 0.08), int(h_ * 0.42)), (w_ // 2 + int(w_ * 0.08), int(h_ * 0.95)), 255, -1)
    return m


def test_cinematic_25d_defaults_and_render(tmp_path):
    assert C25.active(lambda k: {"ANIM_MODE": ""}.get(k, "")) is True
    assert C25.active(lambda k: {"ANIM_MODE": "cartoon25d"}.get(k, "")) is True
    assert C25.active(lambda k: {"ANIM_MODE": "character"}.get(k, "")) is True
    assert C25.active(lambda k: {"ANIM_MODE": "cutout"}.get(k, "")) is False
    assert C25.active(lambda k: {"CARTOON_25D": "0"}.get(k, "")) is False

    # Unrevealed ghost character MUST NEVER float!
    assert C25.detect_motion("শম্ভুদা লণ্ঠন মুছছেন", "", "normal", "Shambhu", ["Shambhu"], revealed=False) == "idle"
    assert C25.detect_motion("ছায়াটা শূন্যে ভাসছে", "", "eerie", "Shambhu", ["Shambhu"], revealed=False) == "loom"
    assert C25.detect_motion("ছায়াটা শূন্যে ভাসছে", "", "eerie", "Shambhu", ["Shambhu"], revealed=True) == "ghost_float"

    s1 = str(tmp_path / "shot_00_00.jpg")
    s2 = str(tmp_path / "shot_00_01.jpg")
    wav = str(tmp_path / "scene_00.wav")
    _make_painted_shot(s1, bg_col=(20, 28, 45))
    _make_painted_shot(s2, bg_col=(28, 22, 38))
    _make_wav(wav, secs=2.2)

    L = C25.split_25d_layers(s1, 640, 360, cutout_fn=_fake_fg_mask)
    assert L["has_fg"] is True
    wx = C25.detect_weather("foggy Bengal railway station at night", ["rain"], "creepy", ["কে ওখানে?"])
    tex = C25._textures(640, 360)
    frame = C25.render_frame_25d(
        L, 640, 360, 5, 0.5, 0.25, "dramatic_closeup", "creepy", wx, tex,
        mouth=0.5, blink=0.2, speaking=True, emo="scared", motion_verb="idle",
    )
    assert frame.shape == (360, 640, 3) and frame.dtype == np.uint8 and frame.mean() > 5

    if shutil.which("ffmpeg"):
        mp4 = str(tmp_path / "scene_00.mp4")
        dur = C25.render_scene(
            [(s1, 0.0), (s2, 1.1)], wav, mp4, idx=0, mood="creepy",
            talk=[(0.1, 1.0, False, "scared", "কে ওখানে?"), (1.1, 2.0, False, "normal", "আমি শম্ভু।")],
            meta={"place": "foggy Bengal railway station at night", "ambience": ["rain"],
                  "ghost_names": ["Shambhu"], "speakers": ["Bapi", "Shambhu"], "revealed": [False, False]},
            W=640, H=360, FPS=12, SR=44100, cutout_fn=_fake_fg_mask,
        )
        assert dur >= 2.15 and os.path.exists(mp4) and os.path.getsize(mp4) > 5000


def test_v4_workflow_zero_cut_voice_and_cinematic_prebuild(tmp_path):
    yml = open(os.path.join(ROOT, ".github/workflows/horror-story.yml"), encoding="utf-8").read()
    assert "ANIM_MODE: ${{ vars.ANIM_MODE || 'cartoon25d' }}" in yml
    assert "assets/cinematic_shots" in yml
    assert 'cron: "0 22 * * *"' in yml
    assert "espeakng-loader" in yml and "espeak-ng" in yml
    for sec in ("CF_ACCOUNT_ID_2", "CF_API_TOKEN_2", "AGNES_API_KEY",
                "GEMINI_API_KEY_2", "GEMINI_API_KEY_4", "GEMINI_TTS_KEY_2", "GEMINI_TTS_KEY_6"):
        assert f"secrets.{sec}" in yml

    msrc = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert "1 whole line per request - ZERO slicing!" in msrc
    assert "def _build_plan_cinematic_shots(" in msrc
    assert "def _cinematic_shots_missing(" in msrc
    assert 'if (_am == "cutout" and env("PAINTED_2D") != "0"):' in msrc
    assert '_c25["revealed"] = [bool(ln.get("_revealed", False)) for ln in spoken]' in msrc
    assert "extras.slot_done(hist_now, key)" in msrc

    esrc = open(os.path.join(ROOT, "extras.py"), encoding="utf-8").read()
    assert "DAY_OUT.add((key, model))\n                    HITS[model] = 0\n                    continue" in esrc
    assert "max(0.45, plain_len / 24) <= d <= plain_len / 2.2 + 10" in esrc

    sr = 16000
    t = np.linspace(0, 3.2, int(sr * 3.2), endpoint=False)
    sig = (0.3 * np.sin(2 * np.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 2.5 * t))).astype(np.float32)
    sig[int(sr * 1.5):int(sr * 2.8)] = sig[int(sr * 0.1):int(sr * 1.4)]
    p1 = str(tmp_path / "line1.wav")
    wavfile.write(p1, sr, np.clip(sig * 32767, -32768, 32767).astype(np.int16))
    assert EX.fix_heard_twice([{"out": p1, "plain": "কুয়াশার পেটের ভেতর মিলিয়ে গেল, আর মুহূর্তের মধ্যে অন্ধকার নামল।", "voice": "Charon"}]) == 0
