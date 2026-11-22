"""POSE-FIRST artwork pipeline: MECHANICS only (the pictures here are drawn stand-ins - never evidence of real
image-generation quality; the real pictures come from mode = pose_art and are judged by the owner)."""
import json
import os
import sys

import cv2
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _figure(arms_out=True, H=1920, W=1280):
    img = np.full((H, W, 3), 180, np.uint8)
    cx = W // 2
    cv2.circle(img, (cx, 230), 120, (120, 170, 240), -1)
    cv2.circle(img, (cx, 230), 120, (20, 20, 20), 6)
    for ex in (cx - 45, cx + 45):
        cv2.circle(img, (ex, 210), 14, (255, 255, 255), -1)
        cv2.circle(img, (ex, 210), 7, (10, 10, 10), -1)
    cv2.rectangle(img, (cx - 40, 330), (cx + 40, 470), (120, 170, 240), -1)
    cv2.rectangle(img, (cx - 170, 460), (cx + 170, 1050), (240, 205, 150), -1)
    if arms_out:
        cv2.line(img, (cx - 170, 500), (cx - 420, 1000), (240, 205, 150), 70)
        cv2.line(img, (cx + 170, 500), (cx + 420, 1000), (240, 205, 150), 70)
    else:
        cv2.rectangle(img, (cx - 240, 470), (cx - 170, 1000), (240, 205, 150), -1)
        cv2.rectangle(img, (cx + 170, 470), (cx + 240, 1000), (240, 205, 150), -1)
    cv2.line(img, (cx - 80, 1050), (cx - 200, 1800), (110, 110, 110), 110)
    cv2.line(img, (cx + 80, 1050), (cx + 200, 1800), (110, 110, 110), 110)
    return img


def test_pose_sets_sizes_and_published_price():
    from engine2 import posefirst as PF
    core = PF.selected("core")
    assert core == ["master", "arm45", "arm90", "arm120", "both_up", "point_index"]
    assert len(PF.selected("hands")) == 8 and PF.size_of("hand_point") == (1024, 1024)
    assert PF.size_of("master") == (1280, 1920)                 # the model's maximum side is 1920 px
    est = PF.estimate(["master"])
    assert est["neurons_each"]["master"] == round(12 * 26.05 + 5.37, 1)   # 3 x 4 output tiles + 1 input tile
    with pytest.raises(ValueError):
        PF.selected("arm999")


def test_every_pose_prompt_keeps_identity_and_is_one_whole_character():
    from engine2 import posefirst as PF
    rec = {"name": "Hari", "look": "a man with a moustache, light blue shirt, grey trousers, black sandals"}
    for pid in PF.selected("all"):
        p = PF.prompt_for(rec, pid)
        assert "SAME character" in p and "reference" in p and len(p) <= 1990
    assert "index finger" in PF.prompt_for(rec, "point_index") and "curled" in PF.prompt_for(rec, "point_index")


def test_reference_input_is_shrunk_inside_the_documented_limit(tmp_path):
    from engine2 import posefirst as PF
    ref = np.zeros((1024, 576, 4), np.uint8)
    ref[100:900, 150:420] = (200, 150, 100, 255)
    f = PF.small_reference(ref, str(tmp_path / "r.jpg"))
    im = cv2.imread(f)
    assert max(im.shape[:2]) <= 511


def test_master_check_wants_arms_away_from_the_body():
    from engine2 import posefirst as PF
    import cutout_assets as CA
    a, l_ = PF.limbs_clear(CA.key_out(_figure(True), keep_all=True))
    b, _ = PF.limbs_clear(CA.key_out(_figure(False), keep_all=True))
    assert a >= 0.5 and l_ >= 0.5 and b < 0.5


def test_resume_429_and_owner_inbox(tmp_path, monkeypatch):
    from engine2 import posefirst as PF
    import cutout_assets as CA
    import char_sheet
    monkeypatch.setattr(char_sheet, "_colours", lambda a, b: ({}, []))
    monkeypatch.setattr(char_sheet, "_eyes_in_head", lambda a: [(1, 1), (2, 2)])
    store = PF.Store("hari", root=str(tmp_path))
    ref = np.zeros((1024, 576, 4), np.uint8)
    ref[100:900, 150:420] = (200, 150, 100, 255)
    calls = []

    def pic(prompt, ref_path, seed, w, h):
        calls.append((w, h))
        if len(calls) >= 2:
            raise CA.Paused("HTTP 429")                     # the free limit after one picture
        ok, buf = cv2.imencode(".png", _figure(True))
        return buf.tobytes()
    made = PF.make({"name": "Hari", "look": "x"}, ref, pic, ["master", "arm45", "arm90"], store)
    assert made == 1 and store.status("master") == "generated" and store.status("arm45") == "pending"
    assert (store.idx.get("arm45") or {}).get("attempts", 0) == 0     # a refused call costs no attempt
    assert json.load(open(store.idx_f))["_approved"] is False
    # the owner puts his own picture for arm45 into the inbox: used, no API call
    cv2.imwrite(os.path.join(store.inbox, "arm45.png"), _figure(True))
    calls.clear()
    PF.make({"name": "Hari", "look": "x"}, ref, lambda *a: (_ for _ in ()).throw(AssertionError("no call")), ["master", "arm45"], store)
    assert store.status("arm45") == "generated" and store.idx["arm45"]["source"].startswith("owner") and not calls
    rep = PF.armlift_from_poses(store, str(tmp_path / "al"))
    assert [s["pose"] for s in rep["steps"] if s.get("status", "").startswith("MISSING")] == ["arm90", "arm120", "both_up"]


def test_pose_art_mode_is_test_only():
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert 'env("MODE") == "pose_art"' in src and "return pose_art_run()" in src
    for f in ("story_engine.py", "scene_planner.py", "animation_renderer.py", "cartoon_rig.py"):
        assert "posefirst" not in open(os.path.join(ROOT, f), encoding="utf-8").read()


def test_an_api_error_stops_the_run_with_the_exact_error_and_no_substitute(tmp_path, monkeypatch):
    from engine2 import posefirst as PF
    import char_sheet
    monkeypatch.setattr(char_sheet, "_colours", lambda a, b: ({}, []))
    monkeypatch.setattr(char_sheet, "_eyes_in_head", lambda a: [(1, 1), (2, 2)])
    store = PF.Store("hari", root=str(tmp_path))
    ref = np.zeros((1024, 576, 4), np.uint8)
    ref[100:900, 150:420] = (200, 150, 100, 255)
    calls = []

    def pic(prompt, ref_path, seed, w, h):
        calls.append(pid_of(prompt))
        if len(calls) == 2:
            raise RuntimeError('HTTP 429: {"errors":[{"code":4006,"message":"daily free allocation"}]}')
        ok, buf = cv2.imencode(".png", _figure(True))
        return buf.tobytes()
    pid_of = lambda p: p[:10]
    made = PF.make({"name": "Hari", "look": "x"}, ref, pic, PF.SIX, store)
    assert made == 1 and len(calls) == 2                    # stopped at the error, nothing after it
    err = store.idx["_stopped_by_error"]
    assert err["pose"] == "arm45" and "HTTP 429" in err["error"] and "4006" in err["error"]
    assert [store.status(p) for p in PF.SIX] == ["generated"] + ["pending"] * 5
    orig = os.path.join(store.poses, store.idx["master"]["original_file"])
    assert cv2.imread(orig).shape[:2] == (1920, 1280)        # the provider's file, full size, byte for byte
    cs = PF.contact_sheet(store, str(tmp_path / "cs.jpg"))
    cm = PF.comparison_sheet(store, ref, str(tmp_path / "cmp.jpg"))
    assert os.path.exists(cs) and os.path.exists(cm)


def test_pose_art_never_uses_mock_or_another_provider():
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    body = src[src.index("def pose_art_run():"):src.index("def rig_test_run():")]
    assert "if MOCK:" in body and "_cf_request_all(CF_MODEL" in body
    assert "agnes" not in body.lower() and "armlift" not in body and "mock_image" not in body


def test_an_unreadable_reply_stops_too_and_keeps_the_providers_file(tmp_path):
    from engine2 import posefirst as PF
    store = PF.Store("hari", root=str(tmp_path))
    ref = np.zeros((1024, 576, 4), np.uint8)
    ref[100:900, 150:420] = (200, 150, 100, 255)
    calls = []

    def pic(*a):
        calls.append(1)
        return b"\x89PNG not really a picture"
    PF.make({"name": "Hari", "look": "x"}, ref, pic, PF.SIX, store)
    assert len(calls) == 1 and "could not be read" in store.idx["_stopped_by_error"]["error"]
    assert os.path.exists(os.path.join(store.poses, store.idx["master"]["original_file"]))
    assert all(store.status(p) != "generated" for p in PF.SIX)


def test_workflow_has_the_mode_inputs_secrets_and_keeps_the_website_out():
    import yaml
    wf = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "horror-story.yml")))
    inputs = wf[True]["workflow_dispatch"]["inputs"]
    assert "mode" in inputs and "character" in inputs and "pose_art" in inputs["mode"]["description"]
    txt = open(os.path.join(ROOT, ".github", "workflows", "horror-story.yml")).read()
    assert "CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}" in txt and "CHAR_SHEET_CHARACTER: ${{ github.event.inputs.character }}" in txt
    assert "github.event.inputs.mode != 'pose_art'" in wf["jobs"]["site"]["if"]
