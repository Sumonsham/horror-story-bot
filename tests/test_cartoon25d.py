"""Tests for Rasta 1: Pure Story-Matched 2.5D Illustrated Horror Engine."""
import os
import sys
import wave

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import cartoon25d as C25


def test_activation_rules():
    assert C25.active(lambda k: {"ANIM_MODE": "cartoon25d"}.get(k, "")) is True
    assert C25.active(lambda k: {"ANIM_MODE": "tvtoon"}.get(k, "")) is True
    assert C25.active(lambda k: {"ANIM_MODE": ""}.get(k, "")) is True
    assert C25.active(lambda k: {"ANIM_MODE": "tvtoon", "CARTOON_25D": "0"}.get(k, "")) is False
    assert C25.active(lambda k: {"ANIM_MODE": "cartoon"}.get(k, "")) is False
    assert C25.active(lambda k: {"ANIM_MODE": "character"}.get(k, "")) is False


def test_weather_and_motion_detection():
    wx = C25.detect_weather("পুরোনো শ্মশানঘাট, ঝড়বৃষ্টি ও কুয়াশা", ["heavy rain"], "scare", ["বাজ পড়ল"])
    assert wx["rain"] and wx["storm"] and wx["embers"] and wx["fog"] > 0.5
    wx2 = C25.detect_weather("গ্রামের পুকুর ঘাট, রাত", ["crickets"], "creepy", ["হারিকেন জ্বলছে"])
    assert wx2["fireflies"] and wx2["lantern"] and not wx2["rain"]
    assert C25.detect_motion("সে দৌড়ে পালাল!", "", "scared", "Bapi") == "run"
    assert C25.detect_motion("ধীরে ধীরে এগিয়ে এল", "", "normal", "Hari") == "walk"
    assert C25.detect_motion("শূন্যে ভেসে উঠল", "", "eerie", "Pishachini", ["Pishachini"]) == "ghost_float"


def test_voice_envelope_and_3layer_render(tmp_path):
    img = np.zeros((360, 640, 3), np.uint8)
    img[:, :] = (36, 26, 20)
    cv2.rectangle(img, (0, 240), (640, 360), (48, 40, 34), -1)
    cv2.circle(img, (320, 120), 34, (140, 175, 225), -1)
    cv2.rectangle(img, (275, 155), (365, 340), (60, 110, 195), -1)
    p = str(tmp_path / "s.jpg")
    cv2.imwrite(p, img)

    wav = str(tmp_path / "v.wav")
    sr = 16000
    t = np.arange(sr * 2) / sr
    sig = (np.sin(2 * np.pi * 220 * t) * ((t > 0.2) & (t < 0.9)) * 16000).astype(np.int16)
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(sig.tobytes())

    env = C25.voice_envelope(wav, 25)
    assert len(env) == 50 and env[12] > 0.5 and env[40] < 0.1

    def cutout(pic, W, H):
        a = np.zeros((H, W), np.uint8)
        cv2.circle(a, (W // 2, int(H * 0.33)), int(H * 0.10), 255, -1)
        cv2.rectangle(a, (int(W * 0.43), int(H * 0.43)), (int(W * 0.57), int(H * 0.94)), 255, -1)
        return a

    L = C25.split_25d_layers(p, 640, 360, cutout_fn=cutout)
    assert L["has_fg"]
    tex = C25._textures(640, 360)
    wx = C25.detect_weather("গ্রামের পুকুর ঘাট, রাত, বৃষ্টি", ["rain"], "scare", [])
    f0 = C25.render_frame_25d(L, 640, 360, 0, 0.0, 0.0, "parallax_lr", "scare", wx, tex, motion_verb="walk")
    f1 = C25.render_frame_25d(L, 640, 360, 10, 0.4, 0.8, "parallax_lr", "scare", wx, tex, motion_verb="walk", speaking=True, mouth=0.8)
    assert f0.shape == (360, 640, 3) and f1.shape == (360, 640, 3)
    assert float(np.abs(f1.astype(int) - f0.astype(int)).mean()) > 3.0


def test_main_wires_rasta1_cleanly():
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    c25_src = open(os.path.join(ROOT, "cartoon25d.py"), encoding="utf-8").read()
    assert "Built-in stylized cartoon face animation" not in c25_src
    for sym in (
        "def cartoon25d_on():",
        "def purify_spoken_language(",
        "def character_dialect_pass(",
        "def production_blueprint_with_writer_loop(",
        "Pure Story-Matched 2.5D Illustrated Horror active",
        "Key story objects visible:",
        "prevented mid-line cut",
    ):
        assert sym in src, f"Missing {sym} in main.py"
