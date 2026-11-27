"""Tests for Painted 2D Studio V3: 2 CF accounts + Agnes fallback + 3:30 AM backup + all secrets + line-cutoff guards."""
import os
import sys
import tempfile

import cv2
import numpy as np
from scipy.io import wavfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import characters as CH
import painted2d_studio as P2D
import manifest as MF
import compositor as COMP
import cartoon25d as C25
import extras as EX


def _fake_image_fn(prompt, ref_path, seed, w, h):
    img = np.full((h, w, 3), 184, dtype=np.uint8)
    if "Empty painted 2D background" in prompt:
        img[:, :] = (24, 30, 44)
        cv2.rectangle(img, (0, int(h * 0.65)), (w, h), (34, 28, 26), -1)
    elif "prop illustration" in prompt:
        cv2.rectangle(img, (int(w * 0.35), int(h * 0.25)), (int(w * 0.65), int(h * 0.78)), (155, 32, 38), -1)
    else:
        cv2.circle(img, (w // 2, int(h * 0.14)), int(w * 0.09), (210, 175, 145), -1)
        cv2.circle(img, (w // 2 - 14, int(h * 0.13)), 4, (20, 20, 20), -1)
        cv2.circle(img, (w // 2 + 14, int(h * 0.13)), 4, (20, 20, 20), -1)
        if "mouth open" in prompt or "amazement" in prompt:
            cv2.ellipse(img, (w // 2, int(h * 0.17)), (10, 8), 0, 0, 360, (60, 20, 25), -1)
        cv2.rectangle(img, (int(w * 0.34), int(h * 0.23)), (int(w * 0.66), int(h * 0.56)), (45, 70, 115), -1)
        cv2.rectangle(img, (int(w * 0.37), int(h * 0.56)), (int(w * 0.48), int(h * 0.92)), (35, 35, 45), -1)
        cv2.rectangle(img, (int(w * 0.52), int(h * 0.56)), (int(w * 0.63), int(h * 0.92)), (35, 35, 45), -1)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    assert ok
    return buf.tobytes()


def test_painted2d_scout_build_and_completeness(tmp_path):
    story = {
        "title": "রাত-তদন্ত: পেরেকে ঝোলানো শাড়ি",
        "setting": "old abandoned zamindar house interior at night",
        "characters": [
            {"name": "Bapi", "gender": "male", "age": "young", "kind": "human", "look": "young Bengali man in blue shirt"},
            {"name": "Nilkantha", "gender": "male", "age": "old", "kind": "human", "look": "old Bengali astrologer in shawl"},
        ],
        "scenes": [
            {
                "place": "dark dusty room inside old zamindar house",
                "mood": "creepy",
                "characters": ["Bapi", "Nilkantha"],
                "lines": [
                    {"speaker": "Bapi", "emotion": "scared", "text": "মামা, দেওয়ালের পেরেকে ওই রক্তমাখা শাড়িটা ঝুলছে কেন?"},
                    {"speaker": "Nilkantha", "emotion": "normal", "text": "সাবধান বাপি, হারিকেনটা উঁচু করে ধর।"},
                ],
            }
        ],
    }
    assets_dir = str(tmp_path / "assets")
    cache_dir = str(tmp_path / "cache")

    # Before build: incomplete
    chk0 = P2D.story_assets_missing(story, assets_dir, cache_dir, slot_key="2026-11-28@20", series_names=["bapi", "nilkantha"])
    assert chk0["complete"] is False
    assert len(chk0["missing_chars"]) == 2
    assert len(chk0["missing_bgs"]) == 1
    assert len(chk0["missing_props"]) >= 2

    records, by_name, bgs, scene_props, stats = P2D.build_story_assets(
        story, assets_dir, cache_dir, image_fn=_fake_image_fn, slot_key="2026-11-28@20", series_names=["bapi", "nilkantha"]
    )
    assert "bapi" in records and records["bapi"]["mode"] == "photo"
    assert "shock" in records["bapi"]["expr"] and "fear" in records["bapi"]["expr"]

    # After build: 100% complete so 3:30 AM backup skips cleanly!
    chk1 = P2D.story_assets_missing(story, assets_dir, str(tmp_path / "cache2"), slot_key="2026-11-28@20", series_names=["bapi", "nilkantha"])
    assert chk1["complete"] is True, chk1

    beats = [(0.5, 3.0, "Bapi", "scared", "মামা, শাড়িটা দেখো!"), (3.3, 6.0, "Nilkantha", "normal", "সাবধান বাপি।")]
    m = MF.build_scene(0, story["scenes"][0], beats, 6.537, by_name, bgs[0], "creepy", props=scene_props[0])
    assert m["duration"] == 6.537 and len(m["characters"]) == 2 and len(m["props"]) >= 2


def test_v3_secrets_agnes_330am_and_safety_prompts(tmp_path):
    # Softened fear/shock prompts avoid Cloudflare Error 3030 triggers
    for bad in ("terrified", "screaming", "terror", "dread"):
        assert bad not in CH.EXPR_TEXT["fear"].lower()
        assert bad not in CH.EXPR_TEXT["shock"].lower()

    yml = open(os.path.join(ROOT, ".github/workflows/horror-story.yml"), encoding="utf-8").read()
    assert "ANIM_MODE: ${{ vars.ANIM_MODE || 'character' }}" in yml
    assert 'cron: "0 22 * * *"' in yml
    assert "(github.event.schedule == '0 22 * * *' && 'assets')" in yml
    assert "github.event.schedule != '0 22 * * *'" in yml
    for sec in ("CF_ACCOUNT_ID_2", "CF_API_TOKEN_2", "AGNES_API_KEY",
                "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4",
                "GEMINI_TTS_KEY_2", "GEMINI_TTS_KEY_3", "GEMINI_TTS_KEY_4",
                "GEMINI_TTS_KEY_5", "GEMINI_TTS_KEY_6"):
        assert f"secrets.{sec}" in yml, f"missing secret {sec} in workflow"

    msrc = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert 'for suf in ("", "_2"):' in msrc
    assert "if CF_QUOTA_OUT and not extras.agnes_ok():" in msrc
    assert "extras.agnes_image(prompt, crop_16x9=(w > h))" in msrc
    assert "def _gem_text_keys():" in msrc
    assert "P2D.story_assets_missing(" in msrc

    # Verify extras.tts_keys() supports 1..6 keys AND still blocks paid GEMINI_API_KEY when ZERO_COST_MODE is on
    old_env = {k: os.environ.get(k) for k in ("GEMINI_TTS_KEY", "GEMINI_TTS_KEY_2", "GEMINI_TTS_KEY_6", "GEMINI_API_KEY", "TTS_PAID", "ZERO_COST_MODE")}
    try:
        for k in old_env:
            os.environ.pop(k, None)
        os.environ["GEMINI_TTS_KEY"] = "k1"
        os.environ["GEMINI_API_KEY"] = "paid"
        os.environ["TTS_PAID"] = "1"
        assert EX.tts_keys() == ["k1"]
        os.environ["GEMINI_TTS_KEY_2"] = "k2"
        os.environ["GEMINI_TTS_KEY_6"] = "k6"
        assert EX.tts_keys() == ["k1", "k2", "k6"]
    finally:
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # Line cutoff protection test
    sr = 16000
    t = np.linspace(0, 3.2, int(sr * 3.2), endpoint=False)
    sig = (0.3 * np.sin(2 * np.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 2.5 * t))).astype(np.float32)
    sig[int(sr * 1.5):int(sr * 2.8)] = sig[int(sr * 0.1):int(sr * 1.4)]
    p1 = str(tmp_path / "line1.wav")
    wavfile.write(p1, sr, np.clip(sig * 32767, -32768, 32767).astype(np.int16))
    text_bn = "রাত তখন অনেক, হঠাৎ ঘরের ভেতর থেকে অদ্ভুত একটা শব্দ শোনা গেল।"
    assert EX.fix_heard_twice([{"out": p1, "plain": text_bn, "voice": "Charon"}]) == 0
