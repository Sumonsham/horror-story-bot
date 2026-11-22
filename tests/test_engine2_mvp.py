"""engine 2 hybrid MVP: rig safety, decisions, identity, isolation from production (no network, nothing generated)"""
import json
import os

import cv2
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIG = os.path.join(ROOT, "assets", "character_rigs", "hari", "export", "hari.json")
REF = os.path.join(ROOT, "assets", "character_library", "hari", "v1", "reference", "original.png")


@pytest.fixture(scope="module")
def rig():
    if not os.path.exists(RIG):
        pytest.skip("no Hari rig in this checkout")
    from engine2.rigby import raster as RS
    return RS.Rig(RIG)


def test_limits_and_unsafe_animations_found(rig):
    from engine2 import mvp
    lim = mvp.rig_limits(rig)
    assert set(lim) == {"r", "l"} and all(v["limit"] > v["rest"] for v in lim.values())
    saf = mvp.anim_safety(rig, lim)
    assert saf["idle"]["safe"]                              # standing still never lifts an arm
    assert not saf["indicate"]["safe"]                       # the far arm goes to ~80 degrees: past the safe range


def test_clamp_brings_every_frame_inside_the_limit(rig):
    from engine2 import mvp
    lim = mvp.rig_limits(rig)
    for anim in ("talk", "indicate", "sit_talk", "walk"):
        for t in np.linspace(0, rig.durations[anim], 9):
            p, _e = mvp.safe_pose(rig, anim, t, lim)
            for s in ("r", "l"):
                assert mvp.arm_raise(p, s) <= lim[s]["limit"] + 0.5


def test_armlift_failure_lowers_nothing_but_a_pass_raises_the_limit(rig):
    from engine2 import mvp
    base = mvp.rig_limits(rig)
    fake = {"arms": {"r": [{"degrees": 30, "pass": True}, {"degrees": 45, "pass": True}, {"degrees": 60, "pass": False}],
                     "l": [{"degrees": 30, "pass": False}]}}
    lim = mvp.rig_limits(rig, fake)
    assert lim["r"]["limit"] == max(45.0, base["r"]["limit"])
    assert lim["l"]["limit"] == base["l"]["limit"]


def test_decisions_never_use_failed_or_unapproved_assets_in_production(rig):
    from engine2 import mvp
    lim = mvp.rig_limits(rig)
    saf = mvp.anim_safety(rig, lim)
    inv = {"arm90": {"file": "x", "status": "passed", "approved": False, "rejected_by_owner": False},
           "both_up": {"file": "y", "status": "failed", "approved": False, "rejected_by_owner": False}}
    prev = {r["action"]: r for r in mvp.decide(saf, inv)}
    assert prev["one_arm_raised"]["method"] == "B_complete_pose" and prev["one_arm_raised"]["approved"] is False
    assert prev["both_arms_raised"]["method"] == "MISSING" and "failed" in prev["both_arms_raised"]["reason"]
    assert prev["scared"]["method"] == "MISSING"
    assert prev["pointing"]["method"] == "MISSING"           # no pointing drawing in this inventory, rig is not used
    prod = {r["action"]: r for r in mvp.decide(saf, inv, production=True)}
    for r in prod.values():
        assert r["method"] in ("MISSING", "camera"), r     # nothing approved -> production would use nothing


def test_owner_rejection_wins(rig):
    from engine2 import mvp
    saf = mvp.anim_safety(rig, mvp.rig_limits(rig))
    inv = {"arm90": {"file": "x", "status": "passed", "approved": False, "rejected_by_owner": True}}
    assert {r["action"]: r for r in mvp.decide(saf, inv)}["one_arm_raised"]["method"] == "MISSING"


def test_identity_is_never_an_approval_and_spots_a_recolour():
    from engine2 import mvp
    if not os.path.exists(REF):
        pytest.skip("no reference")
    ref = cv2.imread(REF, cv2.IMREAD_UNCHANGED)
    same = mvp.identity(ref, ref.copy())
    assert same["verdict"] == "CONSISTENT" and "approve" in same["note"]
    odd = ref.copy()
    hsv = cv2.cvtColor(odd[..., :3], cv2.COLOR_BGR2HSV)
    hsv[..., 0] = (hsv[..., 0].astype(int) + 60) % 180         # every colour shifted: a different character
    odd[..., :3] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    assert mvp.identity(ref, odd)["verdict"] in ("MISMATCH", "NEEDS_REVIEW")


def test_flood_fill_cutout_keeps_inside_and_drops_ground_shadow():
    from engine2 import mvp
    img = np.full((400, 300, 3), 180, np.uint8)
    cv2.ellipse(img, (150, 370), (90, 14), 0, 0, 360, (158, 156, 156), -1)          # soft grey ground shadow
    cv2.rectangle(img, (110, 60), (190, 360), (40, 40, 160), -1)                    # the figure
    cv2.rectangle(img, (140, 150), (160, 170), (180, 180, 180), -1)                 # background-grey INSIDE (a button)
    rgba = mvp.figure_rgba(img)
    a = rgba[..., 3]
    assert a[200, 150] == 255 and a[160, 150] == 255             # figure and its inner grey stay
    assert a[10, 10] == 0 and a[372, 60] == 0                    # background and shadow go


def test_production_paths_never_import_the_mvp():
    """isolation: no production module reads engine2.mvp or HYBRID_2D_MODE"""
    for fn in os.listdir(ROOT):
        if fn.endswith(".py") and fn not in ("main.py",):
            src = open(os.path.join(ROOT, fn), encoding="utf-8").read()
            assert "engine2.mvp" not in src and "HYBRID_2D_MODE" not in src, fn
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    i = src.find("from engine2 import mvp")
    while i != -1:                                               # only inside the three test-mode functions
        head = src.rfind("\ndef ", 0, i)
        assert src[head:head + 40].split("(")[0].strip().split()[-1] in ("engine_audit_run", "asset_qa_run", "render_test_run")
        i = src.find("from engine2 import mvp", i + 1)
    for read in ('env("HYBRID_2D_MODE")', 'getenv("HYBRID_2D_MODE")', 'environ.get("HYBRID_2D_MODE")', "vars.HYBRID_2D_MODE"):
        assert read not in src                                   # the flag exists only on paper: OFF, read nowhere


def test_workflow_lists_the_new_modes_and_keeps_them_off_the_website():
    import yaml
    wf = open(os.path.join(ROOT, ".github", "workflows", "horror-story.yml"), encoding="utf-8").read()
    for m in ("engine_audit", "asset_qa", "render_test"):
        assert f"{m} = engine 2" in wf
        assert f"github.event.inputs.mode != '{m}'" in wf
    yaml.safe_load(wf)


# ------------------------------------------------------------------ visual remediation (23 Nov 2026)

def test_body_metrics_ignores_a_raised_hand():
    from engine2 import mvp
    a = np.zeros((500, 300), np.uint8)
    cv2.rectangle(a, (120, 100), (180, 480), 255, -1)            # head + body, top at 100
    cv2.rectangle(a, (220, 20), (240, 200), 255, -1)             # a hand raised far above the head, to the side
    m = mvp.body_metrics(a)
    assert m["top"] == 100 and m["bottom"] == 480 and m["height"] == 380


def test_pose_scale_consistency_and_ground(rig):
    """every complete pose stands on the same ground at the rig's body height (+-1.5 %)"""
    from engine2 import mvp
    inv = mvp.pose_inventory("hari")
    if not inv:
        pytest.skip("no pose drawings")

    class Cam:
        s = 1.0

        def to_screen(self, x, y):
            return x, y
    for pid, rec in inv.items():
        cp = mvp.ComplexPose(rec["file"], 600.0)
        f = np.full((800, 500, 3), 236, np.uint8)
        a = cp.draw(f, Cam(), 250, 760, breathe=False) > 0.3
        m = mvp.body_metrics(a)
        assert abs(m["height"] - 600) / 600 < 0.015, (pid, m["height"])
        assert abs(m["bottom"] - 760) <= 2, (pid, m["bottom"])


def test_walk_waist_artifact_is_gone(rig):
    """the hidden top of a trouser leg must never show at the waist in any walk phase"""
    from engine2 import mvp
    w = mvp.waist_exposure(rig, phases=24)
    assert w["max_px"] <= 5, w


def test_walk_feet_stay_on_their_ground(rig):
    from engine2 import mvp
    rig.json_path = RIG
    lim = mvp.rig_limits(rig)
    fd = mvp._foot_data(rig)
    worst_sink = 0.0
    for k in range(24):
        p, _e = mvp.safe_pose(rig, "walk", rig.durations["walk"] * k / 24, lim)
        for s in ("r", "l"):
            worst_sink = max(worst_sink, fd[s]["rest_low"] - mvp._foot_low(p, s, fd[s]["rect"]))
    assert worst_sink <= 1.0                                     # no foot (rectangle) below its own ground line


def test_contact_shadow_sits_under_the_feet():
    from engine2 import mvp
    img = np.full((200, 300, 3), 180, np.uint8)
    out = mvp.contact_shadow(img.copy(), [(100, 150, 20, 1.0), (200, 140, 20, 0.0)])
    assert out[151, 100].mean() < 175                            # darker right under the planted foot
    assert out[141, 200].mean() >= 179                           # a foot in the air casts none here
    assert out[60, 100].mean() >= 179                            # nothing far from the feet (no big oval)


def test_missing_poses_are_left_out_and_blocked():
    from engine2 import mvp
    rows = [{"action": "neutral", "method": "A_rig", "asset": "rig:idle", "approved": False, "reason": ""},
            {"action": "scared", "method": "MISSING", "asset": None, "approved": False, "reason": "no drawing"},
            {"action": "scene_transition", "method": "camera", "asset": "x", "approved": True, "reason": ""}]
    tl, left = mvp.timeline(rows, [("neutral", 4, "a"), ("scared", 3, "a"), ("scene_transition", 2, None)], total=10)
    assert left == ["scared"] and [a for a, _d, _l in tl] == ["neutral", "scene_transition"]
    assert abs(sum(d for _a, d, _l in tl) - 10) < 1e-6
    gate = dict(mvp.production_gate(rows, ["neutral", "scared"]))
    assert gate["scared"].startswith("BLOCKED") and gate["neutral"].startswith("BLOCKED")


def test_identity_harmonise_brings_colours_to_the_reference():
    from engine2 import mvp
    inv = mvp.pose_inventory("hari")
    if "point_index" not in inv or not os.path.exists(REF):
        pytest.skip("no pointing drawing")
    ref = mvp.figure_rgba(cv2.imread(REF, cv2.IMREAD_UNCHANGED))
    cand = mvp.figure_rgba(cv2.imread(inv["point_index"]["file"], cv2.IMREAD_UNCHANGED))
    out, rep = mvp.harmonize(cand, ref)
    assert rep["shirt"][1] < rep["shirt"][0] and rep["shirt"][1] <= 3.0
    assert (out[..., 3] == cand[..., 3]).all()                  # the shape is never changed
    assert mvp.identity(ref, out)["verdict"] != "MISMATCH"


def test_render_frames_carry_no_debug_overlay(tmp_path, monkeypatch, rig):
    """the clean render never draws the watermark band or any label into the video"""
    from engine2 import mvp
    called = []
    monkeypatch.setattr(mvp, "_mark", lambda img: called.append("mark"))
    r = mvp.render_test("hari", out_root=str(tmp_path), log=lambda *a: None, preview=True,
                        script=[("neutral", 1.0, "house_interior")], total=1.0)
    assert not called and r["checks"]["overlay_in_video"] is False
    import subprocess
    png = str(tmp_path / "f.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.5", "-i", r["files"]["video"], "-frames:v", "1", png])
    f = cv2.imread(png)
    band = f[:15].astype(int)
    assert not (np.abs(band - 20).max(axis=2) < 6).mean() > 0.9   # not the dark watermark band
