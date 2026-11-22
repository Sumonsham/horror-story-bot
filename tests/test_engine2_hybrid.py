"""Engine 2 hybrid (mechanics only - stand-in drawings, NOT art): method choice, complete-pose drawing, renderer
hook, technical video QA."""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _drawing(path, h=900, w=380, colour=(60, 120, 200)):
    img = np.zeros((h + 40, w + 40, 4), np.uint8)
    cv2.circle(img, (20 + w // 2, 20 + h // 9), h // 10, (*colour, 255), -1)
    cv2.rectangle(img, (20 + w // 4, 20 + h // 5), (20 + 3 * w // 4, 20 + h), (*colour, 255), -1)
    cv2.imwrite(path, img)
    return path


def test_full_pose_character_stands_on_the_ground_and_chooses_its_drawings(tmp_path):
    import cartoon_rig as R
    import cinematic_camera as cc
    from engine2.fullpose import FullPoseCharacter
    files = {v: _drawing(str(tmp_path / f"{v}.png")) for v in ("stand", "sit", "point", "walk1", "walk2", "walk3", "walk4")}
    ch = FullPoseCharacter("x", {}, files)
    base = {"x": 960, "ground_y": 935, "facing": 1.0, "t": 0.0}
    assert ch._choose(dict(base, pose=dict(R.POSES["stand"])))[1] == "stand"
    assert ch._choose(dict(base, pose=dict(R.POSES["sit_talk"])))[1] == "sit"
    assert ch._choose(dict(base, pose=dict(R.POSES["stand_point"])))[1] == "point"
    assert [ch._choose(dict(base, pose={}, walk_phase=p))[1] for p in (0.1, 1.7, 3.3, 4.8)] == ["walk1", "walk2", "walk3", "walk4"]
    cam = cc.Camera(640, 360)
    cam.set(960, 700, 1.2)
    img = np.zeros((360, 640, 3), np.uint8)
    j = ch.draw(R.Painter(img, cam), dict(base, pose=dict(R.POSES["stand"])))
    ys = np.where(img.sum(axis=2).any(axis=1))[0]
    assert abs(ys.max() - cam.to_screen(0, 935)[1]) <= 2                    # the feet on the ground line
    assert ch.step_length() > 0


def test_hybrid_picks_drawings_for_complex_actions_and_reports_missing(tmp_path):
    import cartoon_rig as R
    from engine2 import hybrid
    from engine2.fullpose import FullPoseCharacter
    files = {v: _drawing(str(tmp_path / f"{v}.png")) for v in ("stand", "sit")}
    full = FullPoseCharacter("x", {}, files)

    class Cut:                                              # (a stand-in cut-out rig)
        def joints(self, st): return {"head": (0, 0)}
        def foot_floor(self, st): return 0.0
        def draw(self, pt, st): return {}
    h = hybrid.HybridCharacter("x", {}, Cut(), full)
    assert h._pick({"pose": dict(R.POSES["sit_talk"])})[1] == "full_pose"    # sitting: the drawing
    assert h._pick({"pose": dict(R.POSES["stand_talk"])})[1] == "cutout"     # talking: the rig
    assert h._pick({"pose": {}, "walk_phase": 1.0})[1] == "cutout"           # no walk drawings -> the rig walks
    table = hybrid.missing_for(True, sorted(files))
    assert table["sitting"] == "full_pose" and table["running"].startswith("MISSING")
    assert hybrid.missing_for(False, [])["talking"].startswith("MISSING")    # nothing -> reported, never faked


def test_renderer_unchanged_for_ordinary_characters():
    src = open(os.path.join(ROOT, "animation_renderer.py"), encoding="utf-8").read()
    assert 'elif d.get("hybrid"):' in src and 'ch = cutout_rig.load(' in src
    assert "rig.Character(c[\"id\"], d, c.get(\"scale\", 1.0))" in src           # the code rig stays the default


def test_video_qa_checks_the_real_file(tmp_path):
    import subprocess
    from engine2 import videoqa
    good = str(tmp_path / "good.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=24:duration=2",
                    "-f", "lavfi", "-i", "sine=duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", good], check=True)
    assert videoqa.check(good)["pass"]
    bad = str(tmp_path / "bad.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=black:size=640x360:rate=30:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", bad], check=True)
    q = videoqa.check(bad)
    assert not q["pass"] and any("resolution" in p for p in q["problems"]) and any("no audio" in p for p in q["problems"])
