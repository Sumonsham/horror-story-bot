"""Tests for the 2.5D cut-out system (offline, with the stand-in provider - the mechanics, not the art quality)."""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.setdefault("MOCK", "1")


def _ghost():
    """(a person in a shirt and trousers: the stand-in draws its separate pieces cleanly)"""
    import character_designer as CD
    c = {"name": "Madhu", "gender": "male", "age": "young", "kind": "human", "look": "a young man, combed black hair, a green shirt and grey trousers"}
    d, _, _ = CD.design(c)
    return {"name": c["name"], "look": c["look"], "design": d}


def test_assets_made_checked_and_kept(tmp_path):
    import cutout_assets as CA
    from fake_provider import Fake
    rec = _ghost()
    reg = CA.Registry(str(tmp_path))
    rep = CA.ensure_cast([rec], reg, Fake(rec["design"]), places=[("road", {})])
    key = CA.char_key(rec)
    assert rep["characters"]["Madhu"]["status"] == "ready" and rep["plates"]["road"] == "ready"
    files = os.listdir(tmp_path / key)
    for f in ("body.png", "rig.json", "head_three_q.png", "head_three_q.json", "part_torso.png", "part_thigh_near.png",
              "piece_torso.png", "piece_arm.png", "piece_legs.png"):
        assert f in files
    assert json.load(open(tmp_path / key / "rig.json"))["method"] == "rebuilt"           # built from separate pieces
    meta = json.load(open(tmp_path / key / "rig.json"))
    assert {"head", "torso", "thigh_near", "shin_near", "thigh_far", "shin_far"} <= set(meta["parts"])
    again = CA.ensure_cast([rec], reg, Fake(rec["design"]))                 # nothing is made twice
    assert again["made"] == 0
    assert (tmp_path / "history.jsonl").exists() and json.load(open(tmp_path / "index.json"))["characters"][key]["status"] == "ready"


def test_free_limit_pauses_and_the_next_run_continues(tmp_path):
    import cutout_assets as CA
    from fake_provider import Fake
    rec = _ghost()
    reg = CA.Registry(str(tmp_path))
    first = CA.ensure_cast([rec], reg, Fake(rec["design"], limit_after=2))
    assert first["paused"] and first["characters"]["Madhu"]["status"] in ("partial", "pending")
    assert os.path.exists(tmp_path / CA.char_key(rec) / "body.png")       # the finished work is kept
    second = CA.ensure_cast([rec], CA.Registry(str(tmp_path)), Fake(rec["design"]))
    assert not second["paused"] and second["characters"]["Madhu"]["status"] == "ready"
    assert second["made"] == 8 - 2                                          # only what was missing (8 pictures in all)


def test_a_bad_picture_is_detected_never_marked_ready(tmp_path):
    import cutout_assets as CA
    from fake_provider import Fake

    class Empty(Fake):
        def __call__(self, prompt, ref, seed, w, h):
            self.calls += 1
            import cv2
            return cv2.imencode(".png", np.full((h, w, 3), (180, 180, 180), np.uint8))[1].tobytes()
    rec = _ghost()
    reg = CA.Registry(str(tmp_path))
    p = Empty(rec["design"])
    rep = CA.ensure_cast([rec], reg, p)
    assert rep["characters"]["Madhu"]["status"] == "failed" and p.calls == 3          # retried, but not for ever
    CA.ensure_cast([rec], reg, p)
    CA.ensure_cast([rec], reg, p)
    assert p.calls == 6                                     # after 6 failures the free limit is not wasted again


def test_cutout_character_draws_with_the_same_motions(tmp_path):
    import cartoon_rig as R
    import cinematic_camera as cc
    import cutout_assets as CA
    import cutout_rig as CR
    from fake_provider import Fake
    rec = _ghost()
    reg = CA.Registry(str(tmp_path))
    CA.ensure_cast([rec], reg, Fake(rec["design"]))
    ch = CR.load("m", rec["design"], str(tmp_path), CA.char_key(rec))
    assert ch is not None and ch.complete and len(ch.heads) >= 3
    cam = cc.Camera(320, 320)
    cam.set(960, 700, 1.8)
    frames = []
    for pose, mouth, blink in ((R.POSES["stand"], (0.0, "rest"), 0.0), (R.walk_pose(1.2), (0.9, "A"), 1.0)):
        img = np.zeros((320, 320, 3), np.uint8)
        j = ch.draw(R.Painter(img, cam), {"x": 960, "ground_y": 935, "facing": 1.0, "head_yaw": 0.6, "pose": dict(pose),
                                          "mouth": mouth, "blink": blink, "t": 0.0})
        assert {"ft_n", "ft_f", "hd_n", "head", "k"} <= set(j)
        frames.append(img.astype(int))
    assert frames[0].sum() > 0 and np.abs(frames[0] - frames[1]).sum() > 0            # it is drawn and it moves


def test_two_and_a_half_d_is_off_unless_switched_on(monkeypatch):
    import story_engine
    monkeypatch.delenv("ART_MODE", raising=False)
    assert story_engine.cutout_art() is None
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert 'env("ART_MODE").strip().lower() != "cutout"' in src
    assert "_cf_request_all(CF_MODEL" in src.split("def _cutout_image")[1][:600]          # never the reference-less backup


def test_scene_check_finds_a_missing_character():
    import asset_qa
    plan = {"duration": 10.0, "characters": [{"id": "a"}], "camera": [{"t0": 0.0, "t1": 10.0}], "dialogue": []}
    bad = asset_qa.scene(plan, {"a", "b"}, {"a", "b"}, {"a": "cutout"})
    assert not bad["pass"] and any("'b'" in p for p in bad["problems"])
    ok = asset_qa.scene(plan, {"a"}, {"a"}, {"a": "code"})
    assert ok["pass"] and ok["notes"]


def test_plate_check_rejects_black_and_washed_out():
    import asset_qa
    assert not asset_qa.plate(np.zeros((576, 1024, 3), np.uint8))["pass"]
    assert not asset_qa.plate(np.full((576, 1024, 3), 250, np.uint8))["pass"]
    assert asset_qa.plate(np.full((576, 1024, 3), 90, np.uint8))["pass"]


def test_rebuilt_arm_stays_attached_when_it_moves(tmp_path):
    """the arm is a separate piece: pointing straight out, the hand is still at the end of the arm (no floating hand)"""
    import cartoon_rig as R
    import cutout_assets as CA
    import cutout_rig as CR
    from fake_provider import Fake
    rec = _ghost()
    reg = CA.Registry(str(tmp_path))
    CA.ensure_cast([rec], reg, Fake(rec["design"], broken={"overlap"}))     # (an arm drawn over the chest in the reference)
    ch = CR.load("m", rec["design"], str(tmp_path), CA.char_key(rec))
    assert ch.meta["method"] == "rebuilt" and all(ch.meta["arm_free"].values())          # no movement limit needed
    st = {"x": 960, "ground_y": 935, "facing": 1.0, "head_yaw": 0.6, "pose": dict(R.POSES["stand_point"]), "t": 0.0}
    j = ch.joints(st)
    s = ch._s()
    ua, fa = ch.parts["uarm_near"][1] * s, ch.parts["farm_near"][1] * s
    import math
    assert abs(math.hypot(j["el_n"][0] - j["sh_n"][0], j["el_n"][1] - j["sh_n"][1]) - ua) < 1.0
    assert abs(math.hypot(j["hd_n"][0] - j["el_n"][0], j["hd_n"][1] - j["el_n"][1]) - fa) < 1.0
    assert j["hd_n"][0] - j["sh_n"][0] > 0.8 * (ua + fa)                                   # really pointing forward


def test_each_character_type_gets_its_own_pieces():
    import asset_plan
    import character_designer as CD
    looks = {"man": ("male", "adult", "human", "a blue shirt and grey trousers"),
             "saree": ("female", "adult", "human", "hair in a bun, a red saree with a gold border"),
             "ghost": ("female", "young", "ghost", "long open black hair down to her waist, a torn white saree"),
             "child": ("male", "child", "human", "a little boy of about eight, a yellow shirt and blue shorts")}
    plans = {k: asset_plan.plan(CD.design({"name": k, "gender": g, "age": a, "kind": kd, "look": l})[0])
             for k, (g, a, kd, l) in looks.items()}
    assert plans["man"]["pieces"] == ["torso", "arm", "legs"]
    assert {"skirt", "pallu"} <= set(plans["saree"]["pieces"]) and "legs" not in plans["saree"]["pieces"]
    assert {"skirt", "hair_back"} <= set(plans["ghost"]["pieces"]) and plans["ghost"]["floats"]
    assert plans["child"]["child"] and plans["child"]["head_fraction"][1] > plans["man"]["head_fraction"][1]
    lay = plans["saree"]["layers"]                       # garments cover what they cover in real life
    assert lay.index("hair_back") < lay.index("torso") < lay.index("pallu") < lay.index("uarm_near")
    assert lay.index("thigh_near") < lay.index("skirt_up") < lay.index("torso")


def test_an_inconsistent_piece_is_rejected(tmp_path):
    import cv2
    import asset_qa
    import cutout_assets as CA
    import cutout_rebuild as RB
    from fake_provider import Fake
    import art_director as AD
    rec = _ghost()
    ref = CA.key_out(CA._decode(Fake(rec["design"])(AD.character_prompt(rec), None, 1, 576, 1024)))
    rig, _ = CA.auto_rig(ref)
    M = RB.measure(ref, rig)
    torso = CA.key_out(CA._decode(Fake(rec["design"])(AD.part_prompt(rec, "torso"), None, 1, 576, 640)))
    assert asset_qa.part(torso, "torso", ref, M)["pass"]                          # the right shirt: accepted
    other = torso.copy()
    hsv = cv2.cvtColor(other[..., :3], cv2.COLOR_BGR2HSV)
    hsv[..., 0] = (hsv[..., 0].astype(int) + 90) % 180                            # another character's shirt colour
    other[..., :3] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    q = asset_qa.part(other, "torso", ref, M)
    assert not q["pass"] and any("colours differ" in p for p in q["problems"])


def test_saree_and_ghost_are_built_without_legs_and_stay_whole(tmp_path):
    import cartoon_rig as R
    import cinematic_camera as cc
    import character_designer as CD
    import cutout_assets as CA
    import cutout_rig as CR
    from fake_provider import Fake
    for c in ({"name": "S", "gender": "female", "age": "adult", "kind": "human", "look": "hair in a bun, a red saree with a gold border"},
              {"name": "G", "gender": "female", "age": "young", "kind": "ghost", "look": "long open black hair down to her waist, a torn white saree"}):
        d, _, _ = CD.design(c)
        rec = {"name": c["name"], "look": c["look"], "design": d}
        reg = CA.Registry(str(tmp_path / c["name"]))
        CA.ensure_cast([rec], reg, Fake(d))
        ch = CR.load(c["name"], d, str(tmp_path / c["name"]), CA.char_key(rec))
        assert ch is not None and ch.meta["no_legs"] and {"skirt_up", "skirt_lo"} <= set(ch.parts)
        cam = cc.Camera(300, 400)
        cam.set(960, 760, 2.0)
        img = np.zeros((400, 300, 3), np.uint8)
        ch.draw(R.Painter(img, cam), {"x": 960, "ground_y": 935, "facing": 1.0, "head_yaw": 0.9, "pose": dict(R.POSES["sit_talk"]), "t": 0.0})
        m = (img.sum(axis=2) > 0).astype(np.uint8)
        n, _, st, _ = cv2_cc(m)
        assert n == 2 or sorted(st[1:, 4])[-2] < 0.01 * st[1:, 4].max()          # ONE connected figure: nothing torn off


def cv2_cc(m):
    import cv2
    return cv2.connectedComponentsWithStats(m, 8)
