"""Tests for the 2.5D cut-out system (offline, with the stand-in provider - the mechanics, not the art quality)."""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.setdefault("MOCK", "1")


def setup_module(_m):
    import puppet_builder
    puppet_builder.ARM_MIN = 0.2      # (TEST ONLY: the stand-in figure is drawn by the code rig, whose arms are short)


def _ghost():
    """(a person in a shirt and trousers: the stand-in draws its separate pieces cleanly)"""
    import character_designer as CD
    c = {"name": "Madhu", "gender": "male", "age": "young", "kind": "human", "look": "a young man, combed black hair, a green shirt and grey trousers"}
    d, _, _ = CD.design(c)
    return {"name": c["name"], "look": c["look"], "design": d}


def test_assets_made_checked_and_kept(tmp_path):
    """ONE reference picture -> the puppet -> the assembled 7-pose check -> ready; nothing is made twice"""
    import cutout_assets as CA
    from fake_provider import Fake
    rec = _ghost()
    reg = CA.Registry(str(tmp_path))
    p = Fake(rec["design"])
    rep = CA.ensure_cast([rec], reg, p, places=[("road", {})])
    key = CA.char_key(rec)
    assert rep["characters"]["Madhu"]["status"] == "ready" and rep["plates"]["road"] == "ready"
    files = os.listdir(tmp_path / key)
    for f in ("body.png", "rig.json", "head_ref.png", "head_ref.json", "assembly.jpg", "assembly.json", "part_torso.png",
              "part_thigh_near.png", "part_uarm_near.png"):
        assert f in files
    meta = json.load(open(tmp_path / key / "rig.json"))
    assert meta["method"] == "reference" and meta["gate"] == "pass"          # only a checked puppet is on disk as rig.json
    assert {"head", "torso", "uarm_near", "farm_near", "uarm_far", "farm_far", "thigh_near", "shin_near", "thigh_far",
            "shin_far"} <= set(meta["parts"])
    gate = json.load(open(tmp_path / key / "assembly.json"))
    assert gate["pass"] and set(gate["poses"]) == {"three_q_right", "three_q_left", "seated", "talking", "pointing", "walking"}
    assert gate["genuine_views"]["front"] is False and gate["genuine_views"]["side_profile"] is False     # (said honestly)
    calls = p.calls
    again = CA.ensure_cast([rec], reg, Fake(rec["design"]))                 # nothing is made twice
    assert again["made"] == 0 and calls == 2                                # (1 character picture + 1 background)
    assert (tmp_path / "history.jsonl").exists() and json.load(open(tmp_path / "index.json"))["characters"][key]["status"] == "ready"


def test_free_limit_pauses_and_the_next_run_continues(tmp_path):
    import cutout_assets as CA
    from fake_provider import Fake
    rec = _ghost()
    reg = CA.Registry(str(tmp_path))
    first = CA.ensure_cast([rec], reg, Fake(rec["design"], limit_after=0))
    assert first["paused"] and first["characters"]["Madhu"]["status"] in ("partial", "pending")
    second = CA.ensure_cast([rec], CA.Registry(str(tmp_path)), Fake(rec["design"]))
    assert not second["paused"] and second["characters"]["Madhu"]["status"] == "ready" and second["made"] == 1


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
    assert rep["characters"]["Madhu"]["status"] != "ready" and p.calls == 3          # retried, but not for ever
    CA.ensure_cast([rec], reg, p)
    assert reg.index["characters"][CA.char_key(rec)]["status"] == "failed" and p.calls == 6
    CA.ensure_cast([rec], reg, p)
    assert p.calls == 6                                     # after 6 failures the free limit is not wasted again
    assert not os.path.exists(tmp_path / CA.char_key(rec) / "rig.json")


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
    assert ch is not None and ch.complete and "ref" in ch.heads                # its OWN head (blinks + talks on it)
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


def test_arm_stays_attached_when_it_moves(tmp_path):
    """pointing straight out, the hand is at the end of the arm and the arm at the shoulder (no floating hand)"""
    import cartoon_rig as R
    import cutout_assets as CA
    import cutout_rig as CR
    from fake_provider import Fake
    rec = _ghost()
    reg = CA.Registry(str(tmp_path))
    CA.ensure_cast([rec], reg, Fake(rec["design"]))
    ch = CR.load("m", rec["design"], str(tmp_path), CA.char_key(rec))
    assert ch.meta["method"] == "reference" and all(ch.meta["arm_free"].values())          # no movement limit
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


def test_saree_is_built_without_legs_and_stays_whole_and_a_ghost_floats(tmp_path):
    import cv2
    import assembly_qa as AQ
    import asset_plan
    import character_designer as CD
    import cutout_assets as CA
    import cutout_rig as CR
    import puppet_builder as PB
    from fake_provider import Fake
    c = {"name": "S", "gender": "female", "age": "adult", "kind": "human", "look": "hair in a bun, a red saree with a gold border"}
    d, _, _ = CD.design(c)
    rec = {"name": c["name"], "look": c["look"], "design": d}
    reg = CA.Registry(str(tmp_path / "s"))
    assert CA.ensure_cast([rec], reg, Fake(d))["characters"]["S"]["status"] == "ready"
    ch = CR.load("S", d, str(tmp_path / "s"), CA.char_key(rec))
    assert ch is not None and ch.meta["no_legs"] and {"skirt_up", "skirt_lo"} <= set(ch.parts)
    for pose in ("sit_talk", "walk", "stand"):                # ONE connected figure: the saree never tears
        al = AQ._alpha(ch, AQ._pose(pose), 0.6, 0.6)[0]
        n, _, st, _ = cv2.connectedComponentsWithStats((al > 0.5).astype(np.uint8), 8)
        assert n == 2
    # a ghost in a saree: the same cloth structure, floating (no legs at all)
    g = {"name": "G", "gender": "female", "age": "young", "kind": "ghost", "look": "hair in a bun, a torn white saree"}
    gd = CD.design(g)[0]
    plan = asset_plan.plan(gd)
    assert plan["archetype"] == "ghost_flowing" and plan["floats"]
    body = cv2.imread(str(tmp_path / "s" / CA.char_key(rec) / "body.png"), cv2.IMREAD_UNCHANGED)
    rig, probs, _ = PB.build(body, plan)
    assert rig["no_legs"] and rig["floats"] and "thigh_near" not in rig["parts"] and not probs


def test_the_assembled_check_rejects_a_duplicated_person(tmp_path):
    """the real failure of 21 Nov 2026: a whole second person drawn into a leg piece. Glued onto the reference, the
    assembled check must refuse it (never 'ready')"""
    import cv2
    import assembly_qa as AQ
    import cutout_assets as CA
    import cutout_rig as CR
    import puppet_builder as PB
    import asset_plan
    from fake_provider import Fake
    import art_director as AD
    rec = _ghost()
    body = CA.key_out(CA._decode(Fake(rec["design"])(AD.character_prompt(rec), None, 1, 576, 1024)))
    ys, xs = np.where(body[..., 3] > 127)
    small = cv2.resize(body[ys.min():ys.max(), xs.min():xs.max()], None, fx=0.32, fy=0.32)
    bad = body.copy()
    H = ys.max() - ys.min()
    y0 = int(ys.min() + 0.52 * H)                           # over the legs (touching the body, as in the real test)
    x0 = int((xs.min() + xs.max()) / 2 - small.shape[1] * 0.3)
    roi = bad[y0:y0 + small.shape[0], x0:x0 + small.shape[1]]
    a = small[..., 3:4] / 255.0
    roi[...] = (roi * (1 - a) + small * a).astype(np.uint8)
    plan = asset_plan.plan(rec["design"])
    rig, probs, _ = PB.build(bad, plan)
    if rig is None or probs:
        return                                              # refused already while cutting - good
    CA.Maker._save_rig(str(tmp_path), rig)
    CA.save_ref_head(str(tmp_path), rig)
    ch = CR.CutoutCharacter("m", rec["design"], str(tmp_path))
    assert not AQ.check(ch, bad, probs, plan)["pass"]


def test_an_old_or_unchecked_puppet_is_never_used(tmp_path):
    import cutout_assets as CA
    import cutout_rig as CR
    from fake_provider import Fake
    rec = _ghost()
    reg = CA.Registry(str(tmp_path))
    CA.ensure_cast([rec], reg, Fake(rec["design"]))
    key = CA.char_key(rec)
    meta = json.load(open(tmp_path / key / "rig.json"))
    meta.pop("gate")                                        # a rig of the first version (never checked as a whole)
    json.dump(meta, open(tmp_path / key / "rig.json", "w"))
    assert CR.load("m", rec["design"], str(tmp_path), key) is None
    reg.index["characters"][key]["builder"] = None          # its 'ready' from before does not count
    assert CA.status_of(reg, rec) == "needs re-check"


def test_a_checking_error_keeps_the_reference_and_is_not_ready(tmp_path, monkeypatch):
    import assembly_qa as AQ
    import cutout_assets as CA
    from fake_provider import Fake

    def boom(*a, **k):
        raise ValueError("drawing failed")
    monkeypatch.setattr(AQ, "check", boom)
    rec = _ghost()
    reg = CA.Registry(str(tmp_path))
    rep = CA.ensure_cast([rec], reg, Fake(rec["design"]))
    key = CA.char_key(rec)
    assert rep["characters"]["Madhu"]["status"] == "partial"
    assert os.path.exists(tmp_path / key / "body.png") and not [f for f in os.listdir(tmp_path / key) if f.startswith("rejected")]


class _Sheet:
    """TEST ONLY (mechanics, not artwork): a stand-in provider that returns the reference picture; a walk prompt gets
    the reference 4 times side by side; it can refuse with HTTP 429 after N pictures, or crash"""

    def __init__(self, limit_after=None, crash_after=None):
        self.calls, self.prompts, self.refs = 0, [], []
        self.limit_after, self.crash_after = limit_after, crash_after

    def __call__(self, prompt, ref, seed, w, h):
        import cv2
        if self.limit_after is not None and self.calls >= self.limit_after:
            raise RuntimeError('HTTP 429: {"errors":[{"message":"AiError: you have used up your daily free allocation of 10,000 neurons"}]}')
        if self.crash_after is not None and self.calls >= self.crash_after:
            raise RuntimeError("connection reset")
        self.calls += 1
        self.prompts.append(prompt)
        self.refs.append(ref)
        img = cv2.imread(ref)
        if "sprite sheet" in prompt:
            bg = [int(v) for v in img[2, 2]]
            one = cv2.resize(img, (int(w // 4 * 0.7), int(h * 0.8)))
            px, py = w // 4 - one.shape[1], h - one.shape[0]
            one = cv2.copyMakeBorder(one, py // 2, py - py // 2, px // 2, px - px // 2, cv2.BORDER_CONSTANT, value=bg)
            img = np.hstack([one] * 4)
        else:
            img = cv2.resize(img, (w, h))
        return cv2.imencode(".png", img)[1].tobytes()


def _sheet_setup(tmp_path, monkeypatch):
    import cv2
    import hashlib
    import char_sheet as CS
    import cutout_assets as CA
    from fake_provider import Fake
    import art_director as AD
    monkeypatch.setattr(CS, "ROOT", str(tmp_path / "parts"))
    monkeypatch.setattr(CS, "OUT", str(tmp_path / "out"))
    real = CS.check_drawing                                 # (the stand-in faces the viewer: its 'side' skips the eye test)
    monkeypatch.setattr(CS, "check_drawing", lambda r, ref, v: real(r, ref, "stand" if v == "side" else v))
    sums = {}
    for c in CS.cast():
        key = CA.char_key({"name": c["name"], "look": c["look"]})
        d = tmp_path / "parts" / key
        d.mkdir(parents=True)
        img = CA._decode(Fake(c["design"])(AD.character_prompt(c), None, 1, 576, 1024))
        cv2.imwrite(str(d / "body_src.png"), img)
        cv2.imwrite(str(d / "body.png"), CA.key_out(img))
        for f in ("body_src.png", "body.png"):
            sums[str(d / f)] = hashlib.md5(open(d / f, "rb").read()).hexdigest()
    return CS, CA, sums


def _unchanged(sums):
    import hashlib
    return all(hashlib.md5(open(f, "rb").read()).hexdigest() == h for f, h in sums.items())


def test_char_sheet_429_at_once_makes_nothing_and_costs_no_attempt(tmp_path, monkeypatch):
    CS, CA, sums = _sheet_setup(tmp_path, monkeypatch)
    rep = CS.run(_Sheet(limit_after=0), log=lambda *a: None)
    assert rep["paused"] and rep["made"] == 0 and "10,000 neurons" in rep["blocker"]
    for n, r in rep["characters"].items():
        assert r["generated"] == [] and r["failed"] == [] and len(r["pending"]) == len(CS.VIEWS)
        assert not r["ready"] and not r["approved"] and r["state"].startswith("INCOMPLETE")
        key = CA.char_key(next(c for c in CS.cast() if c["name"] == n))
        assert all((CS.load_idx(key).get(v) or {}).get("attempts", 0) == 0 for v in CS.VIEWS)   # a refused call is no try
    assert _unchanged(sums)                                 # the originals are never touched


def test_char_sheet_one_character_then_resume_only_the_missing(tmp_path, monkeypatch):
    CS, CA, sums = _sheet_setup(tmp_path, monkeypatch)
    saved = []
    p1 = _Sheet(limit_after=3)
    r1 = CS.run(p1, log=lambda *a: None, only="Hari", on_saved=lambda n, v: saved.append((n, v)))
    h = r1["characters"]["Hari"]
    assert r1["paused"] and r1["made"] == 3 and h["generated"] == ["front", "side", "stand"]
    assert h["pending"] == ["sit", "talk", "point", "walk"] and not h["ready"] and not h["approved"]
    assert saved == [("Hari", "front"), ("Hari", "side"), ("Hari", "stand")]          # saved one by one, at once
    for other in ("Saraswati", "Kishori"):                  # the others are not touched at all
        assert not r1["characters"][other]["drawn_this_run"] and r1["characters"][other]["generated"] == []
        key = CA.char_key(next(c for c in CS.cast() if c["name"] == other))
        assert not os.path.exists(tmp_path / "parts" / key / "sheet" / "sheet.json")
    assert all("light blue full-sleeve shirt" in pr for pr in p1.prompts)      # only Hari's look was drawn
    p2 = _Sheet()
    r2 = CS.run(p2, log=lambda *a: None, only="hari")
    assert r2["made"] == 4 and r2["characters"]["Hari"]["state"].startswith("COMPLETE")
    assert not any(k in pr for pr in p2.prompts for k in ("seen straight from the FRONT", "true side profile",
                                                         "standing relaxed"))          # nothing redrawn
    assert not r2["characters"]["Hari"]["approved"] and not r2["characters"]["Hari"]["ready"]
    r3 = CS.run(_Sheet(), log=lambda *a: None, only="Hari")
    assert r3["made"] == 0                                  # complete: never drawn again
    key = CA.char_key(next(c for c in CS.cast() if c["name"] == "Hari"))
    assert set(p1.refs + p2.refs) == {str(tmp_path / "parts" / key / "body_src.png")}     # always the original
    ws = [__import__("cv2").imread(str(tmp_path / "out" / "Hari" / f"walk{k}.png"), -1) for k in range(1, 5)]
    assert len({w.shape for w in ws}) == 1                  # the 4 walk frames: one canvas, one ground line
    g = [np.where((w[..., 3] > 127).any(axis=1))[0].max() for w in ws]
    assert max(g) - min(g) <= 2
    assert _unchanged(sums)
    import pytest
    with pytest.raises(ValueError):
        CS.run(_Sheet(), log=lambda *a: None, only="Nobody")


def test_char_sheet_crash_keeps_every_saved_picture(tmp_path, monkeypatch):
    CS, CA, sums = _sheet_setup(tmp_path, monkeypatch)
    import pytest
    with pytest.raises(RuntimeError):
        CS.run(_Sheet(crash_after=2), log=lambda *a: None, only="Saraswati")
    key = CA.char_key(next(c for c in CS.cast() if c["name"] == "Saraswati"))
    idx = CS.load_idx(key)
    assert [v for v in CS.VIEWS if CS.image_status(idx, v) == "generated"] == ["front", "side"]
    os.remove(tmp_path / "parts" / key / "sheet" / "sheet.json")              # even the progress file lost:
    p = _Sheet()
    r = CS.run(p, log=lambda *a: None, only="Saraswati")
    assert r["made"] == len(CS.VIEWS) - 2                   # the pictures on disk are re-checked, not redrawn
    assert r["characters"]["Saraswati"]["state"].startswith("COMPLETE")
    assert _unchanged(sums)


def test_char_sheet_estimate_uses_the_published_price_only(tmp_path, monkeypatch):
    CS, CA, sums = _sheet_setup(tmp_path, monkeypatch)
    est = CS.estimate([c for c in CS.cast() if c["name"] == "Hari"])
    assert est["pictures_missing"] == len(CS.VIEWS)
    per = 4 * 26.05 + 4 * 5.37                              # 576x1024 = 4 tiles out, the 576x1024 original = 4 tiles in
    assert est["neurons_if_all_pass_first_time"] == round(per * len(CS.VIEWS))
    assert "NOT known" in est["note"] and "left_today" not in est                    # nothing invented


def test_a_front_face_is_not_accepted_as_a_side_view():
    import cv2
    import char_sheet as CS
    import cutout_assets as CA
    from fake_provider import Fake
    import art_director as AD
    import character_designer as CD
    c = {"name": "Hari", "gender": "male", "age": "adult", "kind": "human", "look": "a man, a blue shirt and grey trousers"}
    d = CD.design(c)[0]
    img = CA.key_out(CA._decode(Fake(d)(AD.character_prompt(dict(c, design=d)), None, 1, 576, 1024)))
    if len(CS._eyes_in_head(img)) < 2:
        return                                              # (the stand-in face shows no clear eye pair)
    q = CS.check_drawing(img, img, "side")
    assert not q["pass"] and any("not a true side view" in p for p in q["problems"])
