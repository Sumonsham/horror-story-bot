"""Engine 2, stage 2: the permanent Character Asset Library (mechanics - the pictures here are stand-ins, NOT art)."""
import json
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _figure(w=576, h=1024, colour=(40, 90, 200)):
    img = np.zeros((h, w, 4), np.uint8)
    cv2.ellipse(img, (w // 2, h // 5), (w // 9, h // 12), 0, 0, 360, (*colour, 255), -1)
    cv2.rectangle(img, (w // 3, h // 4), (2 * w // 3, int(h * 0.92)), (*colour, 255), -1)
    return img


def _project(tmp_path, monkeypatch, with_sheet=False):
    from engine2 import library as L
    parts = tmp_path / "cartoon_parts"
    key = "74f563185c40"
    d = parts / key
    d.mkdir(parents=True)
    cv2.imwrite(str(d / "body.png"), _figure())
    cv2.imwrite(str(d / "body_src.png"), _figure()[..., :3])
    json.dump({"characters": {key: {"name": "Hari", "status": "ready"}}}, open(parts / "index.json", "w"))
    if with_sheet:
        (d / "sheet").mkdir()
        sj = {"_approved": False}
        for v in ("front", "side", "stand", "sit", "talk", "point"):
            cv2.imwrite(str(d / "sheet" / f"{v}.png"), _figure())
            sj[v] = {"status": "passed"}
        for k in range(1, 5):
            cv2.imwrite(str(d / "sheet" / f"walk{k}.png"), _figure())
        sj["walk"] = {"status": "passed"}
        json.dump(sj, open(d / "sheet" / "sheet.json", "w"))
    monkeypatch.setattr(L, "PARTS_ROOT", str(parts))
    monkeypatch.setattr(L, "LIB", str(tmp_path / "character_library"))
    return L, d


def test_sync_brings_assets_in_once_and_never_approves(tmp_path, monkeypatch):
    L, d = _project(tmp_path, monkeypatch, with_sheet=True)
    L.sync(log=lambda *a: None)
    h = L.Character("Hari")
    m = json.load(open(h.manifest_f))
    for k in ("character_id", "asset_version", "original_reference", "approval_status", "body_proportions",
              "layer_order", "joint_coordinates", "anchor_points", "available_poses", "available_expressions",
              "missing_assets", "validation_status"):
        assert k in m
    assert m["asset_version"] == "v1" and len(m["available_poses"]) == 10
    assert "NOT APPROVED" in m["approval_status"]
    data = json.load(open(os.path.join(h.dir, "v1", "version.json")))
    assert all(e["status"] in ("VISUAL_REVIEW_REQUIRED", "REJECTED") for e in data["assets"].values())   # never more
    assert h.render_assets() == (None, "not approved by the owner")
    L.sync(log=lambda *a: None)                             # again: nothing new, no new version
    assert h.versions() == ["v1"]
    assert open(d / "body.png", "rb").read() and os.path.exists(d / "body_src.png")       # the originals stay


def test_only_the_owner_approves_and_an_approved_version_never_changes(tmp_path, monkeypatch):
    L, d = _project(tmp_path, monkeypatch, with_sheet=True)
    L.sync(log=lambda *a: None)
    h = L.Character("Hari")
    f = os.path.join(L.LIB, "APPROVALS.json")
    a = json.load(open(f))
    a["hari"] = {"v1": {"status": "USER_APPROVED", "method": "full_pose", "note": "test"}}
    json.dump(a, open(f, "w"))
    assets, why = h.render_assets()
    assert why is None and assets["version"] == "v1" and assets["method"] == "full_pose" and "pose:walk4" in assets["files"]
    sha_before = L.sha256(os.path.join(h.dir, "v1", "poses", "front.png"))
    img = _figure(colour=(200, 40, 40))                     # a NEW front drawing arrives later
    cv2.imwrite(str(d / "sheet" / "front.png"), img)
    L.sync(log=lambda *a: None)
    assert h.versions() == ["v1", "v2"]                     # -> a new version ...
    assert L.sha256(os.path.join(h.dir, "v1", "poses", "front.png")) == sha_before        # ... v1 untouched
    assert h.render_assets()[0]["version"] == "v1"          # the video keeps using the APPROVED one
    assert "NOT APPROVED" in json.load(open(h.manifest_f))["approval_status"]              # v2 waits for the owner


def test_integrity_check_finds_damage_and_blocks_use(tmp_path, monkeypatch):
    L, d = _project(tmp_path, monkeypatch, with_sheet=True)
    L.sync(log=lambda *a: None)
    h = L.Character("Hari")
    json.dump({"hari": {"v1": {"status": "USER_APPROVED", "method": "full_pose"}}}, open(os.path.join(L.LIB, "APPROVALS.json"), "w"))
    with open(os.path.join(h.dir, "v1", "poses", "sit.png"), "ab") as fh:
        fh.write(b"damage")
    assert h.verify("v1")["corrupt"] == ["pose:sit"]
    assets, why = h.render_assets()
    assert assets is None and "damaged" in why


def test_missing_assets_are_listed_and_a_bad_picture_is_rejected(tmp_path, monkeypatch):
    L, d = _project(tmp_path, monkeypatch, with_sheet=False)
    L.sync(log=lambda *a: None)
    m = json.load(open(L.Character("Hari").manifest_f))
    assert "pose:front" in m["missing_assets"] and "part:head" in m["missing_assets"]
    assert m["available_poses"] == [] and "happy" in m["missing_expressions"]
    empty = np.zeros((1024, 576, 4), np.uint8)
    cv2.imwrite(str(tmp_path / "empty.png"), empty)
    v, st = L.Character("Hari").add("pose:front", str(tmp_path / "empty.png"), "poses/front.png", "pose")
    assert st == "REJECTED"


def test_production_does_not_read_the_library():
    """the production engine never reads engine 2 (it stays off until the owner approves the new engine)"""
    for f in ("story_engine.py", "animation_renderer.py", "cartoon_rig.py", "scene_planner.py"):
        assert "engine2" not in open(os.path.join(ROOT, f), encoding="utf-8").read()
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    uses = [ln for ln in src.splitlines() if "engine2" in ln]
    assert uses and all("import library" in ln for ln in uses)          # only inside the two test modes
