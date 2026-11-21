"""ART TEST (GitHub: mode = art_test) - the 2.5D cut-out system on REAL AI pictures, before it is ever switched on.

1. The character designer + the image provider (Cloudflare, the bot's own free account, never a paid one) make the
   parts of a HUMAN (Taranath), a YOUNG MAN (Kishori) and a GHOST (Madhusundari), and the illustrated background of
   the hut - every picture is QUALITY-CHECKED, failed ones are made again (max 2 more), a free-limit message PAUSES.
2. A contact sheet of EVERY picture and every cut part (with the joints marked) - so a person can see them.
3. A short sample video: Taranath talks to Kishori (lip-sync on the AI face, blinks, head turns, gestures) and
   Madhusundari appears (see-through, floating) - the parts move with the same motions as the code-drawn rig.
4. A report: per picture pass / fail + the measured numbers, which characters were drawn as cut-outs and which
   fell back to the code-drawn rig (and why). Nothing is posted anywhere.
"""
import json
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cutout_assets as CA  # noqa: E402
import story_test as ST  # noqa: E402

OUT = os.path.join(HERE, "work", "art_test")
ROOT = os.path.join(HERE, "assets", "cartoon_parts")
SCENES = [
    {"id": "T1", "place": "তারানাথের কুটির, রাত", "cast": ["taranath", "kishori"],
     "lines": [("s_1111_093554_4", 0, "taranath", "kishori"), ("s_1111_093554_4", 4, "taranath", "kishori")]},
    {"id": "T2", "place": "তারানাথের কুটির, অমাবস্যার রাত", "cast": ["taranath", "madhusundari"], "present": ["taranath"],
     "lines": [("s_1111_093344_0", 5, "narrator", None)]},
]


def sheet(reg, keys, path):
    """every picture + every cut part with its joint marked, on one image"""
    tiles = []
    for name, key in keys.items():
        d = os.path.join(reg.root, key)
        row = []
        for f in ["body.png", "piece_torso.png", "piece_arm.png", "piece_legs.png", "head_front.png", "head_three_q.png",
                  "head_profile.png", "head_scared.png"] + \
                 sorted(x for x in os.listdir(d) if x.startswith("part_")) if os.path.isdir(d) else []:
            p = os.path.join(d, f)
            if not os.path.exists(p):
                continue
            im = cv2.imread(p, cv2.IMREAD_UNCHANGED)
            if im is None or im.ndim < 3 or im.shape[2] < 4:
                continue
            bg = np.full(im.shape[:2] + (3,), (90, 90, 90), np.float32)
            a = im[..., 3:4] / 255.0
            t = (bg * (1 - a) + im[..., :3] * a).astype(np.uint8)
            if f.startswith("part_"):
                try:
                    meta = json.load(open(os.path.join(d, "rig.json")))["parts"][f[5:-4]]
                    cv2.circle(t, (int(meta["pivot"][0]), int(meta["pivot"][1])), 5, (0, 0, 255), -1)
                except Exception:
                    pass
            h = 220
            t = cv2.resize(t, (max(8, int(t.shape[1] * h / t.shape[0])), h))
            cv2.putText(t, f[:14], (3, 14), 0, 0.4, (255, 255, 255), 1)
            row.append(t)
        if row:
            r = np.hstack(row)
            cv2.putText(r, name, (5, 210), 0, 0.7, (0, 255, 255), 2)
            tiles.append(r)
    if not tiles:
        return None
    w = max(t.shape[1] for t in tiles)
    img = np.vstack([np.pad(t, ((0, 0), (0, w - t.shape[1]), (0, 0))) for t in tiles])
    if img.shape[1] > 3000:
        img = cv2.resize(img, (3000, int(img.shape[0] * 3000 / img.shape[1])))
    cv2.imwrite(path, img)
    return path


PLAN_CAST = [   # the test plan's characters (in this order; a paused run continues with the next one next time)
    {"id": "hari", "name": "Hari", "name_local": "হরি", "gender": "male", "age": "adult", "kind": "human",
     "look": "an ordinary Bengali man of about forty, short black hair, thick moustache, a light blue full-sleeve shirt and grey trousers, black sandals"},
    {"id": "saraswati", "name": "Saraswati", "name_local": "সরস্বতী", "gender": "female", "age": "adult", "kind": "human",
     "look": "a Bengali village woman of about thirty-five, black hair in a bun, a red bindi, a red cotton saree with a broad gold border worn in the Bengali style with the pallu over the left shoulder, a red blouse, gold bangles, bare feet"},
    {"id": "petni", "name": "Petni", "name_local": "পেত্নী", "gender": "female", "age": "young", "kind": "ghost",
     "look": "a female ghost (petni), very long open black hair falling to her waist, pale bluish skin, glowing white eyes, a torn old white saree, no feet visible"},
]
POSES = [("stand", 0.6, 1.0, "3/4"), ("stand", 0.0, 1.0, "front"), ("stand", 1.0, 1.0, "side"), ("walk", 0.6, 1.0, "walk"),
         ("sit_talk", 0.9, 1.0, "sit+talk"), ("stand_point", 0.6, 1.0, "point"), ("stand", -0.6, -1.0, "blink, facing left")]


def poses_sheet(reg, people, path):
    """screenshots of every ASSEMBLED character in the test plan's poses (what the video will show)"""
    import cartoon_rig as R
    import cinematic_camera as cc
    import cutout_rig as CR
    rows = []
    for c in people:
        key = CA.char_key({"name": c["name"], "look": c["look"]})
        ch = CR.load(c["id"], c["design"], reg.root, key)
        tiles = []
        for pose, yaw, f, label in POSES:
            img = np.full((420, 280, 3), (60, 70, 55), np.uint8)
            if ch:
                cam = cc.Camera(280, 420)
                cam.set(960, 740, 1.8)
                p = R.walk_pose(1.1) if pose == "walk" else dict(R.POSES[pose])
                ch.draw(R.Painter(img, cam), {"x": 960, "ground_y": 935, "facing": f, "head_yaw": yaw, "pose": p, "t": 1.0,
                                              "mouth": (0.8, "A") if "talk" in pose else (0.0, "rest"),
                                              "blink": 1.0 if "blink" in label else 0.0,
                                              "float": 14.0 if c["design"].get("ghost") else 0.0})
            else:
                cv2.putText(img, "not ready", (60, 210), 0, 0.7, (255, 255, 255), 2)
            cv2.putText(img, f"{c['name']}: {label}", (4, 16), 0, 0.45, (255, 255, 255), 1)
            tiles.append(img)
        rows.append(np.hstack(tiles))
    if rows:
        cv2.imwrite(path, np.vstack(rows))
        return path
    return None


def run(image_fn, llm=None, log=print, budget=60, W=1280, H=720, fps=24):
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    reg = CA.Registry(ROOT)
    cast = ST.designed_cast(llm, log)
    import character_designer as CD_
    plan_people = [dict(c, design=CD_.design(c)[0]) for c in PLAN_CAST]
    want = plan_people + [c for c in cast if c["id"] in ("taranath", "madhusundari", "kishori")]
    recs = [{"name": c["name"], "look": c["look"], "design": c["design"]} for c in want]
    try:
        gen = CA.ensure_cast(recs, reg, image_fn, log=log, budget=budget, places=[("house_interior", {})])
    except Exception as e:                                 # the exact blocker is reported; finished work stays
        gen = {"characters": {r["name"]: {"status": reg.index["characters"].get(CA.char_key(r), {}).get("status", "pending"),
                                          "problems": []} for r in recs}, "plates": {}, "paused": True, "made": 0,
               "blocker": f"{type(e).__name__}: {str(e)[:300]}"}
        reg.save()
        log(f"  ART TEST BLOCKED: {gen['blocker']}")
    keys = {c["name"]: CA.char_key({"name": c["name"], "look": c["look"]}) for c in want}
    sh = sheet(reg, keys, os.path.join(OUT, "art_sheet.jpg"))
    ps = poses_sheet(reg, want, os.path.join(OUT, "art_poses.jpg"))
    ST.OUT = OUT
    scenes = []
    for sd in SCENES:
        try:
            scenes.append(ST.build_scene(sd, W, H, fps, llm, log, cast, art=reg))
        except Exception as e:
            scenes.append({"id": sd["id"], "error": str(e)[:300]})
            log(f"  art test scene {sd['id']} failed: {str(e)[:200]}")
    vids = [s["video"] for s in scenes if s.get("video")]
    final = None
    if vids:
        lst = os.path.join(OUT, "scenes.txt")
        with open(lst, "w") as f:
            f.writelines(f"file '{os.path.abspath(v)}'\n" for v in vids)
        final = os.path.join(OUT, "art_test.mp4")
        os.system(f"ffmpeg -y -loglevel error -f concat -safe 0 -i '{lst}' -c copy -movflags +faststart '{final}'")
    report = {"generation": gen, "assets": {n: reg.index["characters"].get(k, {}).get("qa") for n, k in keys.items()},
              "plate": reg.index["plates"].get("house_interior"),
              "scenes": [{"id": s.get("id"), "drawn_by": s.get("drawn_by"), "plate": s.get("plate"),
                          "quality": s.get("quality", {}).get("all_pass") if isinstance(s.get("quality"), dict) else None,
                          "failed_checks": {k: v for k, v in (s.get("quality") or {}).items() if isinstance(v, dict) and not v.get("pass")},
                          "error": s.get("error")} for s in scenes],
              "seconds": round(time.time() - t0, 1), "sheet": sh, "poses": ps, "video": final,
              "plans": {n: reg.index["characters"].get(k, {}).get("plan") for n, k in keys.items()},
              "rig_method": {n: reg.index["characters"].get(k, {}).get("rig_method") for n, k in keys.items()}}
    with open(os.path.join(OUT, "art_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    keep = os.path.join(ROOT, "_art_test")                 # kept in the repo too: the results can be examined later
    os.makedirs(keep, exist_ok=True)
    import shutil
    for f in ("art_report.json", "art_sheet.jpg", "art_poses.jpg"):
        if os.path.exists(os.path.join(OUT, f)):
            shutil.copy(os.path.join(OUT, f), os.path.join(keep, f))
    return report
