"""Tests for Painted 2D Cartoon Studio (characters, props, empty backgrounds, manifest, compositor & workflow)."""
import os
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import characters as CH
import painted2d_studio as P2D
import manifest as MF
import compositor as COMP
import cartoon25d as C25


def _fake_image_fn(prompt, ref_path, seed, w, h):
    """Creates a synthetic studio-grey image with a painted character or prop in the center."""
    img = np.full((h, w, 3), 184, dtype=np.uint8)
    if "Empty painted 2D background" in prompt:
        img[:, :] = (24, 30, 44)
        cv2.rectangle(img, (0, int(h * 0.65)), (w, h), (34, 28, 26), -1)
    elif "prop illustration" in prompt:
        cv2.rectangle(img, (int(w * 0.35), int(h * 0.25)), (int(w * 0.65), int(h * 0.78)), (155, 32, 38), -1)
    else:
        # Head + torso + legs on plain grey background
        cv2.circle(img, (w // 2, int(h * 0.14)), int(w * 0.09), (210, 175, 145), -1)
        cv2.circle(img, (w // 2 - 14, int(h * 0.13)), 4, (20, 20, 20), -1)
        cv2.circle(img, (w // 2 + 14, int(h * 0.13)), 4, (20, 20, 20), -1)
        if "mouth open" in prompt or "gasping" in prompt:
            cv2.ellipse(img, (w // 2, int(h * 0.17)), (10, 8), 0, 0, 360, (60, 20, 25), -1)
        cv2.rectangle(img, (int(w * 0.34), int(h * 0.23)), (int(w * 0.66), int(h * 0.56)), (45, 70, 115), -1)
        cv2.rectangle(img, (int(w * 0.37), int(h * 0.56)), (int(w * 0.48), int(h * 0.92)), (35, 35, 45), -1)
        cv2.rectangle(img, (int(w * 0.52), int(h * 0.56)), (int(w * 0.63), int(h * 0.92)), (35, 35, 45), -1)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    assert ok
    return buf.tobytes()


def test_painted2d_scout_and_build(tmp_path):
    story = {
        "title": "রাত-তদন্ত: পেরেকে ঝোলানো শাড়ি",
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
                    {"speaker": "Bapi", "emotion": "scared", "text": "মামা, দেওয়ালের পেরেকে ওই রক্তমাখা শাড়িটা ঝুলছে কেন?"},
                    {"speaker": "Nilkantha", "emotion": "normal", "text": "সাবধান বাপি, হারিকেনটা উঁচু করে ধর।"},
                ],
            }
        ],
    }
    scout = P2D.scout_story_assets(story)
    assert len(scout["characters"]) == 2
    assert len(scout["backgrounds"]) == 1
    prop_names = [p["name"] for p in scout["scene_props"][0]]
    assert any("saree" in n for n in prop_names)
    assert any("lantern" in n for n in prop_names)

    assets_dir = str(tmp_path / "assets")
    cache_dir = str(tmp_path / "cache")
    records, by_name, bgs, scene_props, stats = P2D.build_story_assets(
        story, assets_dir, cache_dir, image_fn=_fake_image_fn, slot_key="2026-11-27@20", series_names=["bapi", "nilkantha"]
    )
    assert "bapi" in records and records["bapi"]["mode"] == "photo"
    assert "talking" in records["bapi"]["expr"] and "blink" in records["bapi"]["expr"]
    assert len(bgs) == 1 and os.path.exists(bgs[0][0])
    assert len(scene_props[0]) >= 2
    assert all(os.path.exists(pr["path"]) for pr in scene_props[0])

    # Second run with image_fn=None must reuse 100% from local repo store without generating anything
    records2, _, bgs2, scene_props2, stats2 = P2D.build_story_assets(
        story, assets_dir, str(tmp_path / "cache2"), image_fn=None, slot_key="2026-11-27@20", series_names=["bapi", "nilkantha"]
    )
    assert stats2["images_made"] == 0 and stats2["bg_made"] == 0 and stats2["props_made"] == 0
    assert stats2["cache_hits"] == 2 and stats2["bg_hits"] == 1 and stats2["props_hits"] >= 2

    # Build manifest and check props + 1-2 character framing
    beats = [(0.5, 3.0, "Bapi", "scared", "মামা, শাড়িটা দেখো!"), (3.3, 6.0, "Nilkantha", "normal", "সাবধান বাপি।")]
    m = MF.build_scene(0, story["scenes"][0], beats, 6.5, by_name, bgs2[0], "creepy", props=scene_props2[0])
    assert len(m["characters"]) == 2
    assert len(m["props"]) >= 2
    assert m["beats"][0]["speaker"] == "bapi" and m["beats"][0]["listener"] == "nilkantha"


def test_cartoon25d_opt_in_and_workflow_default():
    assert C25.active(lambda k: {"ANIM_MODE": ""}.get(k, "")) is False
    assert C25.active(lambda k: {"ANIM_MODE": "character"}.get(k, "")) is False
    assert C25.active(lambda k: {"ANIM_MODE": "cartoon25d"}.get(k, "")) is True
    yml = open(os.path.join(ROOT, ".github/workflows/horror-story.yml"), encoding="utf-8").read()
    assert "ANIM_MODE: ${{ vars.ANIM_MODE || 'character' }}" in yml
    assert "assets/painted2d_prep" in yml
    comp_src = open(os.path.join(ROOT, "compositor.py"), encoding="utf-8").read()
    assert "import cartoon_rig" not in comp_src
