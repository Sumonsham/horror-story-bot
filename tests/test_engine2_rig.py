"""Engine 2, rig track: Hari's Rigby2D rig (prepared layers, AutoRig + joints from the drawing, animations) played by
the vendored Rigby2D Python runtime and drawn by engine2/rigby/raster.py. These are TECHNICAL checks - they never
approve art (that is the owner's)."""
import json
import os
import sys

import cv2
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
RIG = os.path.join(ROOT, "assets", "character_rigs", "hari")
pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(RIG, "export", "hari.json")), reason="Hari's rig is not built")


def _rig():
    from engine2.rigby import raster as RS
    return RS.Rig(os.path.join(RIG, "export", "hari.json"))


def test_rest_pose_reproduces_the_prepared_layers():
    """the rig at rest = the layers exactly where they are drawn (the artwork is not moved, stretched or lost)"""
    from engine2.rigby import raster as RS
    info = json.load(open(os.path.join(RIG, "layers.json")))
    W, H = info["size"]
    comp = np.full((H, W, 3), 236.0, np.float32)
    for nm in info["order"]:
        L = cv2.imread(os.path.join(RIG, info["layers"][nm]["file"]), cv2.IMREAD_UNCHANGED).astype(np.float32)
        a = L[..., 3:] / 255.0
        comp = L[..., :3] * a + comp * (1 - a)
    rig = _rig()
    f = np.full((H, W, 3), 236, np.uint8)
    RS.draw(rig, rig.pose(), f, 1.0, W / 2, H)
    d = np.abs(f.astype(np.float32) - comp).max(axis=2)
    assert np.mean(d) < 3.0 and (d > 80).mean() < 0.004


def test_no_drawn_pixel_was_lost_and_every_layer_has_its_part():
    info = json.load(open(os.path.join(RIG, "layers.json")))
    assert info["lost_pixels"] < 50
    for part in ("head", "torso", "arm_r", "hand_r", "arm_l", "hand_l", "leg_r", "foot_r", "leg_l", "foot_l"):
        assert info["layers"][part]["pixels"] > 1500


def test_skeleton_has_the_full_bone_list_and_joints_from_the_drawing():
    rig = _rig()
    names = {b.name for b in rig.sk.bones}
    for b in ("hip", "chest", "neck", "head", "upperarm_r", "forearm_r", "hand_r", "upperarm_l", "forearm_l", "hand_l",
              "thigh_r", "shin_r", "foot_r", "thigh_l", "shin_l", "foot_l"):
        assert b in names
    rep = json.load(open(os.path.join(RIG, "rig_report.json")))
    for j in rep["joints"]:
        if "want" in j:
            assert abs(j["want"][0] - j["got"][0]) < 0.6 and abs(j["want"][1] - j["got"][1]) < 0.6
        if "middle_joint_error_px" in j:
            assert j["middle_joint_error_px"] < 1.0
    assert rep["validate_ok"]


def test_walk_keeps_a_planted_foot_still_and_has_both_contacts():
    from engine2.rigby import animations as AN
    from engine2.rigby.proof import foot_slide, _xf
    rig = _rig()
    speed = 2 * AN.STEP / (AN.DUTY * AN.WALK_T)
    slide = foot_slide(rig, speed, AN.WALK_T)
    assert max(slide.values()) < 0.2
    # the right heel is in front at t=0, the left at t=T/2 (alternating legs)
    p0, p1 = rig.pose("walk", 0.0), rig.pose("walk", AN.WALK_T / 2)
    r0, l0 = _xf(p0.bone_world("foot_r"), (0, 0))[0], _xf(p0.bone_world("foot_l"), (0, 0))[0]
    r1, l1 = _xf(p1.bone_world("foot_r"), (0, 0))[0], _xf(p1.bone_world("foot_l"), (0, 0))[0]
    assert r0 - (-36) > 60 and l1 - 42 > 60 and r1 < r0 and l0 < l1


@pytest.mark.parametrize("anim,t", [("walk", 0.0), ("walk", 0.32), ("talk", 1.35), ("indicate", 1.2), ("open_palms", 1.0),
                                    ("sit_talk", 0.6), ("listen", 1.3)])
def test_limbs_stay_joined_in_every_pose(anim, t):
    from engine2.rigby.proof import qa_pose, _alpha
    rig = _rig()
    setup = {s.name: int(_alpha(rig, rig.pose(), [s.name]).sum()) for s in rig.sk.slots}
    probs, _ = qa_pose(rig, rig.pose(anim, t), setup, anim)
    if anim == "sit_talk":                                  # (the seated thighs are foreshortened on purpose)
        probs = [p for p in probs if "changes size" not in p or "leg_" not in p]
    assert probs == []


def test_listening_is_not_the_talking_pose():
    rig = _rig()
    a = rig.pose("talk", 1.35).bone_world("forearm_l")
    b = rig.pose("listen", 1.35).bone_world("forearm_l")
    assert abs(a[4] - b[4]) + abs(a[5] - b[5]) > 30


def test_production_never_reads_the_rig_track():
    for f in ("story_engine.py", "cartoon_rig.py", "scene_planner.py", "animation_renderer.py", "extras.py"):
        assert "engine2.rigby" not in open(os.path.join(ROOT, f), encoding="utf-8").read()
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert src.count("from engine2.rigby import") == 1 and 'env("MODE") == "rig_test"' in src and 'env("MODE") == "pose_art"' in src


def test_arm_lift_check_finds_the_old_artworks_shoulder_breaking():
    """the arm-lift test must FAIL the old flattened artwork when the near arm is raised to 90 degrees (that is the
    defect the owner saw) - a check that passes everything is useless"""
    from engine2.rigby import armlift as AL
    rig = _rig()
    r0, _ = AL.visible_root_ratio(rig, AL.pose_at(rig, "r", 0), "r")
    r90, _ = AL.visible_root_ratio(rig, AL.pose_at(rig, "r", 90), "r")
    assert r90 < 0.6 <= r0 + 0.2 and r90 < r0
    p = AL.pose_at(rig, "r", 90)
    ang = AL._ang(p.bone_world("upperarm_r"))
    assert abs(abs(ang) - 180) < 2                          # really horizontal, pointing away from the body
